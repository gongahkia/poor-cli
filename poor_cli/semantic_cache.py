"""
Semantic response cache for poor-cli.

SQLite-backed cache with cosine-similarity search over embeddings.
Avoids redundant API calls by detecting semantically similar queries
and returning cached responses.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .embeddings import EmbeddingProvider, cosine_similarity, get_embedding_provider
from .exceptions import setup_logger

logger = setup_logger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.92
DEFAULT_TTL_SECONDS = 86400 # 24h
DEFAULT_MAX_ENTRIES = 2048


@dataclass
class CacheResult:
    """A cache hit result."""
    query: str
    response: str
    similarity: float
    context_hash: str
    created_at: float
    entry_id: int


@dataclass
class SemanticCacheStats:
    """Accumulated semantic cache statistics."""
    lookups: int = 0
    hits: int = 0
    misses: int = 0
    stores: int = 0
    invalidations: int = 0
    estimated_tokens_saved: int = 0
    estimated_cost_saved_usd: float = 0.0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups > 0 else 0.0


class SemanticCache:
    """SQLite-backed semantic response cache with cosine similarity search."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        self.db_path = db_path or (Path.home() / ".poor-cli" / "cache" / "semantic_cache.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.threshold = similarity_threshold
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._provider = embedding_provider
        self._stats = SemanticCacheStats()
        self._db: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        try:
            self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    query_hash TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    response TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    model_name TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    last_hit_at REAL,
                    hit_count INTEGER DEFAULT 0,
                    response_tokens_est INTEGER DEFAULT 0
                )
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_context_hash
                ON semantic_cache(context_hash)
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON semantic_cache(created_at)
            """)
            self._db.commit()
        except Exception as e:
            logger.error("semantic cache db init failed: %s", e)
            self._db = None

    def _get_provider(self) -> Optional[EmbeddingProvider]:
        if self._provider is None:
            self._provider = get_embedding_provider(preferred="ollama") # prefer local/offline
        return self._provider

    async def get(self, query: str, context_hash: str) -> Optional[CacheResult]:
        """Search cache for semantically similar query with matching context."""
        self._stats.lookups += 1
        if not self._db:
            self._stats.misses += 1
            return None
        provider = self._get_provider()
        if not provider:
            self._stats.misses += 1
            return None
        try:
            embeddings = await provider.embed([query])
            if not embeddings or not embeddings[0]:
                self._stats.misses += 1
                return None
            query_emb = embeddings[0]
        except Exception as e:
            logger.warning("semantic cache embed failed: %s", e)
            self._stats.misses += 1
            return None
        now = time.time()
        cutoff = now - self.ttl
        try:
            rows = self._db.execute(
                "SELECT id, query, response, embedding, created_at, context_hash, response_tokens_est "
                "FROM semantic_cache WHERE context_hash = ? AND created_at > ?",
                (context_hash, cutoff),
            ).fetchall()
        except Exception as e:
            logger.warning("semantic cache query failed: %s", e)
            self._stats.misses += 1
            return None
        best: Optional[CacheResult] = None
        best_sim = 0.0
        for row in rows:
            entry_id, q, resp, emb_json, created_at, ctx_h, tokens_est = row
            try:
                emb = json.loads(emb_json)
            except (json.JSONDecodeError, TypeError):
                continue
            sim = cosine_similarity(query_emb, emb)
            if sim >= self.threshold and sim > best_sim:
                best_sim = sim
                best = CacheResult(
                    query=q, response=resp, similarity=sim,
                    context_hash=ctx_h, created_at=created_at, entry_id=entry_id,
                )
        if best:
            self._stats.hits += 1
            try:
                self._db.execute(
                    "UPDATE semantic_cache SET last_hit_at = ?, hit_count = hit_count + 1 WHERE id = ?",
                    (now, best.entry_id),
                )
                self._db.commit()
            except Exception:
                pass
            return best
        self._stats.misses += 1
        return None

    async def put(
        self,
        query: str,
        context_hash: str,
        response: str,
        *,
        model_name: str = "",
    ) -> bool:
        """Store a query-response pair with its embedding."""
        if not self._db:
            return False
        provider = self._get_provider()
        if not provider:
            return False
        try:
            embeddings = await provider.embed([query])
            if not embeddings or not embeddings[0]:
                return False
            emb = embeddings[0]
        except Exception as e:
            logger.warning("semantic cache embed for store failed: %s", e)
            return False
        query_hash = hashlib.sha256(query.encode("utf-8", errors="replace")).hexdigest()
        tokens_est = len(response) // 4
        try:
            self._db.execute(
                "INSERT INTO semantic_cache "
                "(query, query_hash, context_hash, response, embedding, model_name, "
                "created_at, response_tokens_est) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (query, query_hash, context_hash, response, json.dumps(emb),
                 model_name, time.time(), tokens_est),
            )
            self._db.commit()
            self._stats.stores += 1
            self._maybe_evict()
            return True
        except Exception as e:
            logger.warning("semantic cache store failed: %s", e)
            return False

    def _maybe_evict(self) -> None:
        """Evict oldest entries if over max_entries."""
        if not self._db:
            return
        try:
            count = self._db.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0]
            if count > self.max_entries:
                excess = count - self.max_entries
                self._db.execute(
                    "DELETE FROM semantic_cache WHERE id IN "
                    "(SELECT id FROM semantic_cache ORDER BY last_hit_at ASC, created_at ASC LIMIT ?)",
                    (excess,),
                )
                self._db.commit()
        except Exception as e:
            logger.warning("semantic cache eviction failed: %s", e)

    def invalidate_by_context(self, context_hash: str) -> int:
        """Invalidate all entries matching a context hash. Returns count removed."""
        if not self._db:
            return 0
        try:
            cursor = self._db.execute(
                "DELETE FROM semantic_cache WHERE context_hash = ?", (context_hash,),
            )
            self._db.commit()
            n = cursor.rowcount
            self._stats.invalidations += n
            return n
        except Exception as e:
            logger.warning("semantic cache invalidation failed: %s", e)
            return 0

    def invalidate_all(self) -> int:
        """Clear entire cache. Returns count removed."""
        if not self._db:
            return 0
        try:
            count = self._db.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0]
            self._db.execute("DELETE FROM semantic_cache")
            self._db.commit()
            self._stats.invalidations += count
            return count
        except Exception as e:
            logger.warning("semantic cache clear failed: %s", e)
            return 0

    def invalidate_expired(self) -> int:
        """Remove TTL-expired entries."""
        if not self._db:
            return 0
        cutoff = time.time() - self.ttl
        try:
            cursor = self._db.execute(
                "DELETE FROM semantic_cache WHERE created_at < ?", (cutoff,),
            )
            self._db.commit()
            n = cursor.rowcount
            self._stats.invalidations += n
            return n
        except Exception as e:
            logger.warning("semantic cache ttl cleanup failed: %s", e)
            return 0

    def record_savings(self, response_text: str, cost_per_1k: float = 0.001) -> None:
        """Record estimated savings from a cache hit."""
        tokens_est = len(response_text) // 4
        self._stats.estimated_tokens_saved += tokens_est
        self._stats.estimated_cost_saved_usd += (tokens_est / 1000) * cost_per_1k

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        entry_count = 0
        if self._db:
            try:
                entry_count = self._db.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0]
            except Exception:
                pass
        return {
            "lookups": self._stats.lookups,
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "hit_rate": round(self._stats.hit_rate, 4),
            "stores": self._stats.stores,
            "invalidations": self._stats.invalidations,
            "entries": entry_count,
            "estimated_tokens_saved": self._stats.estimated_tokens_saved,
            "estimated_cost_saved_usd": round(self._stats.estimated_cost_saved_usd, 6),
            "threshold": self.threshold,
            "ttl_seconds": self.ttl,
        }

    def close(self) -> None:
        if self._db:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None


# ── context hashing ─────────────────────────────────────────────────

def compute_context_hash(
    context_files: Optional[List[str]] = None,
    pinned_context_files: Optional[List[str]] = None,
    model_name: str = "",
    system_prompt_hash: Optional[str] = None,
    tool_schema_hash: Optional[str] = None,
    rules_hash: Optional[str] = None,
) -> str:
    """Compute a deterministic hash over the active context.

    Folds in a sha256 content fingerprint for every referenced file
    (memoized by mtime+size in `file_cache`, so unchanged files cost
    one stat call per lookup), plus optional hashes for the system
    prompt, active tool schema, and active rules/memory so any change
    to those invalidates the response cache.

    Edits to a file invalidate the key even if the path stays the
    same — the stale-answer class of bug from LEARNING.md §2.1.
    """
    # Local import to avoid circular import at module load time.
    from .file_cache import content_fingerprint

    parts: List[str] = [f"m={model_name}"]
    all_files = sorted(set((context_files or []) + (pinned_context_files or [])))
    for fp in all_files:
        fprint = content_fingerprint(fp)
        parts.append(f"{fp}\x00{fprint}\x01")
    if system_prompt_hash:
        parts.append(f"sp={system_prompt_hash}")
    if tool_schema_hash:
        parts.append(f"ts={tool_schema_hash}")
    if rules_hash:
        parts.append(f"rules={rules_hash}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:24]


# ── singleton ───────────────────────────────────────────────────────

_instance: Optional[SemanticCache] = None


def get_semantic_cache(
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> SemanticCache:
    """Get or create the global SemanticCache singleton."""
    global _instance
    if _instance is None:
        _instance = SemanticCache(
            similarity_threshold=similarity_threshold,
            ttl_seconds=ttl_seconds,
        )
    return _instance


def reset_semantic_cache() -> None:
    """Close and discard the global instance (for tests)."""
    global _instance
    if _instance:
        _instance.close()
    _instance = None
