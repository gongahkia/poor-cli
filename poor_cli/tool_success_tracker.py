"""CB3 adaptive per-tool-success tracker.

Persists a rolling per-tool success-rate cache so history pruning can
lower the prune-priority of reliable tools and raise it for flaky ones.

Storage: ``<base_dir>/tool_success_cache.json`` — a simple dict keyed by
tool name, with success/failure counters and a timestamp. Reasoning for
flat-file over SQLite: pruning reads this synchronously on every call; JSON
is cheap, atomic-replace-safe, and portable.

This layer is Ollama-for-CB3 — small, no new deps, opt-in via policy.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)

CACHE_FILENAME = "tool_success_cache.json"
DEFAULT_HALFLIFE_TURNS = 500  # decay old samples so early failures fade
PERSIST_EVERY_N_RECORDS = 25  # auto-persist after this many record() calls


@dataclass
class ToolStats:
    success: int = 0
    failure: int = 0
    last_updated: str = ""

    def rate(self) -> Optional[float]:
        total = self.success + self.failure
        if total == 0:
            return None
        return self.success / total

    def to_dict(self) -> dict:
        return {"success": self.success, "failure": self.failure, "last_updated": self.last_updated}

    @classmethod
    def from_dict(cls, data: dict) -> "ToolStats":
        return cls(
            success=int(data.get("success", 0) or 0),
            failure=int(data.get("failure", 0) or 0),
            last_updated=str(data.get("last_updated", "") or ""),
        )


class ToolSuccessTracker:
    """Thread-safe per-tool success/failure counter with atomic persist."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = Path(base_dir) if base_dir else Path.cwd() / ".poor-cli"
        self._path = self._base / CACHE_FILENAME
        self._stats: Dict[str, ToolStats] = {}
        self._lock = threading.Lock()
        self._loaded = False
        self._records_since_persist = 0

    def load(self) -> None:
        self._loaded = True
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("failed to load tool success cache: %s", exc)
            return
        if not isinstance(raw, dict):
            return
        with self._lock:
            for name, data in raw.items():
                if isinstance(data, dict):
                    self._stats[name] = ToolStats.from_dict(data)

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def record(self, tool_name: str, success: bool) -> None:
        """Increment success or failure for a tool. Auto-persists periodically."""
        self._ensure_loaded()
        name = tool_name.strip().lower()
        if not name:
            return
        with self._lock:
            stats = self._stats.setdefault(name, ToolStats())
            if success:
                stats.success += 1
            else:
                stats.failure += 1
            stats.last_updated = datetime.now(timezone.utc).isoformat()
            self._records_since_persist += 1
            should_flush = self._records_since_persist >= PERSIST_EVERY_N_RECORDS
        if should_flush:
            self.persist()
            self._records_since_persist = 0

    def rate_for(self, tool_name: str) -> Optional[float]:
        """Return success rate in [0, 1], or None when no data."""
        self._ensure_loaded()
        stats = self._stats.get(tool_name.strip().lower())
        return stats.rate() if stats else None

    def tool_weight_multiplier(self, tool_name: str, *, min_samples: int = 5) -> float:
        """Return a multiplier in [0.5, 1.5] for the pruner's tool weight.

        1.0 = neutral (use default tool weight).
        >1.0 = reliable tool, protect from pruning.
        <1.0 = flaky tool, prune more aggressively.

        Requires ``min_samples`` observations before deviating from 1.0.
        """
        self._ensure_loaded()
        stats = self._stats.get(tool_name.strip().lower())
        if stats is None:
            return 1.0
        total = stats.success + stats.failure
        if total < min_samples:
            return 1.0
        rate = stats.success / total
        # map [0, 1] → [0.5, 1.5] linearly
        return 0.5 + rate

    def persist(self) -> None:
        """Atomically write cache to disk."""
        self._ensure_loaded()
        self._base.mkdir(parents=True, exist_ok=True)
        payload = {name: stats.to_dict() for name, stats in self._stats.items()}
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self._base), suffix=".json.tmp")
            try:
                os.write(fd, json.dumps(payload, indent=None).encode("utf-8"))
                os.fsync(fd)
                os.close(fd)
                os.replace(tmp, str(self._path))
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as exc:
            logger.warning("failed to persist tool success cache: %s", exc)

    def snapshot(self) -> Dict[str, dict]:
        """Return a read-only view of the current cache."""
        self._ensure_loaded()
        return {name: stats.to_dict() for name, stats in self._stats.items()}


# ──────────────────────────────────────────────────────────────────────────
# Process-wide default tracker
# ──────────────────────────────────────────────────────────────────────────

_default_tracker: Optional[ToolSuccessTracker] = None
_default_tracker_lock = threading.Lock()


def get_default_tracker(base_dir: Optional[Path] = None) -> ToolSuccessTracker:
    """Return the lazily-constructed process-wide tracker.

    Used by the turn lifecycle (writer) and the history pruner (reader) so
    they share state without explicit plumbing through every constructor.
    Tests should construct their own ``ToolSuccessTracker(tmpdir)`` instances
    rather than touching this singleton.
    """
    global _default_tracker
    if _default_tracker is not None:
        return _default_tracker
    with _default_tracker_lock:
        if _default_tracker is None:
            _default_tracker = ToolSuccessTracker(base_dir)
    return _default_tracker


def reset_default_tracker() -> None:
    """Clear the singleton — for tests only."""
    global _default_tracker
    with _default_tracker_lock:
        _default_tracker = None
