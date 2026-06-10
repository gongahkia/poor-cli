"""Debug tools exposed to the agent harness.

Write-side tools notify an attached debug bridge when one exists. In plain CLI
sessions no bridge is assumed, so the tool returns an explicit unavailable
result instead of pretending a breakpoint was installed.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from poor_cli.tool_blocks import ToolResult
from poor_cli.tools._registry import register_tool


def _has_debug_bridge(ctx: Any) -> bool:
    fn = getattr(ctx, "has_plugin", None)
    return bool(callable(fn) and fn("debug"))


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


async def _request(ctx: Any, method: str, params: Dict[str, Any]) -> Any:
    fn = getattr(ctx, "request_client", None)
    if fn is None:
        return None
    result = fn(method, params)
    if asyncio.iscoroutine(result):
        return await result
    return result


async def handle_set_breakpoint(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_debug_bridge(ctx):
        return ToolResult.error(
            "debug bridge is not available in this session",
            degraded="unavailable",
        )
    file = str(args.get("file") or "")
    line = int(args.get("line") or 0)
    if not file or line <= 0:
        return ToolResult.error("file and line (≥1) are required")
    payload: Dict[str, Any] = {"file": file, "line": line}
    if args.get("condition"):
        payload["condition"] = str(args["condition"])
    await _notify(ctx, "integration.debug.setBreakpoint", payload)
    return ToolResult.text(f"breakpoint set at {file}:{line}")


async def handle_clear_breakpoint(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_debug_bridge(ctx):
        return ToolResult.error("debug bridge is not available")
    file = str(args.get("file") or "")
    line = int(args.get("line") or 0)
    if not file or line <= 0:
        return ToolResult.error("file and line are required")
    await _notify(ctx, "integration.debug.clearBreakpoint", {"file": file, "line": line})
    return ToolResult.text(f"breakpoint cleared at {file}:{line}")


async def handle_step(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_debug_bridge(ctx):
        return ToolResult.error("debug bridge is not available")
    direction = str(args.get("direction") or "over").lower()
    if direction not in {"over", "in", "out"}:
        return ToolResult.error("direction must be one of: over, in, out")
    await _notify(ctx, "integration.debug.step", {"direction": direction})
    return ToolResult.text(f"step {direction}")


async def handle_continue(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_debug_bridge(ctx):
        return ToolResult.error("debug bridge is not available")
    await _notify(ctx, "integration.debug.continue", {})
    return ToolResult.text("continued")


async def handle_stack(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_debug_bridge(ctx):
        return ToolResult.error("debug bridge is not available")
    result = await _request(ctx, "integration.debug.stack", {})
    if result is None:
        return ToolResult.error("debug bridge does not support stack requests")
    return ToolResult.text(_format_debug_payload(result), payload=result)


async def handle_eval(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_debug_bridge(ctx):
        return ToolResult.error("debug bridge is not available")
    expr = str(args.get("expression") or "")
    if not expr:
        return ToolResult.error("expression is required")
    result = await _request(ctx, "integration.debug.eval", {"expression": expr})
    if result is None:
        return ToolResult.error("debug bridge does not support eval requests")
    return ToolResult.text(_format_debug_payload(result), payload=result)


def _format_debug_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict) and "text" in payload:
        return str(payload["text"])
    return repr(payload)


register_tool(
    name="debug.breakpoint.set",
    description="Set a breakpoint at file:line through an attached debug bridge. Optional condition.",
    schema={
        "type": "object",
        "required": ["file", "line"],
        "properties": {
            "file": {"type": "string"},
            "line": {"type": "integer", "minimum": 1},
            "condition": {"type": "string"},
        },
        "additionalProperties": False,
    },
    handler=handle_set_breakpoint,
)

register_tool(
    name="debug.breakpoint.clear",
    description="Clear a breakpoint at file:line through an attached debug bridge.",
    schema={
        "type": "object",
        "required": ["file", "line"],
        "properties": {
            "file": {"type": "string"},
            "line": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    },
    handler=handle_clear_breakpoint,
)

register_tool(
    name="debug.step",
    description="Single-step the debugger. direction=over|in|out (default: over).",
    schema={
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["over", "in", "out"]}
        },
        "additionalProperties": False,
    },
    handler=handle_step,
    exclusive=True,
)

register_tool(
    name="debug.continue",
    description="Continue execution to the next breakpoint.",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_continue,
    exclusive=True,
)

register_tool(
    name="debug.stack",
    description="Return current debug stack frames through an attached request/response debug bridge.",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_stack,
)

register_tool(
    name="debug.eval",
    description="Evaluate an expression in the active frame through an attached request/response debug bridge.",
    schema={
        "type": "object",
        "required": ["expression"],
        "properties": {"expression": {"type": "string"}},
        "additionalProperties": False,
    },
    handler=handle_eval,
)
