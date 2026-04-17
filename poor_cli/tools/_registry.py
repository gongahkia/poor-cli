"""Phase-B tool registry.

A minimal in-process registry that ``core_tool_dispatch`` queries to resolve
a tool name to its handler + schema + metadata. Kept separate from the legacy
``_tool_registry_builder.py`` which powers the (already-registered) core tools
like ``read_file`` and ``bash``. Phase-B tools live in their own tables so the
two systems can evolve independently during the migration.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from poor_cli.tool_blocks import ToolResult


ToolHandler = Callable[..., Awaitable[ToolResult]]

_IDEMPOTENCY_KEY_SCHEMA: Dict[str, Any] = {
    "type": "string",
    "pattern": "^[A-Za-z0-9_-]{8,64}$",
    "description": (
        "Optional deduplication key. Reuse across retries to prevent double execution."
    ),
}


def _ensure_exclusive_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(schema) if isinstance(schema, dict) else {}
    props = out.setdefault("properties", {})
    if isinstance(props, dict) and "idempotency_key" not in props:
        props["idempotency_key"] = deepcopy(_IDEMPOTENCY_KEY_SCHEMA)
    return out


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
    # Proposal E.1 — in-session memoization. Defaults off; must opt in.
    cacheable: bool = False
    cache_ttl_s: float = 60.0
    # Tool names whose cached results this tool's success should invalidate.
    # e.g. git.commit invalidates="git.status git.diff git.log hunks.list".
    invalidates: List[str] = field(default_factory=list)
    # Proposal E.2 — per-tool override for the result-size truncation
    # budget. None → dispatcher uses DEFAULT_MAX_RESULT_TOKENS (8000).
    # Raise it for tools that legitimately produce large structured output
    # the agent will consume wholesale (rare). Lower it for tools that
    # shouldn't balloon (chatty subprocess wrappers).
    max_result_tokens: Optional[int] = None
    # Proposal F.1 — per-tool circuit breaker tuning.
    circuit_threshold: int = 5
    circuit_window_s: float = 60.0
    circuit_cooldown_s: float = 30.0
    circuit_disabled: bool = False
    # Proposal F.3 — auto-checkpoint defaults.
    auto_checkpoint: bool = True
    auto_rollback: bool = False
    # Proposal F.4 — per-tool minute cap.
    max_per_minute: Optional[int] = None


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
    cacheable: bool = False,
    cache_ttl_s: float = 60.0,
    invalidates: Optional[List[str]] = None,
    max_result_tokens: Optional[int] = None,
    circuit_threshold: int = 5,
    circuit_window_s: float = 60.0,
    circuit_cooldown_s: float = 30.0,
    circuit_disabled: bool = False,
    auto_checkpoint: bool = True,
    auto_rollback: bool = False,
    max_per_minute: Optional[int] = None,
) -> ToolSpec:
    """Register a Phase-B tool. Called from each tool module at import time.

    Proposal E.1 fields:
      - ``cacheable``: allow the dispatcher to memoize results keyed on
        ``sha256(args)``. Default off; exclusive tools silently override
        to false regardless of the flag (mutations should never cache).
      - ``cache_ttl_s``: entries live at most this long. Default 60s.
      - ``invalidates``: on *successful* dispatch of this tool, wipe cache
        entries for every listed tool name. Use for mutations whose
        observable effect changes the output of pure read tools (e.g.
        ``git.commit`` → [``git.status``, ``git.log``]).
    """
    if exclusive and cacheable:
        # Forced invariant: exclusive tools never cache. Silently downgrade
        # rather than raise so a future tool author's typo doesn't crash
        # registration during import.
        cacheable = False
    if exclusive:
        schema = _ensure_exclusive_schema(schema)
    spec = ToolSpec(
        name=name,
        description=description,
        schema=schema,
        handler=handler,
        timeout_s=timeout_s,
        exclusive=exclusive,
        examples=list(examples or []),
        degraded_fallbacks=list(degraded_fallbacks or []),
        cacheable=cacheable,
        cache_ttl_s=cache_ttl_s,
        invalidates=list(invalidates or []),
        max_result_tokens=max_result_tokens,
        circuit_threshold=max(1, int(circuit_threshold)),
        circuit_window_s=max(1.0, float(circuit_window_s)),
        circuit_cooldown_s=max(0.1, float(circuit_cooldown_s)),
        circuit_disabled=bool(circuit_disabled),
        auto_checkpoint=bool(auto_checkpoint),
        auto_rollback=bool(auto_rollback),
        max_per_minute=(None if max_per_minute is None else max(1, int(max_per_minute))),
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
