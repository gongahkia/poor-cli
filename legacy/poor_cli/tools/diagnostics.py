"""Diagnostics tools.

- ``diagnostics.emit``: the agent records structured findings for files/lines.
- ``diagnostics.list``: returns findings recorded during this session.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from poor_cli.tool_blocks import TableBlock, ToolResult
from poor_cli.tools._registry import register_tool


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


async def handle_emit(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    items = args.get("items") or []
    if not isinstance(items, list):
        return ToolResult.error("items must be a list")
    cleaned: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file = str(item.get("file") or "")
        if not file:
            continue
        cleaned.append(
            {
                "file": file,
                "line": int(item.get("line") or 1),
                "col": int(item.get("col") or 0),
                "end_line": item.get("end_line"),
                "end_col": item.get("end_col"),
                "severity": str(item.get("severity") or "info"),
                "message": str(item.get("message") or ""),
            }
        )
    if not cleaned:
        return ToolResult.error("no valid items (need file + message)")
    existing = getattr(ctx, "diagnostics", None)
    if not isinstance(existing, list):
        existing = []
        try:
            setattr(ctx, "diagnostics", existing)
        except Exception:
            pass
    existing.extend(cleaned)
    await _notify(ctx, "integration.diagnostics.emit", {"items": cleaned})
    return ToolResult.text(f"recorded {len(cleaned)} diagnostic(s)")


async def handle_clear(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    existing = getattr(ctx, "diagnostics", None)
    if isinstance(existing, list):
        existing.clear()
    await _notify(ctx, "integration.diagnostics.clear", {})
    return ToolResult.text("cleared poor-cli diagnostics")


async def handle_list(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    items = list(getattr(ctx, "diagnostics", []) or [])
    rows = [
        [
            str(item.get("severity") or "info"),
            str(item.get("file") or ""),
            str(item.get("line") or 1),
            str(item.get("message") or ""),
        ]
        for item in items
        if isinstance(item, dict)
    ]
    if not rows:
        return ToolResult.text("no diagnostics recorded", diagnostics=[])
    return ToolResult(
        content=[TableBlock(columns=["severity", "file", "line", "message"], rows=rows)],
        metadata={"diagnostics": items},
    )


register_tool(
    name="diagnostics.emit",
    description=(
        "Record agent-authored findings for specific files and lines after "
        "reviewing code."
    ),
    schema={
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["file", "message"],
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": "integer", "minimum": 1, "default": 1},
                        "col": {"type": "integer", "minimum": 0, "default": 0},
                        "end_line": {"type": "integer", "minimum": 1},
                        "end_col": {"type": "integer", "minimum": 0},
                        "severity": {
                            "type": "string",
                            "enum": ["error", "warn", "warning", "info", "hint"],
                            "default": "info",
                        },
                        "message": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            }
        },
        "additionalProperties": False,
    },
    handler=handle_emit,
)

register_tool(
    name="diagnostics.clear",
    description="Clear all poor-cli-authored diagnostics.",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_clear,
)

register_tool(
    name="diagnostics.list",
    description="List diagnostics recorded in the current harness session.",
    schema={
        "type": "object",
        "properties": {
            "buffer": {"type": "string"},
            "severity": {"type": "string"},
        },
        "additionalProperties": False,
    },
    handler=handle_list,
)
