"""Review tools (Phase B).

The user-facing `:PoorCLIReview <verb>` commands (Phase A §4.2) are
preserved as chat-prompt seeds; this module backs them with callable tools
the agent invokes itself when it chooses. Reviewers can also fire these
directly via chat ("review PR 42") without going through the verb.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from typing import Any, Dict, List

from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


async def _run(argv: List[str], *, cwd: str, timeout: float = 60.0) -> Any:
    def _sync():
        try:
            return subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as e:
            class _R:
                returncode = 124
                stdout = e.stdout or ""
                stderr = (e.stderr or "") + "\n[timed out]"
            return _R()

    return await asyncio.get_running_loop().run_in_executor(None, _sync)


def _ctx_cwd(ctx: Any) -> str:
    return getattr(ctx, "cwd", None) or os.getcwd()


async def handle_pr(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    number = args.get("number")
    if number is None:
        return ToolResult.error("number is required")
    try:
        n = int(number)
    except (TypeError, ValueError):
        return ToolResult.error("number must be an integer")
    repo = args.get("repo")
    argv = ["gh", "pr", "view", str(n), "--json",
            "number,title,author,state,body,baseRefName,headRefName,files,commits"]
    if repo:
        argv.extend(["--repo", str(repo)])
    meta_proc = await _run(argv, cwd=cwd)
    if meta_proc.returncode != 0:
        return ToolResult.error(
            f"gh pr view failed: {meta_proc.stderr.strip() or meta_proc.stdout.strip()}"
        )
    diff_proc = await _run(
        ["gh", "pr", "diff", str(n)] + (["--repo", str(repo)] if repo else []),
        cwd=cwd,
        timeout=90.0,
    )
    blocks: List[Any] = [
        CodeBlock(language="json", code=meta_proc.stdout or "{}"),
    ]
    if diff_proc.returncode == 0 and diff_proc.stdout.strip():
        blocks.append(CodeBlock(language="diff", code=diff_proc.stdout))
    return ToolResult(content=blocks, metadata={"pr_number": n})


async def handle_changes(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    base = str(args.get("base") or "HEAD")
    result = await _run(["git", "diff", base], cwd=cwd, timeout=45.0)
    if result.returncode != 0:
        return ToolResult.error(
            f"git diff failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    if not result.stdout.strip():
        return ToolResult.text(f"no changes vs {base}")
    return ToolResult(content=[CodeBlock(language="diff", code=result.stdout)])


async def handle_lint(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    path = args.get("path")
    # Discover common linter configs and pick one best-effort. Priority:
    # ruff (if pyproject or ruff.toml present), eslint (if .eslintrc*),
    # else we return a helpful message — never guess commands that might
    # not be installed.
    root = os.path.abspath(cwd)
    linters: List[List[str]] = []
    if os.path.exists(os.path.join(root, "pyproject.toml")) or os.path.exists(
        os.path.join(root, "ruff.toml")
    ):
        argv = ["ruff", "check"]
        if path:
            argv.append(str(path))
        linters.append(argv)
    if any(
        os.path.exists(os.path.join(root, p))
        for p in (".eslintrc", ".eslintrc.js", ".eslintrc.json", "eslint.config.js")
    ):
        argv = ["eslint"]
        if path:
            argv.append(str(path))
        else:
            argv.extend([".", "--ext", ".js,.ts,.jsx,.tsx"])
        linters.append(argv)
    if not linters:
        return ToolResult.text(
            "no linter config detected (looked for pyproject.toml/ruff.toml/.eslintrc*)"
        )
    blocks: List[Any] = []
    any_err = False
    for argv in linters:
        proc = await _run(argv, cwd=cwd)
        blocks.append(TextBlock(text=f"$ {' '.join(argv)} (exit {proc.returncode})"))
        out = (proc.stdout or "") + (proc.stderr or "")
        if out.strip():
            blocks.append(CodeBlock(language="text", code=out[-6000:]))
        if proc.returncode != 0:
            any_err = True
    return ToolResult(content=blocks, is_error=any_err)


register_tool(
    name="review.pr",
    description=(
        "Fetch a GitHub PR by number via the ``gh`` CLI: metadata JSON plus the "
        "unified diff. Optional ``repo`` (owner/name) overrides the default."
    ),
    schema={
        "type": "object",
        "required": ["number"],
        "properties": {
            "number": {"type": "integer", "minimum": 1},
            "repo": {"type": "string"},
        },
        "additionalProperties": False,
    },
    handler=handle_pr,
    timeout_s=120.0,
)

register_tool(
    name="review.changes",
    description=(
        "Return ``git diff <base>`` (default ``HEAD``). Use this when the user "
        "asks 'review my changes' without specifying a PR."
    ),
    schema={
        "type": "object",
        "properties": {"base": {"type": "string", "default": "HEAD"}},
        "additionalProperties": False,
    },
    handler=handle_changes,
    timeout_s=60.0,
    cacheable=True,
    cache_ttl_s=15.0,
)

register_tool(
    name="review.lint",
    description=(
        "Run the repo's configured linter(s): ruff for Python, eslint for "
        "JS/TS. Returns each tool's exit + output. Does not attempt to "
        "install missing linters — that's the user's job."
    ),
    schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "additionalProperties": False,
    },
    handler=handle_lint,
    timeout_s=120.0,
)
