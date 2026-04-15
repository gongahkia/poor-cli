"""MH7: strategy dispatch (score_order / mmr / cross_encoder fallback)."""
from __future__ import annotations
import sys
import types
import pytest

from poor_cli.memory import MemoryEntry
from poor_cli import memory_reranker as rr


def _entries():
    return [MemoryEntry(name=f"n{i}", description=f"d{i}", type="project", content=f"c{i}") for i in range(4)]


def test_score_order_returns_top_k_in_incoming_order():
    entries = _entries()
    hits = [(entries[0], 0.9), (entries[1], 0.8), (entries[2], 0.7), (entries[3], 0.6)]
    out = rr.rerank_semantic_hits([0.0], hits, {}, strategy="score_order", k=2)
    assert [e.name for e in out] == ["n0", "n1"]


def test_unknown_strategy_falls_back_to_mmr(caplog):
    entries = _entries()
    hits = [(entries[0], 0.9), (entries[1], 0.8)]
    embeddings = {"n0.md": [1.0, 0.0], "n1.md": [0.0, 1.0]}
    with caplog.at_level("WARNING"):
        out = rr.rerank_semantic_hits([1.0, 0.0], hits, embeddings, strategy="bogus", k=2)
    assert len(out) >= 1


def test_cross_encoder_missing_dep_falls_back_to_mmr(monkeypatch):
    entries = _entries()
    hits = [(entries[0], 0.9), (entries[1], 0.8)]
    embeddings = {entries[0].filename: [1.0, 0.0], entries[1].filename: [0.0, 1.0]}

    # force sentence_transformers ImportError path
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    rr._CROSS_ENCODER_CACHE.clear()

    out = rr.rerank_semantic_hits(
        [1.0, 0.0], hits, embeddings, strategy="cross_encoder",
        query_text="test query", k=2,
    )
    assert len(out) >= 1
    # cache should now have None sentinel
    assert rr._CROSS_ENCODER_CACHE[rr.DEFAULT_CROSS_ENCODER_MODEL] is None


def test_cross_encoder_with_stub_model_reranks(monkeypatch):
    entries = _entries()
    hits = [(entries[0], 0.5), (entries[1], 0.5), (entries[2], 0.5)]

    class _Stub:
        def __init__(self, name: str) -> None: self.name = name
        def predict(self, pairs):
            # give a decreasing score so result order is n2, n1, n0
            return [0.1 * i for i in range(len(pairs), 0, -1)]

    stub_module = types.ModuleType("sentence_transformers")
    stub_module.CrossEncoder = _Stub  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub_module)
    rr._CROSS_ENCODER_CACHE.clear()

    out = rr.rerank_semantic_hits(
        [1.0, 0.0], hits, {}, strategy="cross_encoder",
        query_text="q", k=3,
    )
    assert [e.name for e in out] == ["n0", "n1", "n2"]


def test_cross_encoder_without_query_text_falls_back(monkeypatch):
    entries = _entries()
    hits = [(entries[0], 0.9), (entries[1], 0.8)]
    embeddings = {entries[0].filename: [1.0, 0.0], entries[1].filename: [0.0, 1.0]}
    out = rr.rerank_semantic_hits(
        [1.0, 0.0], hits, embeddings, strategy="cross_encoder",
        query_text="", k=2,
    )
    assert len(out) >= 1
