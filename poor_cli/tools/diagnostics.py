"""Diagnostics tools (Phase B).

- ``diagnostics.emit``: the agent pushes findings into the Trouble pane under
  the poor-cli namespace so the user can browse them as a quickfix-like list.
- ``diagnostics.list``: intended for the agent to pull the user's current LSP
  diagnostics. Read round-trip is deferred (Phase C T10); the stub keeps the
  tool surface stable.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from poor_cli.tool_blocks import TextBlock, ToolResult
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
    await _notify(ctx, "integration.trouble.emit", {"items": cleaned})
    return ToolResult.text(f"emitted {len(cleaned)} diagnostic(s) to Trouble")


async def handle_clear(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    await _notify(ctx, "integration.trouble.clear", {})
    return ToolResult.text("cleared poor-cli diagnostics")


async def handle_list(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    # Requires a request/response round-trip to Lua. Deferred to Phase C T10.
    return ToolResult(
        content=[TextBlock(text="diagnostics.list is not yet implemented")],
        metadata={"not_implemented": True},
    )


register_tool(
    name="diagnostics.emit",
    description=(
        "Push agent-authored findings into the Trouble window under the "
        "poor-cli namespace. Use this to attach structured feedback to "
        "specific lines after reviewing a file."
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
    description="Clear all poor-cli-authored diagnostics from Trouble.",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_clear,
)

register_tool(
    name="diagnostics.list",
    description="Snapshot the user's current LSP diagnostics (not yet implemented).",
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
