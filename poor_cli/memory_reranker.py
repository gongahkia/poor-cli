"""MH7 post-retrieval reranker for memory.

Addresses the "retrieval misfire" failure mode — candidates that are close
semantically but wrong contextually. Cheap MMR (Maximal Marginal Relevance)
picks a subset that balances relevance to the query against diversity among
chosen memories. No new dependencies: reuses vectors from the semantic search
layer when available.

Strategy:
- ``mmr(query_vec, candidates, lambda_=0.7, k=5)`` returns up to k entries that
  maximize ``lambda * sim(query, entry) - (1 - lambda) * max(sim(entry, picked))``.
- ``lambda_=1.0`` = pure relevance; ``lambda_=0.0`` = pure diversity.
- Default 0.7 slightly favors relevance while still injecting diversity.

Optional cross-encoder strategy is stubbed but gated behind
``memory.reranker.enabled`` and the HF local stack — not wired by default.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .embeddings import cosine_similarity
from .memory import MemoryEntry


def mmr(
    query_vec: Sequence[float],
    candidates: List[Tuple[MemoryEntry, List[float]]],
    *,
    lambda_: float = 0.7,
    k: int = 5,
) -> List[MemoryEntry]:
    """Maximal Marginal Relevance rerank.

    candidates is a list of (entry, embedding_vector) pairs. Returns up to k
    entries in rerank order. lambda_ trades relevance vs diversity (1.0 = pure
    relevance; 0.0 = pure diversity). Default 0.7.
    """
    if not candidates:
        return []
    if k <= 0:
        return []
    lambda_ = max(0.0, min(1.0, lambda_))
    selected: List[Tuple[MemoryEntry, List[float]]] = []
    remaining = list(candidates)
    # rank initial candidates by similarity to query for efficient first pick
    remaining.sort(key=lambda c: cosine_similarity(query_vec, c[1]), reverse=True)
    while remaining and len(selected) < k:
        best_idx = 0
        best_score = -float("inf")
        for idx, (_, vec) in enumerate(remaining):
            relevance = cosine_similarity(query_vec, vec)
            if selected:
                max_sim = max(cosine_similarity(vec, chosen_vec) for _, chosen_vec in selected)
            else:
                max_sim = 0.0
            score = lambda_ * relevance - (1.0 - lambda_) * max_sim
            if score > best_score:
                best_score = score
                best_idx = idx
        selected.append(remaining.pop(best_idx))
    return [entry for entry, _ in selected]


def rerank_semantic_hits(
    query_vec: Sequence[float],
    hits: List[Tuple[MemoryEntry, float]],
    manager_embeddings: dict,
    *,
    strategy: str = "mmr",
    lambda_: float = 0.7,
    k: int = 5,
) -> List[MemoryEntry]:
    """Rerank semantic_search output into a diversity-balanced top-k.

    manager_embeddings is a mapping filename -> vector (from
    MemoryEmbeddingStore). Entries missing from the mapping are skipped.
    """
    if strategy != "mmr":
        # only MMR ships in v1; other strategies (cross-encoder) would register here
        return [entry for entry, _ in hits[:k]]
    pairs: List[Tuple[MemoryEntry, List[float]]] = []
    for entry, _ in hits:
        vec = manager_embeddings.get(entry.filename)
        if vec:
            pairs.append((entry, vec))
    if not pairs:
        return [entry for entry, _ in hits[:k]]
    return mmr(query_vec, pairs, lambda_=lambda_, k=k)
