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

    def test_profiles_query_modes_and_excludes(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._manager(Path(tmp))
            results = asyncio.run(search_lod(
                mgr,
                "JSONL pytest",
                max_results=5,
                alpha_profile="semantic",
                exclude=["pytest"],
            ))
            self.assertTrue(results)
            self.assertNotEqual(results[0].entry.name, "old failure")
            never_seen = asyncio.run(search_lod(mgr, "state", max_results=5, query_mode="never_seen"))
            self.assertTrue(all(result.entry.hit_count <= 1 for result in never_seen))

    def test_save_synthesizes_lod_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = MemoryManager(Path(tmp) / ".poor-cli")
            mgr.save(MemoryEntry(
                name="long note",
                description="",
                type="project",
                content="This is the first sentence. " + "detail " * 100,
                headline="",
                summary="",
            ))
            loaded = mgr.get("long note", record_hit=False)
            self.assertIsNotNone(loaded)
            self.assertIn("first sentence", loaded.headline)
            self.assertTrue(loaded.summary.endswith("..."))


if __name__ == "__main__":
    unittest.main()
