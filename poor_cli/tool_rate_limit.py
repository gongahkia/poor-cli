"""Per-tool per-session fixed-window rate limiter for tool dispatch."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple


class ToolRateLimiter:
    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check_and_consume(
        self,
        tool: str,
        *,
        max_per_minute: int,
        now: Optional[float] = None,
    ) -> Tuple[bool, float]:
        current = time.monotonic() if now is None else float(now)
        cutoff = current - 60.0
        with self._lock:
            bucket = self._events.get(tool)
            if bucket is None:
                bucket = deque()
                self._events[tool] = bucket
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= max_per_minute:
                retry_after = max(0.0, 60.0 - (current - bucket[0]))
                return False, retry_after
            bucket.append(current)
            return True, 0.0

    def usage(
        self,
        tool: str,
        *,
        max_per_minute: int,
        now: Optional[float] = None,
    ) -> Dict[str, float]:
        current = time.monotonic() if now is None else float(now)
        cutoff = current - 60.0
        with self._lock:
            bucket = self._events.get(tool)
            if bucket is None:
                used = 0
                retry_after = 0.0
            else:
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                used = len(bucket)
                retry_after = 0.0
                if used >= max_per_minute:
                    retry_after = max(0.0, 60.0 - (current - bucket[0]))
        return {
            "used": float(used),
            "max": float(max_per_minute),
            "remaining": float(max(0, max_per_minute - used)),
            "retry_after_s": retry_after,
        }


def get_limiter(ctx: object, *, create: bool = False) -> Optional[ToolRateLimiter]:
    limiter = getattr(ctx, "tool_rate_limiter", None)
    if isinstance(limiter, ToolRateLimiter):
        return limiter
    if not create:
        return None
    limiter = ToolRateLimiter()
    setattr(ctx, "tool_rate_limiter", limiter)
    return limiter
