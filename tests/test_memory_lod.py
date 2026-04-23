import asyncio
import tempfile
import unittest
from pathlib import Path

from poor_cli.memory import MemoryEntry, MemoryManager
from poor_cli.memory_lod import expand_memory, promote_memory, search_lod


class MemoryLODTests(unittest.TestCase):
    def _manager(self, root: Path) -> MemoryManager:
        mgr = MemoryManager(root / ".poor-cli")
        mgr.save(MemoryEntry(name="old failure", description="pytest timeout", type="project", content="pytest timed out because the fixture waited forever"))
        mgr.save(MemoryEntry(name="decision", description="use JSONL", type="project", content="append-only JSONL is the source of truth for run state"))
        return mgr

    def test_lod_search_returns_tier_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._manager(Path(tmp))
            results = asyncio.run(search_lod(mgr, "JSONL state", max_results=5))
            self.assertTrue(results)
            payload = results[0].to_dict()
            self.assertIn(payload["tier"], {"full", "summary", "headline"})
            self.assertIn("lodScore", payload)

    def test_expand_and_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._manager(Path(tmp))
            entry = expand_memory(mgr, "decision")
            self.assertIsNotNone(entry)
            promoted = promote_memory(mgr, "decision")
            self.assertIsNotNone(promoted)
            self.assertTrue(promoted.pinned)


if __name__ == "__main__":
    unittest.main()
