"""Filesystem browse tools (Phase B).

``fs.browse`` returns a directory listing as structured data. When oil.nvim
is available, a notification pops oil's buffer for the same path so the user
sees what the agent just enumerated. Falls back to pure stdlib otherwise.

``fs.glob`` does fast pattern matching respecting .gitignore (via ``git
ls-files`` when inside a repo; stdlib glob otherwise).
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import subprocess
from typing import Any, Dict, List

from poor_cli.tool_blocks import FileRefBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
}


def _ctx_cwd(ctx: Any) -> str:
    return getattr(ctx, "cwd", None) or os.getcwd()


async def _notify(ctx: Any, method: str, params: Dict[str, Any]) -> None:
    fn = getattr(ctx, "notify_client", None)
    if fn is None:
        return
    try:
        maybe = fn(method, params)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass


def _list_dir(path: str, max_depth: int, skip: set) -> List[Dict[str, Any]]:
    """Walk ``path`` up to ``max_depth`` levels deep. Returns a flat list of
    ``{path, kind}`` records relative to ``path``."""
    out: List[Dict[str, Any]] = []
    base_depth = path.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        rel_root = os.path.relpath(root, path)
        cur_depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        if cur_depth > max_depth:
            dirs[:] = []
            continue
        for d in dirs:
            out.append(
                {"path": os.path.join(rel_root, d) if rel_root != "." else d, "kind": "dir"}
            )
        for f in files:
            if f.startswith("."):
                continue
            out.append(
                {"path": os.path.join(rel_root, f) if rel_root != "." else f, "kind": "file"}
            )
    return out


async def handle_browse(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    raw = str(args.get("path") or ".")
    target = os.path.abspath(os.path.join(cwd, raw))
    if not os.path.isdir(target):
        return ToolResult.error(f"not a directory: {raw}", not_a_dir=True)
    max_depth = int(args.get("max_depth") or 2)
    max_depth = max(1, min(max_depth, 5))
    entries = _list_dir(target, max_depth, _SKIP_DIRS)
    # oil.nvim UX: pop the directory in the user's oil buffer if available.
    if getattr(ctx, "has_plugin", lambda _: False)("oil"):
        await _notify(ctx, "integration.oil.openPath", {"path": target})
    rows = [[e["kind"], e["path"]] for e in entries[:500]]
    blocks: List[Any] = [TextBlock(text=f"{target} ({len(entries)} entries, depth≤{max_depth})")]
    if rows:
        blocks.append(TableBlock(columns=["kind", "path"], rows=rows))
    return ToolResult(content=blocks, metadata={"entries": entries, "root": target})


async def handle_glob(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    pattern = str(args.get("pattern") or "").strip()
    if not pattern:
        return ToolResult.error("pattern is required")
    # Prefer git ls-files when inside a repo — respects .gitignore, stays fast.
    if os.path.isdir(os.path.join(cwd, ".git")):
        proc = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=15.0,
            ),
        )
        if proc.returncode == 0:
            all_paths = proc.stdout.splitlines()
            matches = fnmatch.filter(all_paths, pattern)
            matches.sort()
            return _glob_result(pattern, matches[:500])
    # Fallback: stdlib walk + fnmatch.
    matches: List[str] = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), cwd)
            if fnmatch.fnmatch(rel, pattern):
                matches.append(rel)
        if len(matches) >= 500:
            break
    matches.sort()
    return _glob_result(pattern, matches[:500])


def _glob_result(pattern: str, matches: List[str]) -> ToolResult:
    if not matches:
        return ToolResult.text(f"no matches for {pattern!r}")
    return ToolResult(
        content=[
            TextBlock(text=f"{len(matches)} match(es) for {pattern!r}"),
            TableBlock(columns=["path"], rows=[[m] for m in matches]),
        ],
        metadata={"matches": matches},
    )


register_tool(
    name="fs.browse",
    description=(
        "List the contents of a directory as structured rows (kind, path). "
        "When oil.nvim is available the path is also popped in oil's buffer "
        "for the user. Paths are relative to ``path``. ``max_depth`` clamps "
        "traversal (1..5, default 2)."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "default": "."},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": 5, "default": 2},
        },
        "additionalProperties": False,
    },
    handler=handle_browse,
)

register_tool(
    name="fs.glob",
    description=(
        "Fast path-pattern match over the repo. Respects .gitignore when "
        "inside a git repo (uses ``git ls-files``); stdlib fnmatch otherwise. "
        "Capped at 500 results."
    ),
    schema={
        "type": "object",
        "required": ["pattern"],
        "properties": {"pattern": {"type": "string"}},
        "additionalProperties": False,
    },
    handler=handle_glob,
)
