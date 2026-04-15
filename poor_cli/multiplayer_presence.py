"""Typing presence tracking for multiplayer rooms."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass
class _PresenceEntry:
    last_keystroke_at: float
    typing: bool = False
    last_broadcast_at: Optional[float] = None
    last_broadcast_typing: Optional[bool] = None
    pending_typing: Optional[bool] = None


class PresenceTracker:
    def __init__(
        self,
        *,
        debounce_ms: int,
        broadcast_interval_ms: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.debounce_s = max(0, debounce_ms) / 1000.0
        self.broadcast_interval_s = max(0, broadcast_interval_ms) / 1000.0
        self._clock = clock
        self._entries: Dict[str, _PresenceEntry] = {}

    def mark_typing(self, connection_id: str) -> bool:
        now = self._clock()
        entry = self._entries.get(connection_id)
        if entry is None:
            entry = _PresenceEntry(last_keystroke_at=now)
            self._entries[connection_id] = entry
        entry.last_keystroke_at = now
        if entry.typing:
            return False
        entry.typing = True
        return self._queue_or_broadcast(entry, True, now)

    def mark_idle(self, connection_id: str) -> bool:
        now = self._clock()
        entry = self._entries.get(connection_id)
        if entry is None or not entry.typing:
            return False
        entry.typing = False
        return self._queue_or_broadcast(entry, False, now)

    def remove(self, connection_id: str) -> bool:
        entry = self._entries.pop(connection_id, None)
        if entry is None:
            return False
        return entry.last_broadcast_typing is True or entry.pending_typing is True

    def sweep(self) -> Dict[str, bool]:
        now = self._clock()
        broadcasts: Dict[str, bool] = {}
        for connection_id, entry in list(self._entries.items()):
            if entry.typing and now - entry.last_keystroke_at >= self.debounce_s:
                entry.typing = False
                if self._queue_or_broadcast(entry, False, now):
                    broadcasts[connection_id] = False
            if (
                connection_id not in broadcasts
                and entry.pending_typing is not None
                and self._can_broadcast(entry, now)
            ):
                typing = entry.pending_typing
                entry.pending_typing = None
                entry.last_broadcast_at = now
                entry.last_broadcast_typing = typing
                broadcasts[connection_id] = typing
        return broadcasts

    def snapshot(self) -> dict[str, bool]:
        return {
            connection_id: entry.typing
            for connection_id, entry in self._entries.items()
        }

    def _queue_or_broadcast(
        self,
        entry: _PresenceEntry,
        typing: bool,
        now: float,
    ) -> bool:
        if self._can_broadcast(entry, now):
            entry.last_broadcast_at = now
            entry.last_broadcast_typing = typing
            entry.pending_typing = None
            return True
        if entry.last_broadcast_typing == typing:
            entry.pending_typing = None
            return False
        entry.pending_typing = typing
        return False

    def _can_broadcast(self, entry: _PresenceEntry, now: float) -> bool:
        if entry.last_broadcast_at is None:
            return True
        return now - entry.last_broadcast_at >= self.broadcast_interval_s
