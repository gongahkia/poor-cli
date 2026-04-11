"""Tests for semantic response cache."""

import asyncio
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.semantic_cache import (
    CacheResult,
    SemanticCache,
    SemanticCacheStats,
    compute_context_hash,
    reset_semantic_cache,
)


def _make_embedding(dim: int = 768, seed: float = 1.0) -> list:
    """Deterministic fake embedding."""
    import math
    return [math.sin(seed * (i + 1)) for i in range(dim)]


class FakeEmbeddingProvider:
    """In-process embedding stub for tests."""

    def __init__(self, dim: int = 768):
        self._dim = dim
        self._call_count = 0

    @property
    def name(self) -> str:
        return "fake"

    @property
    def dimensions(self) -> int:
        return self._dim

    def available(self) -> bool:
        return True

    async def embed(self, texts: list) -> list:
        self._call_count += 1
        return [_make_embedding(self._dim, seed=hash(t) % 1000) for t in texts]


class TestSemanticCacheBasic(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self._tmpdir) / "test_cache.db"
        self.provider = FakeEmbeddingProvider()
        self.cache = SemanticCache(
            db_path=self.db_path,
            similarity_threshold=0.90,
            ttl_seconds=3600,
            embedding_provider=self.provider,
        )

    def tearDown(self):
        self.cache.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_miss_on_empty_cache(self):
        result = self._run(self.cache.get("hello world", "ctx1"))
        self.assertIsNone(result)
        self.assertEqual(self.cache._stats.misses, 1)

    def test_put_and_exact_hit(self):
        """Same query should produce a cache hit (similarity=1.0)."""
        self._run(self.cache.put("what is python?", "ctx1", "Python is a language."))
        result = self._run(self.cache.get("what is python?", "ctx1"))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.similarity, 1.0, places=4)
        self.assertEqual(result.response, "Python is a language.")

    def test_different_context_hash_misses(self):
        """Same query but different context hash should miss."""
        self._run(self.cache.put("what is python?", "ctx1", "Python is a language."))
        result = self._run(self.cache.get("what is python?", "ctx_DIFFERENT"))
        self.assertIsNone(result)

    def test_stats_tracking(self):
        self._run(self.cache.put("q1", "c1", "r1"))
        self._run(self.cache.get("q1", "c1"))
        self._run(self.cache.get("q_miss", "c1"))
        stats = self.cache.get_stats()
        self.assertEqual(stats["stores"], 1)
        self.assertEqual(stats["lookups"], 2)
        self.assertGreaterEqual(stats["hits"], 1)

    def test_invalidate_by_context(self):
        self._run(self.cache.put("q1", "ctx_a", "r1"))
        self._run(self.cache.put("q2", "ctx_a", "r2"))
        self._run(self.cache.put("q3", "ctx_b", "r3"))
        removed = self.cache.invalidate_by_context("ctx_a")
        self.assertEqual(removed, 2)
        # ctx_b entry still present
        result = self._run(self.cache.get("q3", "ctx_b"))
        self.assertIsNotNone(result)

    def test_invalidate_all(self):
        self._run(self.cache.put("q1", "c1", "r1"))
        self._run(self.cache.put("q2", "c2", "r2"))
        removed = self.cache.invalidate_all()
        self.assertEqual(removed, 2)
        stats = self.cache.get_stats()
        self.assertEqual(stats["entries"], 0)

    def test_record_savings(self):
        self.cache.record_savings("x" * 400) # ~100 tokens
        stats = self.cache.get_stats()
        self.assertEqual(stats["estimated_tokens_saved"], 100)
        self.assertGreater(stats["estimated_cost_saved_usd"], 0)


class TestSemanticCacheTTL(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self._tmpdir) / "ttl_cache.db"
        self.provider = FakeEmbeddingProvider()
        self.cache = SemanticCache(
            db_path=self.db_path,
            similarity_threshold=0.90,
            ttl_seconds=1, # 1 second TTL for testing
            embedding_provider=self.provider,
        )

    def tearDown(self):
        self.cache.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_ttl_expiry(self):
        self._run(self.cache.put("q1", "c1", "r1"))
        result = self._run(self.cache.get("q1", "c1"))
        self.assertIsNotNone(result)
        time.sleep(1.1) # wait for TTL
        result = self._run(self.cache.get("q1", "c1"))
        self.assertIsNone(result)

    def test_invalidate_expired(self):
        self._run(self.cache.put("q1", "c1", "r1"))
        time.sleep(1.1)
        removed = self.cache.invalidate_expired()
        self.assertEqual(removed, 1)


class TestSemanticCacheEviction(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self._tmpdir) / "evict_cache.db"
        self.provider = FakeEmbeddingProvider()
        self.cache = SemanticCache(
            db_path=self.db_path,
            similarity_threshold=0.90,
            max_entries=3,
            embedding_provider=self.provider,
        )

    def tearDown(self):
        self.cache.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_evicts_oldest_when_full(self):
        for i in range(5):
            self._run(self.cache.put(f"query_{i}", "c1", f"response_{i}"))
        stats = self.cache.get_stats()
        self.assertLessEqual(stats["entries"], 3)


class TestContextHash(unittest.TestCase):
    def test_empty_produces_hash(self):
        h = compute_context_hash()
        self.assertTrue(len(h) > 0)

    def test_different_files_different_hash(self):
        h1 = compute_context_hash(context_files=["/tmp/a.py"])
        h2 = compute_context_hash(context_files=["/tmp/b.py"])
        self.assertNotEqual(h1, h2)

    def test_different_model_different_hash(self):
        h1 = compute_context_hash(model_name="gpt-4")
        h2 = compute_context_hash(model_name="claude-3")
        self.assertNotEqual(h1, h2)

    def test_file_change_invalidates(self):
        """Changing a file's mtime should change the context hash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("v1")
            fpath = f.name
        try:
            h1 = compute_context_hash(context_files=[fpath])
            time.sleep(0.05)
            Path(fpath).write_text("v2") # changes mtime
            h2 = compute_context_hash(context_files=[fpath])
            self.assertNotEqual(h1, h2)
        finally:
            os.unlink(fpath)


class TestSemanticCacheNoProvider(unittest.TestCase):
    """Cache degrades gracefully when no embedding provider is available."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self._tmpdir) / "no_provider.db"

    def tearDown(self):
        if self.db_path.exists():
            self.db_path.unlink()

    def _run(self, coro):
        return asyncio.run(coro)

    @patch("poor_cli.semantic_cache.get_embedding_provider", return_value=None)
    def test_get_returns_none(self, _mock):
        cache = SemanticCache(db_path=self.db_path, embedding_provider=None)
        cache._provider = None # force re-resolve
        result = self._run(cache.get("hello", "ctx"))
        self.assertIsNone(result)
        cache.close()

    @patch("poor_cli.semantic_cache.get_embedding_provider", return_value=None)
    def test_put_returns_false(self, _mock):
        cache = SemanticCache(db_path=self.db_path, embedding_provider=None)
        cache._provider = None
        ok = self._run(cache.put("hello", "ctx", "resp"))
        self.assertFalse(ok)
        cache.close()


if __name__ == "__main__":
    unittest.main()
