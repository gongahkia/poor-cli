"""Watch-directive tools (Phase B).

``@poor-cli: <instruction>`` comments embedded in source files are surfaced
as pending agent directives. The agent checks them at turn start (preflight
hook in core_agent_loop), acts on them, and marks them consumed.

Phase B provides the read + write side from the backend. The Lua-side
watch_panel still exists as a read-only user view.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from poor_cli.tool_blocks import TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


# Pattern: ``// @poor-cli: <instruction>`` — supports //, #, and -- comment
# markers. The instruction runs to end-of-line.
_DIRECTIVE_RE = re.compile(
    r"""(?:^|\s)(?://|\#|--|;)\s*@poor-cli:\s*(?P<instruction>[^\n]+)"""
)

# Dedup key for "consumed" directives so the same comment isn't replayed
# across turns in the same session. Stored per-cwd in an in-memory set;
# persistence across sessions is a follow-up.
_CONSUMED: Dict[str, set] = {}


def _ctx_cwd(ctx: Any) -> str:
    return getattr(ctx, "cwd", None) or os.getcwd()


def _consumed_set(cwd: str) -> set:
    key = os.path.abspath(cwd)
    if key not in _CONSUMED:
        _CONSUMED[key] = set()
    return _CONSUMED[key]


async def _list_tracked_files(cwd: str) -> List[str]:
    """Prefer git ls-files; fall back to a walk of the cwd capped at 5k files
    so a huge non-git workspace doesn't melt."""
    if os.path.isdir(os.path.join(cwd, ".git")):
        def _sync():
            return subprocess.run(
                ["git", "ls-files"], cwd=cwd, capture_output=True, text=True, timeout=20.0
            )

        proc = await asyncio.get_running_loop().run_in_executor(None, _sync)
        if proc.returncode == 0:
            return [p for p in proc.stdout.splitlines() if p]
    paths: List[str] = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"node_modules"}]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), cwd)
            paths.append(rel)
            if len(paths) >= 5000:
                return paths
    return paths


def _scan_file(path: Path, rel: str) -> List[Dict[str, Any]]:
    try:
        text = path.read_text(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return []
    out: List[Dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _DIRECTIVE_RE.search(line)
        if m:
            out.append(
                {
                    "file": rel,
                    "line": lineno,
                    "instruction": m.group("instruction").strip(),
                }
            )
    return out


async def handle_directives_list(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    include_consumed = bool(args.get("include_consumed"))
    files = await _list_tracked_files(cwd)
    consumed = _consumed_set(cwd)
    items: List[Dict[str, Any]] = []
    for rel in files:
        full = Path(cwd) / rel
        if not full.is_file():
            continue
        for d in _scan_file(full, rel):
            key = f"{d['file']}:{d['line']}"
            d["consumed"] = key in consumed
            if include_consumed or not d["consumed"]:
                items.append(d)
    if not items:
        return ToolResult.text("no pending @poor-cli directives")
    rows = [
        [item["file"], str(item["line"]), "yes" if item["consumed"] else "no", item["instruction"]]
        for item in items
    ]
    return ToolResult(
        content=[
            TextBlock(text=f"{len(items)} directive(s)"),
            TableBlock(columns=["file", "line", "consumed", "instruction"], rows=rows),
        ],
        metadata={"directives": items},
    )


async def handle_directives_consume(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    file = str(args.get("file") or "")
    line = int(args.get("line") or 0)
    if not file or line <= 0:
        return ToolResult.error("file and line are required")
    _consumed_set(cwd).add(f"{file}:{line}")
    return ToolResult.text(f"directive {file}:{line} marked consumed")


async def handle_directives_clear(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    cwd = _ctx_cwd(ctx)
    _consumed_set(cwd).clear()
    return ToolResult.text("cleared consumed-directive memory")


register_tool(
    name="watch.directives.list",
    description=(
        "List all ``@poor-cli: <instruction>`` comments in tracked source "
        "files. By default only unconsumed directives are returned. Set "
        "``include_consumed=true`` to see everything."
    ),
    schema={
        "type": "object",
        "properties": {
            "include_consumed": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    handler=handle_directives_list,
    examples=[
        {
            "when": "at turn start — proactively act on pending user TODOs",
            "args": {},
            "result_summary": "list of file:line directives",
        }
    ],
)

register_tool(
    name="watch.directives.consume",
    description=(
        "Mark a specific directive (by file+line) as consumed so it's not "
        "re-surfaced on the next directives.list call. The physical comment "
        "stays — users remove it when they're satisfied with the result."
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
    handler=handle_directives_consume,
)

register_tool(
    name="watch.directives.clear",
    description="Clear the in-memory set of consumed directives for this workdir.",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_directives_clear,
)


def _reset() -> None:
    _CONSUMED.clear()
