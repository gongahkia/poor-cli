"""Tests for MH3 memory forgetting policy + cascading deletes."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from poor_cli.memory import MemoryEntry, MemoryManager
from poor_cli.memory_forgetting import (
    DEFAULT_TTL_DAYS,
    ForgettingPolicy,
    MemoryForgetter,
)


def _old_ts(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class ForgettingPolicyTests(unittest.TestCase):
    def test_feedback_never_expires(self):
        policy = ForgettingPolicy()
        self.assertEqual(policy.effective_ttl_days("feedback"), 0)

    def test_default_ttls_reasonable(self):
        self.assertEqual(DEFAULT_TTL_DAYS["user"], 365)
        self.assertEqual(DEFAULT_TTL_DAYS["project"], 180)
        self.assertEqual(DEFAULT_TTL_DAYS["reference"], 90)
        self.assertEqual(DEFAULT_TTL_DAYS["feedback"], 0)


class MemoryForgetterTests(unittest.TestCase):
    def _mgr(self, tmp: Path) -> MemoryManager:
        return MemoryManager(tmp / ".poor-cli")

    def test_due_for_expiry_returns_old_untouched_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            # reference TTL = 90d; this one is 200d old and never accessed
            e = MemoryEntry(
                name="old ref", description="d", type="reference",
                content="x",
                created_at=_old_ts(200), updated_at=_old_ts(200),
                last_accessed_at=_old_ts(200),
            )
            mgr.save(e)
            stale = MemoryForgetter(mgr).due_for_expiry()
            self.assertEqual(len(stale), 1)
            self.assertEqual(stale[0].name, "old ref")

    def test_feedback_never_returned_as_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            e = MemoryEntry(
                name="feedback old", description="d", type="feedback",
                content="x",
                created_at=_old_ts(2000), updated_at=_old_ts(2000),
                last_accessed_at=_old_ts(2000),
            )
            mgr.save(e)
            self.assertEqual(MemoryForgetter(mgr).due_for_expiry(), [])

    def test_recency_hit_boosts_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            # 200d since creation but recently accessed with a hit count
            e = MemoryEntry(
                name="recent ref", description="d", type="reference",
                content="x",
                created_at=_old_ts(200), updated_at=_old_ts(200),
                last_accessed_at=_old_ts(10),
                hit_count=3,
            )
            mgr.save(e)
            # default TTL 90d + boost 60d = 150d; accessed 10d ago → safe
            stale = MemoryForgetter(mgr).due_for_expiry()
            self.assertEqual(stale, [])

    def test_archive_moves_file_under_archive_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            e = MemoryEntry(name="to archive", description="d", type="reference", content="x")
            mgr.save(e)
            live_path = mgr._memory_dir / e.filename
            self.assertTrue(live_path.exists())
            dst = MemoryForgetter(mgr).archive(e)
            self.assertIsNotNone(dst)
            self.assertTrue(dst.exists())
            self.assertFalse(live_path.exists())
            # removed from manager's live index
            self.assertIsNone(mgr.get(e.name, record_hit=False))

    def test_purge_source_cascade_archives_by_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            mgr.save(MemoryEntry(name="a", description="d", type="project", content="x", source_session_id="sess-1"))
            mgr.save(MemoryEntry(name="b", description="d", type="project", content="x", source_session_id="sess-1"))
            mgr.save(MemoryEntry(name="c", description="d", type="project", content="x", source_session_id="sess-2"))

            forgetter = MemoryForgetter(mgr)
            dry = forgetter.purge_source("sess-1", dry_run=True)
            self.assertEqual({e.name for e in dry}, {"a", "b"})

            archived = forgetter.purge_source("sess-1", dry_run=False)
            self.assertEqual({e.name for e in archived}, {"a", "b"})
            # c unaffected
            self.assertIsNotNone(mgr.get("c", record_hit=False))

    def test_run_expiry_pass_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            # stale
            mgr.save(MemoryEntry(
                name="stale", description="d", type="reference", content="x",
                created_at=_old_ts(200), updated_at=_old_ts(200),
                last_accessed_at=_old_ts(200),
            ))
            # fresh
            mgr.save(MemoryEntry(
                name="fresh", description="d", type="reference", content="x",
                created_at=_old_ts(10), updated_at=_old_ts(10),
                last_accessed_at=_old_ts(10),
            ))

            summary = MemoryForgetter(mgr).run_expiry_pass()
            self.assertEqual(len(summary.archived), 1)
            # fresh survives
            self.assertIsNotNone(mgr.get("fresh", record_hit=False))


if __name__ == "__main__":
    unittest.main()
