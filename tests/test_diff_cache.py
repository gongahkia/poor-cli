"""Tests for CB1 diff-of-diff file context cache."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from poor_cli.context.diff_cache import (
    DiffCache,
    DiffCacheEntry,
    DiffEmission,
    hash_text,
)


class DiffCacheKeyTests(unittest.TestCase):
    def test_key_is_stable_for_same_inputs(self):
        self.assertEqual(
            DiffCache.make_key("src/foo.py", "hashA"),
            DiffCache.make_key("src/foo.py", "hashA"),
        )

    def test_key_differs_on_file_change(self):
        self.assertNotEqual(
            DiffCache.make_key("src/foo.py", "h"),
            DiffCache.make_key("src/bar.py", "h"),
        )

    def test_key_differs_on_context_change(self):
        self.assertNotEqual(
            DiffCache.make_key("src/foo.py", "h1"),
            DiffCache.make_key("src/foo.py", "h2"),
        )


class DiffCacheEnsureTests(unittest.TestCase):
    def _tmp_cache(self, tmp: Path) -> DiffCache:
        return DiffCache(tmp / "cache.json", ttl_seconds=0)  # disable TTL for test

    def test_first_call_returns_full(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self._tmp_cache(Path(tmp))
            key = DiffCache.make_key("src/a.py")
            emission, entry = cache.ensure_entry(key, "line1\nline2\nline3\n")
            self.assertEqual(emission.mode, "full")
            self.assertEqual(emission.tokens_saved_estimate, 0)
            self.assertEqual(entry.full_text, "line1\nline2\nline3\n")

    def test_second_call_identical_content_returns_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self._tmp_cache(Path(tmp))
            key = DiffCache.make_key("src/a.py")
            cache.ensure_entry(key, "x\n")
            emission, _ = cache.ensure_entry(key, "x\n")
            self.assertEqual(emission.mode, "unchanged")

    def test_second_call_modified_content_returns_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self._tmp_cache(Path(tmp))
            key = DiffCache.make_key("src/a.py")
            original = "\n".join([f"line {i}" for i in range(50)])
            cache.ensure_entry(key, original)
            modified = original.replace("line 25", "line 25 MODIFIED")
            emission, _ = cache.ensure_entry(key, modified)
            self.assertEqual(emission.mode, "diff")
            # unchanged runs collapse
            self.assertIn("unchanged", emission.content)
            # modification is present
            self.assertIn("line 25 MODIFIED", emission.content)
            self.assertGreater(emission.tokens_saved_estimate, 0)

    def test_small_unchanged_runs_are_not_collapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self._tmp_cache(Path(tmp))
            key = DiffCache.make_key("src/tiny.py")
            cache.ensure_entry(key, "a\nb\nc\n")
            emission, _ = cache.ensure_entry(key, "a\nB\nc\n")
            self.assertEqual(emission.mode, "diff")
            # runs of 1-2 unchanged lines remain inline (min_run=5)
            self.assertNotIn("unchanged", emission.content)

    def test_invalidate_resets_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self._tmp_cache(Path(tmp))
            key = DiffCache.make_key("src/a.py")
            cache.ensure_entry(key, "x")
            cache.invalidate(key)
            self.assertIsNone(cache.get(key))

    def test_persist_and_reload_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            cache = DiffCache(path, ttl_seconds=3600)
            key = DiffCache.make_key("src/a.py")
            cache.ensure_entry(key, "hello\nworld\n")
            cache.persist()
            self.assertTrue(path.exists())

            reloaded = DiffCache(path, ttl_seconds=3600)
            reloaded.load()
            self.assertIsNotNone(reloaded.get(key))

    def test_ttl_drops_stale_entries_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            cache = DiffCache(path, ttl_seconds=0.001)
            key = DiffCache.make_key("src/a.py")
            cache.ensure_entry(key, "x")
            cache.persist()
            import time
            time.sleep(0.01)

            reloaded = DiffCache(path, ttl_seconds=0.001)
            reloaded.load()
            self.assertIsNone(reloaded.get(key))


class DiffEmissionTests(unittest.TestCase):
    def test_to_dict_keys(self):
        e = DiffEmission(content="x", mode="diff", tokens_saved_estimate=10)
        d = e.to_dict()
        self.assertEqual(d["mode"], "diff")
        self.assertEqual(d["tokensSavedEstimate"], 10)
        self.assertEqual(d["content"], "x")


class HashTextTests(unittest.TestCase):
    def test_hash_stability(self):
        self.assertEqual(hash_text("abc"), hash_text("abc"))
        self.assertNotEqual(hash_text("abc"), hash_text("abd"))
        self.assertEqual(len(hash_text("abc")), 16)


if __name__ == "__main__":
    unittest.main()
