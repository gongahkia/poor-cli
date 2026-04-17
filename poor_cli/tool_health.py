"""Per-tool health tracker (T9).

Records every ``CallRecord`` the dispatcher produces and answers queries
like "what's the success rate of git.push in the last hour?" or
"what's the p95 latency of fs.browse?". Backs the Diagnostics panel's
tool-health drill section and the ``poor-cli/toolHealth`` RPC.

In-process storage — a per-session dict of ring buffers. Doesn't persist
across restarts; the assumption is health signal is most useful for the
current session's troubleshooting.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from poor_cli.tool_dispatcher import CallRecord


@dataclass
class _ToolStats:
    """Per-tool running window."""
    name: str
    successes: int = 0
    failures: int = 0
    latencies_ms: Deque[int] = field(default_factory=lambda: deque(maxlen=512))
    recent_errors: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=5))
    events: Deque[float] = field(default_factory=lambda: deque(maxlen=1024))  # timestamps

    def record(self, rec: CallRecord, *, error_excerpt: Optional[str] = None) -> None:
        self.events.append(time.time())
        self.latencies_ms.append(rec.wall_time_ms)
        if rec.is_error:
            self.failures += 1
            self.recent_errors.append(
                {
                    "at": time.time(),
                    "retry_attempts": rec.retry_attempts,
                    "timeout": rec.timeout,
                    "excerpt": error_excerpt or "",
                }
            )
        else:
            self.successes += 1


class ToolHealth:
    """Thread-safe per-tool health store. Tests and consumers treat it as
    a bag of stats keyed by tool name."""

    def __init__(self) -> None:
        self._tools: Dict[str, _ToolStats] = {}
        self._lock = threading.Lock()

    def record(self, rec: CallRecord, *, error_excerpt: Optional[str] = None) -> None:
        with self._lock:
            stats = self._tools.get(rec.tool)
            if stats is None:
                stats = _ToolStats(name=rec.tool)
                self._tools[rec.tool] = stats
            stats.record(rec, error_excerpt=error_excerpt)

    def tool_names(self) -> List[str]:
        with self._lock:
            return sorted(self._tools.keys())

    def snapshot(self, name: str, *, window_s: float = 3600.0) -> Optional[Dict[str, Any]]:
        """Return a dict snapshot for one tool, or None if unknown."""
        with self._lock:
            stats = self._tools.get(name)
            if stats is None:
                return None
            return _build_snapshot(stats, window_s=window_s)

    def snapshots(self, *, window_s: float = 3600.0) -> List[Dict[str, Any]]:
        """Return snapshots for every known tool. Used by the diag panel."""
        with self._lock:
            return [_build_snapshot(s, window_s=window_s) for s in self._tools.values()]

    def reset(self) -> None:
        with self._lock:
            self._tools.clear()


def _build_snapshot(stats: _ToolStats, *, window_s: float) -> Dict[str, Any]:
    now = time.time()
    cutoff = now - window_s
    # Events limited to the window for rate calculations.
    in_window = [t for t in stats.events if t >= cutoff]
    # Latencies are unwindowed (they're per-call, bounded by the deque size).
    latencies = sorted(stats.latencies_ms)
    total = stats.successes + stats.failures
    success_rate = stats.successes / total if total else None
    # Windowed success rate: recompute from recent_errors + event count.
    window_errors = [e for e in stats.recent_errors if e["at"] >= cutoff]
    window_total = len(in_window)
    window_success_rate = (
        (window_total - len(window_errors)) / window_total if window_total else None
    )
    return {
        "name": stats.name,
        "total": total,
        "successes": stats.successes,
        "failures": stats.failures,
        "success_rate": success_rate,
        "window_s": window_s,
        "window_total": window_total,
        "window_success_rate": window_success_rate,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "recent_errors": list(stats.recent_errors),
    }


def _percentile(sorted_values: List[int], pct: int) -> Optional[int]:
    if not sorted_values:
        return None
    idx = max(0, min(len(sorted_values) - 1, int(round((pct / 100) * (len(sorted_values) - 1)))))
    return sorted_values[idx]


# Module-level singleton. Session code can replace with its own instance
# during tests; ``reset()`` wipes the default singleton in between runs.
_SINGLETON = ToolHealth()


def record(rec: CallRecord, *, error_excerpt: Optional[str] = None) -> None:
    """Record a CallRecord into the process-wide health store."""
    _SINGLETON.record(rec, error_excerpt=error_excerpt)


def snapshot(name: str, *, window_s: float = 3600.0) -> Optional[Dict[str, Any]]:
    return _SINGLETON.snapshot(name, window_s=window_s)


def snapshots(*, window_s: float = 3600.0) -> List[Dict[str, Any]]:
    return _SINGLETON.snapshots(window_s=window_s)


def reset() -> None:
    _SINGLETON.reset()
