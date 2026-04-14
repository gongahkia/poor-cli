"""Tests for MH1 (provenance) + MH8 (access-recency telemetry) on MemoryEntry."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from poor_cli.auto_memory import extract_memories_from_history
from poor_cli.memory import MemoryEntry, MemoryManager, hash_source_message


class TestMemoryProvenance(unittest.TestCase):
    def test_hash_source_message_stable_16_chars(self):
        h1 = hash_source_message("hello world")
        h2 = hash_source_message("hello world")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)
        self.assertNotEqual(h1, hash_source_message("hello World"))

    def test_memory_entry_defaults_on_provenance(self):
        entry = MemoryEntry(name="x", description="d", type="project", content="c")
        self.assertEqual(entry.source_session_id, "")
        self.assertEqual(entry.extractor, "unknown")
        self.assertEqual(entry.derivation_depth, 0)
        self.assertEqual(entry.hit_count, 0)
        self.assertEqual(entry.last_accessed_at, entry.created_at)

    def test_memory_entry_rejects_invalid_extractor(self):
        entry = MemoryEntry(name="x", description="d", type="project", content="c", extractor="bogus")
        self.assertEqual(entry.extractor, "unknown")

    def test_memory_entry_clamps_negative_depth_and_hits(self):
        entry = MemoryEntry(
            name="x", description="d", type="project", content="c",
            derivation_depth=-5, hit_count=-1,
        )
        self.assertEqual(entry.derivation_depth, 0)
        self.assertEqual(entry.hit_count, 0)

    def test_render_file_emits_provenance_only_when_set(self):
        minimal = MemoryEntry(name="x", description="d", type="project", content="c")
        rendered = minimal.render_file()
        self.assertNotIn("source_session_id", rendered)
        self.assertNotIn("hit_count", rendered)

        full = MemoryEntry(
            name="x", description="d", type="project", content="c",
            source_session_id="sess-1", source_turn_id="3",
            source_message_hash="abc123", extractor="heuristic", derivation_depth=1,
            hit_count=5,
        )
        rendered = full.render_file()
        self.assertIn("source_session_id: sess-1", rendered)
        self.assertIn("source_turn_id: 3", rendered)
        self.assertIn("source_message_hash: abc123", rendered)
        self.assertIn("extractor: heuristic", rendered)
        self.assertIn("derivation_depth: 1", rendered)
        self.assertIn("hit_count: 5", rendered)

    def test_to_dict_includes_provenance(self):
        entry = MemoryEntry(
            name="x", description="d", type="project", content="c",
            source_session_id="sess-1", extractor="llm", derivation_depth=1,
        )
        data = entry.to_dict()
        self.assertEqual(data["sourceSessionId"], "sess-1")
        self.assertEqual(data["extractor"], "llm")
        self.assertEqual(data["derivationDepth"], 1)
        self.assertIn("hitCount", data)
        self.assertIn("lastAccessedAt", data)

    def test_roundtrip_load_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = MemoryManager(Path(tmp) / ".poor-cli")
            entry = MemoryEntry(
                name="roundtrip", description="d", type="project", content="c",
                source_session_id="sess-42", source_turn_id="7",
                source_message_hash="deadbeef", extractor="heuristic", derivation_depth=0,
            )
            mgr.save(entry)

            mgr2 = MemoryManager(Path(tmp) / ".poor-cli")
            loaded = mgr2.load()
            self.assertEqual(len(loaded), 1)
            got = loaded[0]
            self.assertEqual(got.source_session_id, "sess-42")
            self.assertEqual(got.source_turn_id, "7")
            self.assertEqual(got.source_message_hash, "deadbeef")
            self.assertEqual(got.extractor, "heuristic")

    def test_extract_from_history_records_provenance(self):
        messages = [
            {"role": "user", "content": "I prefer using Go over Rust for this project."},
        ]
        memories = extract_memories_from_history(messages, source_session_id="sess-abc")
        self.assertEqual(len(memories), 1)
        m = memories[0]
        self.assertEqual(m.source_session_id, "sess-abc")
        self.assertEqual(m.source_turn_id, "0")
        self.assertEqual(m.extractor, "heuristic")
        self.assertEqual(m.derivation_depth, 0)
        self.assertTrue(m.source_message_hash)


class TestMemoryTelemetry(unittest.TestCase):
    def test_touch_increments_and_timestamps(self):
        entry = MemoryEntry(name="x", description="d", type="project", content="c")
        before = entry.hit_count
        before_ts = entry.last_accessed_at
        entry.touch()
        self.assertEqual(entry.hit_count, before + 1)
        self.assertNotEqual(entry.last_accessed_at, before_ts)

    def test_search_records_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = MemoryManager(Path(tmp) / ".poor-cli")
            mgr.save(MemoryEntry(name="golang rule", description="d", type="feedback", content="prefer Go"))
            mgr.save(MemoryEntry(name="other", description="d", type="project", content="unrelated"))

            results = mgr.search("golang")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].hit_count, 1)

            mgr.search("golang")
            self.assertEqual(mgr.get("golang rule", record_hit=False).hit_count, 2)

    def test_get_records_hits_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = MemoryManager(Path(tmp) / ".poor-cli")
            mgr.save(MemoryEntry(name="target", description="d", type="project", content="x"))
            entry = mgr.get("target")
            self.assertEqual(entry.hit_count, 1)
            entry = mgr.get("target", record_hit=False)
            self.assertEqual(entry.hit_count, 1)

    def test_list_all_does_not_record_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = MemoryManager(Path(tmp) / ".poor-cli")
            mgr.save(MemoryEntry(name="a", description="d", type="project", content="x"))
            mgr.list_all()
            mgr.list_all()
            entry = mgr.get("a", record_hit=False)
            self.assertEqual(entry.hit_count, 0)

    def test_telemetry_persisted_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = MemoryManager(Path(tmp) / ".poor-cli")
            mgr.save(MemoryEntry(name="persistent", description="d", type="project", content="x"))
            mgr.get("persistent")  # hit_count=1 on disk
            mgr2 = MemoryManager(Path(tmp) / ".poor-cli")
            loaded = mgr2.get("persistent", record_hit=False)
            self.assertEqual(loaded.hit_count, 1)


if __name__ == "__main__":
    unittest.main()
