"""Hunk-level git tools (Phase B).

Wraps gitsigns when available (so hunks appear in the user's sign column
workflow) and falls back to git-apply / git-add patch-mode. Focus: let the
agent reason over individual hunks of a file and stage/reset them surgically
instead of staging whole files.

``hunks.ai_mark`` lets the agent tag a hunk it just authored so the gitsigns
integration's ai_hunks extmark kicks in on that range.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from typing import Any, Dict, List

from poor_cli.tool_blocks import DiffBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


async def _run(argv: List[str], *, cwd: str, timeout: float = 15.0) -> Any:
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


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_hunks(diff: str) -> List[Dict[str, Any]]:
    """Parse ``git diff`` output into a list of hunk records. Only the first
    file's hunks are returned per call — callers pass a ``path`` arg."""
    hunks: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    body: List[str] = []
    for line in diff.splitlines():
        m = _HUNK_HEADER.match(line)
        if m:
            if current:
                current["body"] = "\n".join(body)
                hunks.append(current)
            old_start = int(m.group(1))
            old_len = int(m.group(2) or "1")
            new_start = int(m.group(3))
            new_len = int(m.group(4) or "1")
            current = {
                "index": len(hunks) + 1,
                "old_start": old_start,
                "old_lines": old_len,
                "new_start": new_start,
                "new_lines": new_len,
            }
            body = [line]
        elif current:
            body.append(line)
    if current:
        current["body"] = "\n".join(body)
        hunks.append(current)
    return hunks


async def handle_list(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    path = str(args.get("file") or "").strip()
    if not path:
        return ToolResult.error("file is required")
    result = await _run(["git", "diff", "--", path], cwd=cwd)
    if result.returncode != 0:
        return ToolResult.error(
            f"git diff failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    hunks = _parse_hunks(result.stdout or "")
    if not hunks:
        return ToolResult.text(f"{path}: no hunks (clean or staged)")
    rows = [
        [
            str(h["index"]),
            f"{h['old_start']},{h['old_lines']}",
            f"{h['new_start']},{h['new_lines']}",
        ]
        for h in hunks
    ]
    return ToolResult(
        content=[
            TextBlock(text=f"{path}: {len(hunks)} hunk(s)"),
            TableBlock(columns=["#", "-", "+"], rows=rows),
        ],
        metadata={"hunks": hunks},
    )


async def handle_stage(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    path = str(args.get("file") or "").strip()
    if not path:
        return ToolResult.error("file is required")
    # The gitsigns path is UX-only (makes the stage visible in the user's
    # sign column). The actual stage uses git add <file> for simplicity
    # during Phase B; per-hunk staging via git apply is a follow-up.
    await _notify(
        ctx,
        "integration.gitsigns.stage",
        {"file": path, "line": args.get("line")},
    )
    result = await _run(["git", "add", "--", path], cwd=cwd)
    if result.returncode != 0:
        return ToolResult.error(
            f"git add failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(f"staged {path}")


async def handle_reset(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    path = str(args.get("file") or "").strip()
    if not path:
        return ToolResult.error("file is required")
    await _notify(
        ctx,
        "integration.gitsigns.reset",
        {"file": path, "line": args.get("line")},
    )
    result = await _run(["git", "checkout", "--", path], cwd=cwd)
    if result.returncode != 0:
        return ToolResult.error(
            f"git checkout -- failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(f"reset {path} to HEAD")


async def handle_ai_mark(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    path = str(args.get("file") or "").strip()
    line = int(args.get("line") or 0)
    if not path or line <= 0:
        return ToolResult.error("file and line (≥1) are required")
    await _notify(ctx, "integration.gitsigns.aiMark", {"file": path, "line": line})
    return ToolResult.text(f"marked {path}:{line} as AI-authored")


register_tool(
    name="hunks.list",
    description=(
        "List the hunks (diff chunks) for a single file. Output includes a "
        "TableBlock with old/new line ranges and the raw hunk bodies in "
        "metadata['hunks'] for downstream processing."
    ),
    schema={
        "type": "object",
        "required": ["file"],
        "properties": {"file": {"type": "string"}},
        "additionalProperties": False,
    },
    handler=handle_list,
)

register_tool(
    name="hunks.stage",
    description=(
        "Stage changes in a file. If gitsigns is available the stage is "
        "reflected in the user's sign column immediately."
    ),
    schema={
        "type": "object",
        "required": ["file"],
        "properties": {
            "file": {"type": "string"},
            "line": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    },
    handler=handle_stage,
)

register_tool(
    name="hunks.reset",
    description="Reset file changes to HEAD. Destructive — unstaged work is lost.",
    schema={
        "type": "object",
        "required": ["file"],
        "properties": {
            "file": {"type": "string"},
            "line": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    },
    handler=handle_reset,
    exclusive=True,
)

register_tool(
    name="hunks.ai_mark",
    description=(
        "Tag a hunk as AI-authored so the gitsigns integration shows the "
        "distinct ✱ glyph. Use immediately after writing via a file tool "
        "(fs.write, apply_diff) so the user can tell AI edits from their own."
    ),
    schema={
        "type": "object",
        "required": ["file", "line"],
        "properties": {
            "file": {"type": "string"},
            "line": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    },
    handler=handle_ai_mark,
)
