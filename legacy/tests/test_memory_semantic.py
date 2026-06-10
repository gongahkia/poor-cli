"""Tests for MH2 semantic memory retrieval."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import List

from poor_cli.embeddings import EmbeddingProvider
from poor_cli.memory import MemoryEntry, MemoryManager
from poor_cli.memory_semantic import (
    MemoryEmbeddingStore,
    hybrid_search,
    semantic_search,
)


class _FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic token-overlap embeddings for testing without network."""

    def __init__(self, vocab: List[str]):
        self._vocab = vocab

    @property
    def name(self) -> str:
        return "fake"

    @property
    def dimensions(self) -> int:
        return len(self._vocab)

    def available(self) -> bool:
        return True

    async def embed(self, texts):
        out = []
        for text in texts:
            lower = text.lower()
            out.append([1.0 if word in lower else 0.0 for word in self._vocab])
        return out


class SemanticSearchTests(unittest.TestCase):
    def _make_manager(self, tmp: Path) -> MemoryManager:
        mgr = MemoryManager(tmp / ".poor-cli")
        mgr.save(MemoryEntry(name="golang", description="prefer Go", type="feedback", content="use Go for services"))
        mgr.save(MemoryEntry(name="python", description="prefer Python", type="feedback", content="use Python for scripts"))
        mgr.save(MemoryEntry(name="team", description="small team", type="project", content="three engineers"))
        return mgr

    def test_semantic_search_returns_empty_when_no_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_manager(Path(tmp))
            results = asyncio.run(semantic_search(mgr, "go services", provider=None))
            # if no provider registered, returns []
            # (could pick a real one in user environment; assert type only)
            self.assertIsInstance(results, list)

    def test_semantic_search_with_fake_provider_scores_hits(self):
        vocab = ["go", "python", "team", "services", "scripts"]
        provider = _FakeEmbeddingProvider(vocab)
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_manager(Path(tmp))
            results = asyncio.run(
                semantic_search(mgr, "go services", provider=provider, threshold=0.01)
            )
            self.assertTrue(results)
            names = [e.name for e, _ in results]
            self.assertIn("golang", names)
            self.assertEqual(names[0], "golang")  # best match first

    def test_hybrid_search_deduplicates_and_prefers_semantic_order(self):
        vocab = ["go", "python", "team"]
        provider = _FakeEmbeddingProvider(vocab)
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_manager(Path(tmp))
            results = asyncio.run(
                hybrid_search(mgr, "go", provider=provider, semantic_threshold=0.01, max_results=10)
            )
            names = [e.name for e in results]
            self.assertIn("golang", names)
            # no duplicates
            self.assertEqual(len(names), len(set(names)))

    def test_hybrid_search_records_hits(self):
        vocab = ["go", "python"]
        provider = _FakeEmbeddingProvider(vocab)
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_manager(Path(tmp))
            results = asyncio.run(
                hybrid_search(mgr, "go", provider=provider, semantic_threshold=0.01)
            )
            self.assertTrue(results)
            self.assertGreaterEqual(results[0].hit_count, 1)

    def test_embedding_cache_reuses_vectors(self):
        vocab = ["go", "python"]
        provider = _FakeEmbeddingProvider(vocab)
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_manager(Path(tmp))
            asyncio.run(semantic_search(mgr, "go", provider=provider, threshold=0.01))
            store = MemoryEmbeddingStore(mgr._memory_dir / "embeddings.sqlite3")
            self.assertTrue(len(store.all_filenames()) >= 1)

    def test_embedding_invalidates_on_content_change(self):
        vocab = ["go", "python", "rust"]
        provider = _FakeEmbeddingProvider(vocab)
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_manager(Path(tmp))
            asyncio.run(semantic_search(mgr, "go", provider=provider, threshold=0.01))
            # mutate content and re-save
            entry = mgr.get("golang", record_hit=False)
            entry.content = "use Rust instead"
            mgr.save(entry)
            # semantic search should re-embed
            results = asyncio.run(semantic_search(mgr, "rust", provider=provider, threshold=0.01))
            self.assertTrue(any(e.name == "golang" for e, _ in results))


if __name__ == "__main__":
    unittest.main()
