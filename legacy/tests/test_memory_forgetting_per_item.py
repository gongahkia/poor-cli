"""MH3-UX: per-item include_filenames filter on run_expiry_pass."""
from __future__ import annotations
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from poor_cli.memory import MemoryEntry, MemoryManager
from poor_cli.memory_forgetting import MemoryForgetter


def _old(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class PerItemExpiryTests(unittest.TestCase):
    def _mgr(self, tmp: Path) -> MemoryManager:
        return MemoryManager(tmp / ".poor-cli")

    def _add_stale(self, mgr: MemoryManager, name: str) -> MemoryEntry:
        e = MemoryEntry(
            name=name, description="d", type="reference", content="x",
            created_at=_old(200), updated_at=_old(200), last_accessed_at=_old(200),
        )
        mgr.save(e)
        return e

    def test_include_filenames_restricts_archive_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            e1 = self._add_stale(mgr, "keep-me")
            e2 = self._add_stale(mgr, "archive-me")
            e3 = self._add_stale(mgr, "also-keep")
            forgetter = MemoryForgetter(mgr)
            stale = forgetter.due_for_expiry()
            self.assertEqual(len(stale), 3)
            summary = forgetter.run_expiry_pass(include_filenames=[e2.filename])
            self.assertEqual(summary.archived, [e2.filename])
            # the other two remain as live entries
            remaining = forgetter.due_for_expiry()
            names = sorted(e.name for e in remaining)
            self.assertEqual(names, ["also-keep", "keep-me"])

    def test_include_filenames_empty_archives_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            self._add_stale(mgr, "a")
            self._add_stale(mgr, "b")
            summary = MemoryForgetter(mgr).run_expiry_pass(include_filenames=[])
            self.assertEqual(summary.archived, [])

    def test_include_filenames_none_keeps_legacy_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            self._add_stale(mgr, "a")
            self._add_stale(mgr, "b")
            summary = MemoryForgetter(mgr).run_expiry_pass(include_filenames=None)
            # both archived (legacy "archive everything stale" behavior)
            self.assertEqual(len(summary.archived), 2)

    def test_dry_run_with_filter_preview_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            e1 = self._add_stale(mgr, "a")
            e2 = self._add_stale(mgr, "b")
            summary = MemoryForgetter(mgr).run_expiry_pass(
                dry_run=True, include_filenames=[e1.filename]
            )
            self.assertEqual(summary.archived, [e1.filename])
            # nothing actually archived — both still stale
            self.assertEqual(len(MemoryForgetter(mgr).due_for_expiry()), 2)


if __name__ == "__main__":
    unittest.main()
