"""Phase-B tool registry.

A minimal in-process registry that ``core_tool_dispatch`` queries to resolve
a tool name to its handler + schema + metadata. Kept separate from the legacy
``_tool_registry_builder.py`` which powers the (already-registered) core tools
like ``read_file`` and ``bash``. Phase-B tools live in their own tables so the
two systems can evolve independently during the migration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from poor_cli.tool_blocks import ToolResult


ToolHandler = Callable[..., Awaitable[ToolResult]]


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: Dict[str, Any]
    handler: ToolHandler
    timeout_s: float = 30.0
    exclusive: bool = False
    examples: List[Dict[str, Any]] = field(default_factory=list)
    degraded_fallbacks: List[str] = field(default_factory=list)


_TOOLS: Dict[str, ToolSpec] = {}


def register_tool(
    name: str,
    *,
    description: str,
    schema: Dict[str, Any],
    handler: ToolHandler,
    timeout_s: float = 30.0,
    exclusive: bool = False,
    examples: Optional[List[Dict[str, Any]]] = None,
    degraded_fallbacks: Optional[List[str]] = None,
) -> ToolSpec:
    """Register a Phase-B tool. Called from each tool module at import time."""
    spec = ToolSpec(
        name=name,
        description=description,
        schema=schema,
        handler=handler,
        timeout_s=timeout_s,
        exclusive=exclusive,
        examples=list(examples or []),
        degraded_fallbacks=list(degraded_fallbacks or []),
    )
    _TOOLS[name] = spec
    return spec


def get(name: str) -> Optional[ToolSpec]:
    return _TOOLS.get(name)


def all_tools() -> Dict[str, ToolSpec]:
    return dict(_TOOLS)


def tool_names() -> List[str]:
    return sorted(_TOOLS.keys())


async def dispatch(name: str, args: Dict[str, Any], ctx: Any) -> ToolResult:
    """Dispatch a tool call. Used by tests and by a future integration point
    in ``core_tool_dispatch``. Not the production path during the Phase B
    migration — the core dispatcher picks these up via ``tool_names()``.
    """
    spec = _TOOLS.get(name)
    if spec is None:
        return ToolResult.error(f"unknown tool: {name}", unknown_tool=True)
    try:
        coro = spec.handler(ctx=ctx, args=args)
        return await asyncio.wait_for(coro, timeout=spec.timeout_s)
    except asyncio.TimeoutError:
        return ToolResult.error(
            f"tool {name!r} timed out after {spec.timeout_s}s", timeout=True
        )


def reset() -> None:
    """Test hook. Clears the registry so per-test registrations don't leak."""
    _TOOLS.clear()
