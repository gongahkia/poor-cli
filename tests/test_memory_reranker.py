"""Tests for MH7 memory reranker (MMR)."""

from __future__ import annotations

import unittest

from poor_cli.memory import MemoryEntry
from poor_cli.memory_reranker import mmr, rerank_semantic_hits


def _entry(name: str) -> MemoryEntry:
    return MemoryEntry(name=name, description="d", type="project", content="c")


class MmrRerankerTests(unittest.TestCase):
    def test_empty_candidates_returns_empty(self):
        self.assertEqual(mmr([1.0, 0.0], [], k=5), [])

    def test_k_zero_returns_empty(self):
        e1, v1 = _entry("a"), [1.0, 0.0]
        self.assertEqual(mmr([1.0, 0.0], [(e1, v1)], k=0), [])

    def test_pure_relevance_orders_by_similarity(self):
        query = [1.0, 0.0]
        candidates = [
            (_entry("irrelevant"), [0.0, 1.0]),
            (_entry("perfect"), [1.0, 0.0]),
            (_entry("related"), [0.8, 0.2]),
        ]
        # lambda_=1.0 → pure relevance; should return [perfect, related, irrelevant]
        result = mmr(query, candidates, lambda_=1.0, k=3)
        names = [e.name for e in result]
        self.assertEqual(names[0], "perfect")
        self.assertEqual(names[1], "related")

    def test_pure_diversity_spreads_picks(self):
        query = [1.0, 0.0, 0.0]
        # three near-identical vectors + one orthogonal
        candidates = [
            (_entry("near1"), [0.99, 0.01, 0.0]),
            (_entry("near2"), [0.98, 0.02, 0.0]),
            (_entry("near3"), [0.97, 0.03, 0.0]),
            (_entry("different"), [0.0, 0.0, 1.0]),
        ]
        result = mmr(query, candidates, lambda_=0.0, k=2)
        names = [e.name for e in result]
        # diversity-only should pick one near-* plus the different one
        self.assertIn("different", names)

    def test_diversity_weight_prefers_different_over_duplicative(self):
        query = [1.0, 0.0, 0.0]
        # near1 and near2 are nearly identical; different is somewhat relevant
        # and orthogonal-ish to the near cluster
        candidates = [
            (_entry("near1"), [0.99, 0.01, 0.0]),
            (_entry("near2"), [0.98, 0.02, 0.0]),
            (_entry("different"), [0.5, 0.0, 0.87]),
        ]
        # at lambda_=0.4 (diversity-weighted), the second pick should be
        # "different" rather than the near-duplicate near2
        result = mmr(query, candidates, lambda_=0.4, k=2)
        names = [e.name for e in result]
        self.assertEqual(names[0], "near1")
        self.assertEqual(names[1], "different")

    def test_k_caps_output_size(self):
        query = [1.0, 0.0]
        candidates = [(_entry(f"e{i}"), [1.0, 0.0]) for i in range(5)]
        result = mmr(query, candidates, lambda_=0.5, k=2)
        self.assertEqual(len(result), 2)

    def test_rerank_semantic_hits_skips_missing_vectors(self):
        hits = [
            (_entry("have"), 0.9),
            (_entry("no_vec"), 0.85),
        ]
        embeddings = {"have.md": [1.0, 0.0]}
        result = rerank_semantic_hits(
            [1.0, 0.0], hits, embeddings, strategy="mmr", k=5
        )
        names = [e.name for e in result]
        self.assertIn("have", names)
        self.assertNotIn("no_vec", names)

    def test_rerank_semantic_hits_falls_back_when_no_embeddings(self):
        hits = [(_entry("a"), 0.9), (_entry("b"), 0.8)]
        # no embeddings known — should fall back to slicing top-k by score
        result = rerank_semantic_hits([1.0, 0.0], hits, {}, strategy="mmr", k=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "a")


if __name__ == "__main__":
    unittest.main()
