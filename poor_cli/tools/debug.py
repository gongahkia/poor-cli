"""Debug tools (Phase B). Drive nvim-dap via the DAP bridge.

Every write tool sends an RPC notification into the Lua bridge. Read tools
aren't yet wired because poor-cli doesn't currently request DAP state; the
agent infers runtime state from log + user narration. Read-tool stubs exist
so the surface is stable — they return a clear "not yet implemented"
ToolResult rather than failing silently.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from poor_cli.tool_blocks import TextBlock, ToolResult
from poor_cli.tools._registry import register_tool


def _has_dap(ctx: Any) -> bool:
    fn = getattr(ctx, "has_plugin", None)
    return bool(callable(fn) and fn("dap"))


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


async def handle_set_breakpoint(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_dap(ctx):
        return ToolResult.error(
            "nvim-dap is not available in this session",
            degraded="unavailable",
        )
    file = str(args.get("file") or "")
    line = int(args.get("line") or 0)
    if not file or line <= 0:
        return ToolResult.error("file and line (≥1) are required")
    payload: Dict[str, Any] = {"file": file, "line": line}
    if args.get("condition"):
        payload["condition"] = str(args["condition"])
    await _notify(ctx, "integration.dap.setBreakpoint", payload)
    return ToolResult.text(f"breakpoint set at {file}:{line}")


async def handle_clear_breakpoint(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_dap(ctx):
        return ToolResult.error("nvim-dap is not available")
    file = str(args.get("file") or "")
    line = int(args.get("line") or 0)
    if not file or line <= 0:
        return ToolResult.error("file and line are required")
    await _notify(ctx, "integration.dap.clearBreakpoint", {"file": file, "line": line})
    return ToolResult.text(f"breakpoint cleared at {file}:{line}")


async def handle_step(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_dap(ctx):
        return ToolResult.error("nvim-dap is not available")
    direction = str(args.get("direction") or "over").lower()
    if direction not in {"over", "in", "out"}:
        return ToolResult.error("direction must be one of: over, in, out")
    await _notify(ctx, "integration.dap.step", {"direction": direction})
    return ToolResult.text(f"step {direction}")


async def handle_continue(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    if not _has_dap(ctx):
        return ToolResult.error("nvim-dap is not available")
    await _notify(ctx, "integration.dap.continue", {})
    return ToolResult.text("continued")


async def handle_stack(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    # The read-side of DAP needs a request (not notification) round-trip;
    # that's Phase C T10 territory. Stub for now.
    return ToolResult(
        content=[TextBlock(text="debug.stack is not yet implemented")],
        metadata={"not_implemented": True},
    )


async def handle_eval(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    expr = str(args.get("expression") or "")
    if not expr:
        return ToolResult.error("expression is required")
    return ToolResult(
        content=[TextBlock(text=f"debug.eval({expr!r}) is not yet implemented")],
        metadata={"not_implemented": True},
    )


register_tool(
    name="debug.breakpoint.set",
    description="Set a breakpoint at file:line via nvim-dap. Optional condition.",
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
    description="Clear a breakpoint at file:line via nvim-dap.",
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
    description="Return the current DAP stack frames (not yet implemented).",
    schema={"type": "object", "properties": {}, "additionalProperties": False},
    handler=handle_stack,
)

register_tool(
    name="debug.eval",
    description="Evaluate an expression in the active frame (not yet implemented).",
    schema={
        "type": "object",
        "required": ["expression"],
        "properties": {"expression": {"type": "string"}},
        "additionalProperties": False,
    },
    handler=handle_eval,
)
