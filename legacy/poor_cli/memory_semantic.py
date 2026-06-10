"""MH2 semantic retrieval layer for MemoryManager.

Layers ``embeddings.py`` over keyword search. Embeddings are stored in a
SQLite sidecar at ``<memory_dir>/embeddings.sqlite3`` keyed by memory filename.
Hybrid retrieval = union of top-K keyword hits + top-K semantic hits, deduped.

Fallback rules:
- No embedding provider available → semantic call returns ``[]``, caller uses keyword only.
- Embedding provider raises → log, return keyword results unchanged.
- Missing embedding for a memory → lazy-embed on first access (best effort).

MH7 reranker can post-process the hybrid result; this module exposes the
raw ranked list so the reranker composes cleanly.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Tuple

from .embeddings import (
    EmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
)
from .exceptions import setup_logger
from .memory import MemoryEntry, MemoryManager

logger = setup_logger(__name__)

EMBEDDINGS_DB_NAME = "embeddings.sqlite3"
DEFAULT_SEMANTIC_THRESHOLD = 0.55  # min cosine sim to count as a hit


class MemoryEmbeddingStore:
    """SQLite-backed embedding store keyed by memory filename."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS memory_embeddings (
                        filename TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        dim INTEGER NOT NULL,
                        vector TEXT NOT NULL,
                        content_hash TEXT NOT NULL
                    )"""
                )
                conn.commit()

    def get(self, filename: str) -> Optional[Tuple[List[float], str, str]]:
        """Return (vector, provider, content_hash) or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT vector, provider, content_hash FROM memory_embeddings WHERE filename = ?",
                (filename,),
            ).fetchone()
            if not row:
                return None
            try:
                vec = json.loads(row["vector"])
            except (json.JSONDecodeError, TypeError):
                return None
            return (vec, row["provider"], row["content_hash"])

    def put(self, filename: str, vector: List[float], provider: str, content_hash: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO memory_embeddings
                       (filename, provider, dim, vector, content_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (filename, provider, len(vector), json.dumps(vector), content_hash),
                )
                conn.commit()

    def delete(self, filename: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM memory_embeddings WHERE filename = ?", (filename,))
                conn.commit()

    def all_filenames(self) -> List[str]:
        with self._connect() as conn:
            return [row["filename"] for row in conn.execute("SELECT filename FROM memory_embeddings")]


def _content_hash(entry: MemoryEntry) -> str:
    from .memory import hash_source_message
    return hash_source_message(f"{entry.name}\n{entry.description}\n{entry.content}")


def _entry_text(entry: MemoryEntry) -> str:
    """Concatenate searchable surface text for embedding."""
    return f"{entry.name}\n{entry.description}\n{entry.content}"


async def ensure_embedding(
    entry: MemoryEntry,
    store: MemoryEmbeddingStore,
    provider: EmbeddingProvider,
) -> Optional[List[float]]:
    """Return the embedding for entry, computing + caching on first access."""
    current_hash = _content_hash(entry)
    cached = store.get(entry.filename)
    if cached is not None:
        vec, cached_provider, cached_hash = cached
        if cached_hash == current_hash and cached_provider == provider.name and len(vec) == provider.dimensions:
            return vec
    try:
        vectors = await provider.embed([_entry_text(entry)])
    except Exception as exc:
        logger.debug("embed failed for %s: %s", entry.filename, exc)
        return None
    if not vectors:
        return None
    vec = list(vectors[0])
    store.put(entry.filename, vec, provider.name, current_hash)
    return vec


async def semantic_search(
    manager: MemoryManager,
    query: str,
    *,
    max_results: int = 5,
    threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    provider: Optional[EmbeddingProvider] = None,
) -> List[Tuple[MemoryEntry, float]]:
    """Rank memories by cosine similarity to query. Returns (entry, score) pairs.

    No hits = empty list. Embedding provider unavailable = empty list.
    Caller should fall back to keyword search when this returns empty.
    """
    if not manager._entries:  # type: ignore[reportPrivateUsage]
        manager.load()
    entries = list(manager._entries.values())  # type: ignore[reportPrivateUsage]
    if not entries:
        return []
    provider = provider or get_embedding_provider()
    if provider is None:
        logger.debug("no embedding provider available; semantic search skipped")
        return []
    store = MemoryEmbeddingStore(manager._memory_dir / EMBEDDINGS_DB_NAME)  # type: ignore[reportPrivateUsage]
    try:
        query_vectors = await provider.embed([query])
    except Exception as exc:
        logger.warning("embed query failed: %s", exc)
        return []
    if not query_vectors:
        return []
    query_vec = list(query_vectors[0])
    scored: List[Tuple[MemoryEntry, float]] = []
    for entry in entries:
        emb = await ensure_embedding(entry, store, provider)
        if emb is None:
            continue
        sim = cosine_similarity(query_vec, emb)
        if sim >= threshold:
            scored.append((entry, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:max_results]


async def hybrid_search(
    manager: MemoryManager,
    query: str,
    *,
    max_results: int = 5,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    provider: Optional[EmbeddingProvider] = None,
    record_hits: bool = True,
    rerank: bool = True,
) -> List[MemoryEntry]:
    """Union of top-K keyword + top-K semantic hits, deduped by filename,
    optionally reranked via the user-selected strategy
    (``ux_strategies.memory_reranker_strategy``).
    """
    keyword_hits = manager.search(query, max_results=max_results, record_hits=False)
    semantic_hits = await semantic_search(
        manager, query,
        max_results=max_results,
        threshold=semantic_threshold,
        provider=provider,
    )
    if rerank and semantic_hits:
        try:
            from .ux_strategies import load as _load_strategies
            from .memory_reranker import rerank_semantic_hits
            strategies = _load_strategies()
            strategy = strategies.get("memory_reranker_strategy", "mmr")
            cross_model = strategies.get("memory_reranker_cross_encoder_model", "")
            # fetch embeddings dict for MMR path
            try:
                store = manager._embedding_store()  # type: ignore[reportPrivateUsage]
                embeddings = store.all_vectors() if hasattr(store, "all_vectors") else {}
            except Exception:
                embeddings = {}
            query_vec = semantic_hits[0][1] if semantic_hits else [0.0]
            if isinstance(query_vec, (int, float)):
                query_vec = [float(query_vec)]
            kwargs = {"strategy": strategy, "k": max_results, "query_text": query}
            if cross_model:
                kwargs["cross_encoder_model"] = cross_model
            reranked = rerank_semantic_hits(
                query_vec, semantic_hits, embeddings, **kwargs,
            )
            if reranked:
                # reranked ordering overrides the semantic-first path, then
                # keyword-only entries come after
                seen: set[str] = set()
                ordered: List[MemoryEntry] = []
                for entry in reranked:
                    if entry.filename in seen:
                        continue
                    seen.add(entry.filename)
                    ordered.append(entry)
                for entry in keyword_hits:
                    if entry.filename in seen:
                        continue
                    seen.add(entry.filename)
                    ordered.append(entry)
                hits = ordered[:max_results]
                if record_hits:
                    manager._record_retrieval(hits)  # type: ignore[reportPrivateUsage]
                return hits
        except Exception:
            # rerank is best-effort; fall through to legacy semantic-first ordering
            pass
    seen: set[str] = set()
    ordered: List[MemoryEntry] = []
    for entry, _ in semantic_hits:
        if entry.filename in seen:
            continue
        seen.add(entry.filename)
        ordered.append(entry)
    for entry in keyword_hits:
        if entry.filename in seen:
            continue
        seen.add(entry.filename)
        ordered.append(entry)
    hits = ordered[:max_results]
    if record_hits:
        manager._record_retrieval(hits)  # type: ignore[reportPrivateUsage]
    return hits


def hybrid_search_sync(
    manager: MemoryManager,
    query: str,
    **kwargs,
) -> List[MemoryEntry]:
    """Blocking wrapper for callers not running in an asyncio context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # caller is inside an async context — they must use the async form
            raise RuntimeError("hybrid_search_sync called inside a running event loop; use hybrid_search instead")
    except RuntimeError:
        loop = None
    return asyncio.run(hybrid_search(manager, query, **kwargs))
