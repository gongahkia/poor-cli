"""Git tools.

These tools let the agent inspect and modify the repository without asking
the user to run git commands.

Handler signature::

    async def handle_X(*, ctx, args) -> ToolResult

``ctx`` is a duck-typed context object with:
  - ``cwd`` — absolute path of the workdir (defaults to ``os.getcwd()``)
  - ``async notify_client(method, params)`` — optional client notification hook

Tests substitute a ``SimpleNamespace`` for ``ctx``; the production dispatcher
synthesises it from the active session handler.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Tuple

from poor_cli.tool_blocks import (
    CodeBlock,
    DiffBlock,
    FileRefBlock,
    TableBlock,
    TextBlock,
    ToolResult,
)
from poor_cli.tools._registry import register_tool


# ───────────────────────── subprocess helpers ─────────────────────────


class _RunResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


async def _run(
    argv: List[str], *, cwd: str, timeout: float = 15.0, input_text: Optional[str] = None
) -> _RunResult:
    """Run a subprocess asynchronously. Returns captured stdout+stderr + returncode.
    Never raises on non-zero exit — callers inspect ``returncode``."""

    def _sync() -> _RunResult:
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                input=input_text,
                timeout=timeout,
            )
            return _RunResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as e:
            return _RunResult(
                124, e.stdout or "", (e.stderr or "") + "\n[timed out]"
            )
        except FileNotFoundError:
            return _RunResult(127, "", f"executable not found: {argv[0]}")

    return await asyncio.get_running_loop().run_in_executor(None, _sync)


def _ctx_cwd(ctx: Any) -> str:
    return getattr(ctx, "cwd", None) or os.getcwd()


def _ctx_has_plugin(ctx: Any, name: str) -> bool:
    fn = getattr(ctx, "has_plugin", None)
    if callable(fn):
        try:
            return bool(fn(name))
        except Exception:
            return False
    return False


async def _ctx_notify(ctx: Any, method: str, params: Dict[str, Any]) -> None:
    fn = getattr(ctx, "notify_client", None)
    if fn is None:
        return
    try:
        maybe_coro = fn(method, params)
        if asyncio.iscoroutine(maybe_coro):
            await maybe_coro
    except Exception:
        pass


def _inside_git_repo(cwd: str) -> bool:
    return os.path.isdir(os.path.join(cwd, ".git")) or os.path.exists(
        os.path.join(cwd, ".git")
    )


# ───────────────────────── git.status ─────────────────────────

_STATUS_XY = {
    " M": ("unstaged", "modified"),
    "M ": ("staged", "modified"),
    "MM": ("both", "modified"),
    "A ": ("staged", "added"),
    "AM": ("both", "added+modified"),
    "D ": ("staged", "deleted"),
    " D": ("unstaged", "deleted"),
    "R ": ("staged", "renamed"),
    "??": ("untracked", "untracked"),
    "!!": ("ignored", "ignored"),
}


async def handle_status(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    if not _inside_git_repo(cwd):
        return ToolResult.error("not a git repository", not_a_repo=True)
    result = await _run(["git", "status", "--porcelain=v1", "-b"], cwd=cwd)
    if result.returncode != 0:
        return ToolResult.error(
            f"git status failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    lines = result.stdout.splitlines()
    branch = ""
    rows: List[List[str]] = []
    for line in lines:
        if line.startswith("## "):
            # "## main...origin/main [ahead 2]" etc.
            branch = line[3:]
            continue
        if len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:]
        group, label = _STATUS_XY.get(xy, ("other", xy.strip() or "?"))
        rows.append([group, label, path])
    blocks: List[Any] = []
    if branch:
        blocks.append(TextBlock(text=f"branch: {branch}"))
    if rows:
        blocks.append(
            TableBlock(columns=["scope", "change", "path"], rows=rows)
        )
    else:
        blocks.append(TextBlock(text="working tree clean"))
    return ToolResult(content=blocks)


register_tool(
    name="git.status",
    description=(
        "Return the structured git status for the repo: branch, staged/unstaged "
        "file changes, and untracked files. Prefer this over asking the user to "
        "run git status."
    ),
    schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    handler=handle_status,
    examples=[
        {
            "when": "about to start a commit; want to know what's changed",
            "args": {},
            "result_summary": "branch + table of staged/unstaged/untracked files",
        }
    ],
    cacheable=True,
    cache_ttl_s=30.0,
    circuit_disabled=True,
)


# ───────────────────────── git.diff ─────────────────────────


async def handle_diff(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    if not _inside_git_repo(cwd):
        return ToolResult.error("not a git repository", not_a_repo=True)
    staged = bool(args.get("staged"))
    path = args.get("path")
    argv = ["git", "diff"]
    if staged:
        argv.append("--staged")
    if path:
        argv.extend(["--", str(path)])
    result = await _run(argv, cwd=cwd, timeout=30.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git diff failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    diff_text = result.stdout
    if not diff_text.strip():
        return ToolResult(
            content=[TextBlock(text="no diff" + (" (staged)" if staged else ""))]
        )
    return ToolResult(content=[CodeBlock(language="diff", code=diff_text)])


register_tool(
    name="git.diff",
    description=(
        "Return a unified diff. `staged=true` shows staged changes; `path` "
        "restricts to one file. Output is a CodeBlock with language=diff so the "
        "frontend renders +/- highlighting."
    ),
    schema={
        "type": "object",
        "properties": {
            "staged": {"type": "boolean", "default": False},
            "path": {"type": "string"},
        },
        "additionalProperties": False,
    },
    handler=handle_diff,
    examples=[
        {
            "when": "user asks 'what did I change'",
            "args": {"staged": False},
            "result_summary": "unified diff of working tree vs HEAD",
        }
    ],
    cacheable=True,
    cache_ttl_s=30.0,
    circuit_disabled=True,
)


# ───────────────────────── git.stage / git.unstage ─────────────────────────


async def handle_stage(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    paths = args.get("paths") or []
    if not paths:
        return ToolResult.error("paths is required")
    if not isinstance(paths, list):
        return ToolResult.error("paths must be a list of strings")
    argv = ["git", "add", "--"] + [str(p) for p in paths]
    result = await _run(argv, cwd=cwd, timeout=15.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git add failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(f"staged {len(paths)} path(s)")


register_tool(
    name="git.stage",
    description="Stage one or more paths for commit (``git add``).",
    schema={
        "type": "object",
        "required": ["paths"],
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            }
        },
        "additionalProperties": False,
    },
    handler=handle_stage,
    exclusive=True,
    invalidates=["git.status", "git.diff", "hunks.list"],
)


async def handle_unstage(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    paths = args.get("paths") or []
    if not paths:
        return ToolResult.error("paths is required")
    argv = ["git", "reset", "HEAD", "--"] + [str(p) for p in paths]
    result = await _run(argv, cwd=cwd, timeout=15.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git reset failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(f"unstaged {len(paths)} path(s)")


register_tool(
    name="git.unstage",
    description="Unstage one or more paths (``git reset HEAD``).",
    schema={
        "type": "object",
        "required": ["paths"],
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            }
        },
        "additionalProperties": False,
    },
    handler=handle_unstage,
    exclusive=True,
    invalidates=["git.status", "git.diff", "hunks.list"],
)


# ───────────────────────── git.commit ─────────────────────────


async def handle_commit(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    message = str(args.get("message") or "").strip()
    if not message:
        return ToolResult.error("message is required")
    auto_stage = bool(args.get("auto_stage"))
    amend = bool(args.get("amend"))

    if _ctx_has_plugin(ctx, "commit_ui"):
        # fire-and-forget UI hint for API clients; commit still runs here.
        await _ctx_notify(
            ctx,
            "integration.git.openCommit",
            {"message": message},
        )

    argv = ["git", "commit", "-m", message]
    if auto_stage:
        argv.insert(2, "-a")
    if amend:
        argv.insert(2, "--amend")
    result = await _run(argv, cwd=cwd, timeout=30.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git commit failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult(
        content=[TextBlock(text=result.stdout.strip() or "commit created")],
        metadata={},
    )


register_tool(
    name="git.commit",
    description=(
        "Create a git commit with a given message. Set ``auto_stage=true`` to "
        "stage tracked modified files before committing, ``amend=true`` to "
        "amend HEAD."
    ),
    schema={
        "type": "object",
        "required": ["message"],
        "properties": {
            "message": {
                "type": "string",
                "description": "Full commit message. First line is the subject.",
            },
            "auto_stage": {"type": "boolean", "default": False},
            "amend": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    handler=handle_commit,
    exclusive=True,
    degraded_fallbacks=["cli"],
    invalidates=["git.status", "git.diff", "git.log", "hunks.list"],
    examples=[
        {
            "when": "user asked for a conventional commit",
            "args": {"message": "feat: add git.commit tool"},
            "result_summary": "commit hash + subject",
        }
    ],
)


# ───────────────────────── git.log ─────────────────────────


async def handle_log(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    limit = int(args.get("limit") or 20)
    limit = max(1, min(limit, 500))
    sep = "\x1f"
    fmt = sep.join(["%h", "%an", "%ar", "%s"])
    result = await _run(
        ["git", "log", f"--pretty=format:{fmt}", f"-n{limit}"], cwd=cwd, timeout=15.0
    )
    if result.returncode != 0:
        return ToolResult.error(
            f"git log failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    rows: List[List[str]] = []
    for line in result.stdout.splitlines():
        parts = line.split(sep)
        while len(parts) < 4:
            parts.append("")
        rows.append(parts[:4])
    if not rows:
        return ToolResult.text("no commits on this branch yet")
    return ToolResult(
        content=[TableBlock(columns=["hash", "author", "when", "subject"], rows=rows)]
    )


register_tool(
    name="git.log",
    description="Return the last N commits on the current branch as a TableBlock.",
    schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 20}
        },
        "additionalProperties": False,
    },
    handler=handle_log,
    cacheable=True,
    cache_ttl_s=30.0,
    circuit_disabled=True,
)


# ───────────────────────── git.branch ─────────────────────────


async def handle_branch_list(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    result = await _run(
        ["git", "branch", "--format=%(HEAD) %(refname:short)"], cwd=cwd, timeout=10.0
    )
    if result.returncode != 0:
        return ToolResult.error(
            f"git branch failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    rows: List[List[str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        head, _, name = line.partition(" ")
        rows.append(["*" if head == "*" else " ", name])
    return ToolResult(content=[TableBlock(columns=["current", "branch"], rows=rows)])


async def handle_branch_create(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    name = str(args.get("name") or "").strip()
    if not name:
        return ToolResult.error("name is required")
    start_point = args.get("start_point")
    argv = ["git", "branch", name]
    if start_point:
        argv.append(str(start_point))
    result = await _run(argv, cwd=cwd, timeout=10.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git branch create failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(f"branch {name!r} created")


async def handle_branch_checkout(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    name = str(args.get("name") or "").strip()
    if not name:
        return ToolResult.error("name is required")
    argv = ["git", "checkout", name]
    if args.get("create"):
        argv.insert(2, "-b")
    result = await _run(argv, cwd=cwd, timeout=15.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git checkout failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(
        (result.stdout.strip() or result.stderr.strip() or f"checked out {name!r}")
    )


register_tool(
    name="git.branch.list",
    description="List local branches; the current one is marked with `*`.",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_branch_list,
    cacheable=True,
    cache_ttl_s=30.0,
    circuit_disabled=True,
)
register_tool(
    name="git.branch.create",
    description="Create a new local branch (optionally from a starting revision).",
    schema={
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "start_point": {"type": "string"},
        },
        "additionalProperties": False,
    },
    handler=handle_branch_create,
    exclusive=True,
    invalidates=["git.branch.list"],
)
register_tool(
    name="git.branch.checkout",
    description="Check out a branch. `create=true` shortcuts `git checkout -b`.",
    schema={
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "create": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    handler=handle_branch_checkout,
    exclusive=True,
    invalidates=["git.branch.list", "git.status", "git.diff", "git.log", "hunks.list"],
)


# ───────────────────────── git.push ─────────────────────────


async def handle_push(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    branch = args.get("branch")
    remote = args.get("remote") or "origin"
    force = bool(args.get("force"))
    set_upstream = bool(args.get("set_upstream"))
    argv = ["git", "push", str(remote)]
    if set_upstream:
        argv.insert(2, "-u")
    if force:
        argv.append("--force-with-lease")
    if branch:
        argv.append(str(branch))
    result = await _run(argv, cwd=cwd, timeout=60.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git push failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(
        (result.stdout.strip() or result.stderr.strip() or "pushed")
    )


register_tool(
    name="git.push",
    description=(
        "Push to a remote branch. Defaults to ``origin`` with the current "
        "tracked branch. ``force`` uses ``--force-with-lease`` (never "
        "unconditional force). This tool is typically permission-gated; expect "
        "a user prompt unless the session preset allows it."
    ),
    schema={
        "type": "object",
        "properties": {
            "remote": {"type": "string", "default": "origin"},
            "branch": {"type": "string"},
            "force": {"type": "boolean", "default": False},
            "set_upstream": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    handler=handle_push,
    exclusive=True,
    timeout_s=60.0,
    max_per_minute=3,
)
