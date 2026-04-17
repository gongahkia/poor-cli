"""Per-session tool-call memoization (Proposal E.1).

The dispatcher consults a session-bound ``ToolCache`` before every tool
invocation. For pure tools (``cacheable=True``) with a cache hit inside
the TTL, the handler is skipped entirely and the previous ``ToolResult``
is returned verbatim with ``metadata.cache_hit = True``.

Philosophical bearings (PROPOSAL-E §1):

- **Agent-centric.** The cache is invisible to the agent except via the
  ``cache_hit`` flag in metadata — identical semantics to a fresh call,
  just cheaper. No new tool, no new verb. Agents that re-probe repo
  state get free answers.
- **Token-frugal.** Every cache hit is a saved handler invocation AND a
  saved round of tool-result tokens. The *raison d'être* of this module.
- **Correctness over savings.** Exclusive tools never cache (mutations
  should be observed, not cached). TTL defaults are conservative
  (60s). Explicit invalidation hooks wipe dependents after known
  mutations.

Scope: session-only, in-memory, LRU-bounded. No disk, no network. If the
session ends, the cache is gone.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from poor_cli.tool_blocks import ToolResult


@dataclass
class _Entry:
    result: ToolResult
    created_at: float
    hits: int = 0


def _hash_args(args: Dict[str, Any]) -> str:
    """Canonical JSON → sha256. ``sort_keys`` makes ``{a:1,b:2}`` and
    ``{b:2,a:1}`` collide on the same cache key. ``default=str`` handles
    datetimes / Paths / arbitrary objects without throwing on import of a
    weird tool."""
    blob = json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ToolCache:
    """Session-scoped memoization store. Thread-safe; one instance per
    chat session lives on ``ctx.tool_cache`` alongside ``session_recorder``."""

    def __init__(self, *, max_entries: int = 512) -> None:
        self._entries: "OrderedDict[str, _Entry]" = OrderedDict()
        self._max_entries = max(8, max_entries)
        self._lock = threading.Lock()
        self._hit_count = 0
        self._miss_count = 0

    def _key(self, tool: str, args: Dict[str, Any]) -> str:
        return f"{tool}:{_hash_args(args)}"

    def get(self, tool: str, args: Dict[str, Any], *, ttl_s: float) -> Optional[ToolResult]:
        """Return a cached result if present and within ``ttl_s`` of creation.
        Advances LRU on hit. Bumps the entry's ``hits`` counter."""
        key = self._key(tool, args)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._miss_count += 1
                return None
            if time.time() - entry.created_at > ttl_s:
                # Expired — evict and miss.
                del self._entries[key]
                self._miss_count += 1
                return None
            entry.hits += 1
            self._hit_count += 1
            # LRU touch
            self._entries.move_to_end(key)
            return entry.result

    def put(self, tool: str, args: Dict[str, Any], result: ToolResult) -> None:
        """Insert or replace a cache entry. Evicts oldest when cap reached."""
        key = self._key(tool, args)
        with self._lock:
            if key in self._entries:
                # Overwrite + move to end
                self._entries.move_to_end(key)
                self._entries[key] = _Entry(result=result, created_at=time.time())
                return
            self._entries[key] = _Entry(result=result, created_at=time.time())
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate_tool(self, tool: str) -> int:
        """Drop every cache entry for ``tool``. Returns the count dropped.
        Called by the dispatcher after a successful mutating tool run when
        that tool declared ``invalidates=[...]``."""
        prefix = f"{tool}:"
        with self._lock:
            doomed = [k for k in self._entries if k.startswith(prefix)]
            for k in doomed:
                del self._entries[k]
        return len(doomed)

    def invalidate_many(self, tools: Iterable[str]) -> int:
        total = 0
        for tool in tools:
            total += self.invalidate_tool(tool)
        return total

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._hit_count = 0
            self._miss_count = 0

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "max_entries": self._max_entries,
                "hits": self._hit_count,
                "misses": self._miss_count,
            }
