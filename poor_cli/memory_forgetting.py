"""MH3 forgetting policy with cascading deletes.

Per-type soft-TTL defaults, access-recency boost, provenance-aware cascade
delete, archive-not-delete recovery path. All config-driven; user can override
any TTL. Archive target: ``<memory_dir>/archive/<YYYY>-<MM>/<filename>``.

Forgetting layers cleanly over MH1 provenance and MH8 telemetry. Without those,
this module falls back to ``updated_at`` and skips recency boost.

Public surface:
- ``DEFAULT_TTL_DAYS`` — {type: days}; 0 means never expires.
- ``ForgettingPolicy(ttl_days, recency_boost_days, archive_dir)``.
- ``MemoryForgetter(manager, policy)``.
    - ``.due_for_expiry(now=None) -> List[MemoryEntry]``
    - ``.archive(entry) -> Path`` (moves to archive subdir)
    - ``.purge_source(session_id, dry_run=False) -> List[MemoryEntry]``
    - ``.run_expiry_pass(dry_run=False) -> dict`` (summary)

Never archives if archive dir cannot be created; logs + returns ``None``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .exceptions import setup_logger
from .memory import MemoryEntry, MemoryManager

logger = setup_logger(__name__)

DEFAULT_TTL_DAYS: Dict[str, int] = {
    "feedback": 0,     # never expires — user preferences are durable
    "user": 365,
    "project": 180,
    "reference": 90,
}
DEFAULT_RECENCY_BOOST_DAYS = 60  # a recent hit resets TTL clock


@dataclass
class ForgettingPolicy:
    ttl_days: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_TTL_DAYS))
    recency_boost_days: int = DEFAULT_RECENCY_BOOST_DAYS
    archive_dirname: str = "archive"
    min_hits_for_boost: int = 1

    def effective_ttl_days(self, mem_type: str) -> int:
        """Return configured TTL (days) for a memory type, 0 = never."""
        return max(0, int(self.ttl_days.get(mem_type, 0)))


@dataclass
class ExpirySummary:
    archived: List[str] = field(default_factory=list)
    skipped_no_ttl: int = 0
    skipped_recent_hit: int = 0
    cascade_deleted: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "archived": list(self.archived),
            "skippedNoTtl": self.skipped_no_ttl,
            "skippedRecentHit": self.skipped_recent_hit,
            "cascadeDeleted": list(self.cascade_deleted),
        }


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


class MemoryForgetter:
    """Run forgetting policy over a MemoryManager."""

    def __init__(self, manager: MemoryManager, policy: Optional[ForgettingPolicy] = None):
        self._manager = manager
        self._policy = policy or ForgettingPolicy()

    @property
    def policy(self) -> ForgettingPolicy:
        return self._policy

    @property
    def archive_dir(self) -> Path:
        return self._manager._memory_dir / self._policy.archive_dirname  # type: ignore[reportPrivateUsage]

    def due_for_expiry(self, now: Optional[datetime] = None) -> List[MemoryEntry]:
        """Return entries past their effective TTL (with recency boost applied)."""
        now = now or datetime.now(timezone.utc)
        if not self._manager._entries:  # type: ignore[reportPrivateUsage]
            self._manager.load()
        stale: List[MemoryEntry] = []
        for entry in self._manager._entries.values():  # type: ignore[reportPrivateUsage]
            ttl_days = self._policy.effective_ttl_days(entry.type)
            if ttl_days <= 0:
                continue
            # recency boost: a hit in the last recency_boost_days resets the clock
            last_access = _parse_iso(entry.last_accessed_at) or _parse_iso(entry.updated_at) or _parse_iso(entry.created_at)
            if last_access is None:
                continue
            age = now - last_access
            if entry.hit_count >= self._policy.min_hits_for_boost:
                # eligible for boost: use extended TTL
                effective = timedelta(days=ttl_days + self._policy.recency_boost_days)
            else:
                effective = timedelta(days=ttl_days)
            if age > effective:
                stale.append(entry)
        return stale

    def archive(self, entry: MemoryEntry) -> Optional[Path]:
        """Move entry to archive/<YYYY>-<MM>/ preserving frontmatter. No-op on error."""
        now = datetime.now(timezone.utc)
        target_dir = self.archive_dir / f"{now.year:04d}-{now.month:02d}"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("failed to create archive dir %s: %s", target_dir, exc)
            return None
        src = self._manager._memory_dir / entry.filename  # type: ignore[reportPrivateUsage]
        dst = target_dir / entry.filename
        try:
            if src.exists():
                shutil.move(str(src), str(dst))
            else:
                # write a fresh rendered copy if src vanished
                dst.write_text(entry.render_file(), encoding="utf-8")
        except Exception as exc:
            logger.warning("failed to archive %s: %s", entry.filename, exc)
            return None
        # remove from live index + rebuild
        self._manager._entries.pop(entry.filename, None)  # type: ignore[reportPrivateUsage]
        self._manager._rebuild_index()  # type: ignore[reportPrivateUsage]
        logger.info("archived memory %s -> %s", entry.filename, dst)
        return dst

    def purge_source(self, session_id: str, *, dry_run: bool = False) -> List[MemoryEntry]:
        """Cascade-archive memories whose ONLY source is the given session.

        Entries with ``source_session_id == session_id`` are the cascade set.
        Archival (not delete) keeps the recovery path cheap.
        """
        if not self._manager._entries:  # type: ignore[reportPrivateUsage]
            self._manager.load()
        targets = [
            e for e in self._manager._entries.values()  # type: ignore[reportPrivateUsage]
            if e.source_session_id == session_id
        ]
        if dry_run:
            return targets
        archived: List[MemoryEntry] = []
        for entry in targets:
            if self.archive(entry) is not None:
                archived.append(entry)
        return archived

    def run_expiry_pass(self, *, dry_run: bool = False) -> ExpirySummary:
        """Evaluate all memories, archive those past TTL. Returns summary."""
        summary = ExpirySummary()
        stale = self.due_for_expiry()
        if dry_run:
            summary.archived = [e.filename for e in stale]
            return summary
        for entry in stale:
            if self.archive(entry) is not None:
                summary.archived.append(entry.filename)
        return summary
