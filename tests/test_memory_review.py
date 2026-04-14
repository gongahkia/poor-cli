"""Tests for MH4 in-loop memory review."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from poor_cli.auto_memory import auto_save_session_memories
from poor_cli.memory import MemoryEntry, MemoryManager
from poor_cli.memory_review import (
    accept_pending,
    bulk_accept,
    bulk_reject,
    clear_pending,
    list_pending,
    pending_dir,
    reject_pending,
    stage_pending_memories,
)


class MemoryReviewTests(unittest.TestCase):
    def _mgr(self, tmp: Path) -> MemoryManager:
        return MemoryManager(tmp / ".poor-cli")

    def test_stage_creates_pending_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            entries = [MemoryEntry(name="pending a", description="d", type="project", content="x")]
            paths = stage_pending_memories(mgr, entries)
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].exists())
            self.assertTrue(pending_dir(mgr).exists())
            # not visible in live store
            self.assertIsNone(mgr.get("pending a", record_hit=False))

    def test_list_pending_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            entries = [
                MemoryEntry(name="a", description="d", type="feedback", content="prefer X", source_session_id="sess-1"),
                MemoryEntry(name="b", description="d", type="project", content="y"),
            ]
            stage_pending_memories(mgr, entries)
            listed = list_pending(mgr)
            names = {e.name for e in listed}
            self.assertEqual(names, {"a", "b"})
            # provenance preserved
            a = next(e for e in listed if e.name == "a")
            self.assertEqual(a.source_session_id, "sess-1")

    def test_accept_pending_moves_to_live_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            e = MemoryEntry(name="accept me", description="d", type="project", content="x")
            stage_pending_memories(mgr, [e])
            saved = accept_pending(mgr, e.filename)
            self.assertIsNotNone(saved)
            # live store has it
            self.assertIsNotNone(mgr.get("accept me", record_hit=False))
            # pending file gone
            self.assertFalse((pending_dir(mgr) / e.filename).exists())

    def test_accept_pending_with_edit_overrides_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            e = MemoryEntry(name="edit me", description="d", type="project", content="original")
            stage_pending_memories(mgr, [e])
            edited = MemoryEntry(name="edit me", description="d", type="project", content="user-edited")
            accept_pending(mgr, e.filename, edited_entry=edited)
            got = mgr.get("edit me", record_hit=False)
            self.assertEqual(got.content, "user-edited")

    def test_reject_pending_drops_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            e = MemoryEntry(name="reject me", description="d", type="project", content="x")
            stage_pending_memories(mgr, [e])
            self.assertTrue(reject_pending(mgr, e.filename))
            self.assertFalse((pending_dir(mgr) / e.filename).exists())
            # live store untouched
            self.assertIsNone(mgr.get("reject me", record_hit=False))

    def test_clear_pending_drops_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            entries = [
                MemoryEntry(name=f"mem{i}", description="d", type="project", content="x")
                for i in range(3)
            ]
            stage_pending_memories(mgr, entries)
            count = clear_pending(mgr)
            self.assertEqual(count, 3)
            self.assertEqual(list_pending(mgr), [])

    def test_bulk_accept(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            entries = [
                MemoryEntry(name=f"mem{i}", description="d", type="feedback", content="x")
                for i in range(3)
            ]
            stage_pending_memories(mgr, entries)
            summary = bulk_accept(mgr)
            self.assertEqual(set(summary.accepted), {"mem0", "mem1", "mem2"})
            self.assertEqual(list_pending(mgr), [])

    def test_bulk_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._mgr(Path(tmp))
            entries = [
                MemoryEntry(name=f"mem{i}", description="d", type="project", content="x")
                for i in range(2)
            ]
            stage_pending_memories(mgr, entries)
            summary = bulk_reject(mgr)
            self.assertEqual(set(summary.rejected), {"mem0", "mem1"})

    def test_auto_save_with_prompt_mode_stages_instead_of_saving(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            messages = [
                {"role": "user", "content": "I prefer Go for backend services always."},
            ]
            saved = asyncio.run(auto_save_session_memories(
                messages, base_dir=base, provider=None,
                source_session_id="sess-x", review_mode="prompt",
            ))
            # staged, not saved live
            mgr = MemoryManager(base)
            self.assertEqual(mgr.list_all(), [])  # nothing live
            pending = list_pending(mgr)
            self.assertTrue(pending)
            self.assertEqual(pending[0].source_session_id, "sess-x")


if __name__ == "__main__":
    unittest.main()
