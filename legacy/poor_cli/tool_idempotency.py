"""Session-scoped idempotency store for mutating tool calls."""

from __future__ import annotations

from copy import deepcopy
import threading
from typing import Dict, Optional, Tuple

from poor_cli.tool_blocks import ToolResult


class IdempotencyStore:
    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, str], ToolResult] = {}
        self._lock = threading.Lock()

    def get(self, tool: str, key: str) -> Optional[ToolResult]:
        with self._lock:
            result = self._entries.get((tool, key))
            return deepcopy(result) if result is not None else None

    def put(self, tool: str, key: str, result: ToolResult) -> None:
        with self._lock:
            self._entries[(tool, key)] = deepcopy(result)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def get_store(ctx: object, *, create: bool = False) -> Optional[IdempotencyStore]:
    store = getattr(ctx, "tool_idempotency_store", None)
    if isinstance(store, IdempotencyStore):
        return store
    if not create:
        return None
    store = IdempotencyStore()
    setattr(ctx, "tool_idempotency_store", store)
    return store
