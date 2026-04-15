"""MH7 post-retrieval reranker for memory.

Addresses the "retrieval misfire" failure mode — candidates that are close
semantically but wrong contextually. Three strategies ship:

- ``score_order``: trivial, return top-k by incoming score. Cheapest. Use
  when you want reproducibility and don't care about diversity.
- ``mmr`` (default): Maximal Marginal Relevance rerank. Cheap, no new deps,
  reuses vectors from the semantic search layer. Trades relevance vs
  diversity via ``lambda_`` in [0.0, 1.0] (default 0.7).
- ``cross_encoder``: optional HF cross-encoder model rescores each
  candidate against the query with a small BERT forward pass. Higher
  quality on ambiguous queries but requires ``sentence-transformers`` and
  downloads a ~80MB model on first use. Gracefully falls back to
  ``score_order`` if the dep is not importable.

The user-facing config ``memory.reranker.strategy`` (wired via
``config.research.memory_reranker_strategy``) picks the strategy.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Tuple

from .embeddings import cosine_similarity
from .memory import MemoryEntry

logger = logging.getLogger(__name__)

VALID_STRATEGIES = ("mmr", "cross_encoder", "score_order")

# Lazily-loaded cross-encoder singleton. Keyed by model name so different
# model choices don't stomp on each other. None sentinel means "tried to
# load and failed — don't retry this session".
_CROSS_ENCODER_CACHE: dict = {}
DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_cross_encoder(model_name: str):
    """Return a loaded CrossEncoder instance or None if unavailable."""
    if model_name in _CROSS_ENCODER_CACHE:
        return _CROSS_ENCODER_CACHE[model_name]
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]
    except ImportError:
        logger.info(
            "cross-encoder reranker requested but sentence-transformers is not installed; "
            "falling back to score_order. install via pip install 'poor-cli[reranker]'."
        )
        _CROSS_ENCODER_CACHE[model_name] = None
        return None
    try:
        model = CrossEncoder(model_name)
    except Exception as exc:
        logger.warning("failed to load cross-encoder %s: %s", model_name, exc)
        _CROSS_ENCODER_CACHE[model_name] = None
        return None
    _CROSS_ENCODER_CACHE[model_name] = model
    return model


def cross_encoder_rerank(
    query_text: str,
    hits: List[Tuple[MemoryEntry, float]],
    *,
    model_name: str = DEFAULT_CROSS_ENCODER_MODEL,
    k: int = 5,
) -> Optional[List[MemoryEntry]]:
    """Rescore hits with a cross-encoder. Returns None if the model is
    unavailable, letting the caller fall back to another strategy.
    """
    if not hits or k <= 0:
        return []
    model = _get_cross_encoder(model_name)
    if model is None:
        return None
    pairs = [(query_text, entry.content or entry.description or entry.name) for entry, _ in hits]
    try:
        scores = model.predict(pairs)
    except Exception as exc:
        logger.warning("cross-encoder scoring failed: %s", exc)
        return None
    ranked = sorted(zip(hits, scores), key=lambda pair: float(pair[1]), reverse=True)
    return [entry for (entry, _score), _ in ranked[:k]]


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
    query_text: str = "",
    cross_encoder_model: str = DEFAULT_CROSS_ENCODER_MODEL,
) -> List[MemoryEntry]:
    """Rerank semantic_search output. Strategy in {mmr, cross_encoder, score_order}.

    manager_embeddings is a mapping filename -> vector (from
    MemoryEmbeddingStore). Entries missing from the mapping are skipped
    (mmr only — cross-encoder uses text).
    """
    strategy = str(strategy or "mmr").strip().lower() or "mmr"
    if strategy not in VALID_STRATEGIES:
        logger.warning("unknown reranker strategy %r; falling back to mmr", strategy)
        strategy = "mmr"

    if strategy == "score_order":
        return [entry for entry, _ in hits[:k]]

    if strategy == "cross_encoder":
        if not query_text:
            # no query text to score against — fall through to mmr/score_order
            logger.debug("cross-encoder strategy needs query_text; falling back to mmr")
        else:
            reranked = cross_encoder_rerank(
                query_text, hits, model_name=cross_encoder_model, k=k
            )
            if reranked is not None:
                return reranked
            # model unavailable — graceful downgrade
            logger.debug("cross-encoder unavailable; falling back to mmr")

    # mmr (default path + fallback)
    pairs: List[Tuple[MemoryEntry, List[float]]] = []
    for entry, _ in hits:
        vec = manager_embeddings.get(entry.filename)
        if vec:
            pairs.append((entry, vec))
    if not pairs:
        return [entry for entry, _ in hits[:k]]
    return mmr(query_vec, pairs, lambda_=lambda_, k=k)
