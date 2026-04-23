"""Level-of-detail memory retrieval."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .memory import MemoryEntry, MemoryManager


@dataclass
class LODConfig:
    alpha: float = 0.65
    full_threshold: float = 0.72
    summary_threshold: float = 0.42
    decay_lambda: float = 0.03
    max_full: int = 8
    max_summary: int = 32


@dataclass
class LODMemoryResult:
    entry: MemoryEntry
    tier: str
    semantic_score: float
    recency_score: float
    lod_score: float

    def surface(self) -> str:
        if self.tier == "full":
            return self.entry.content
        if self.tier == "summary":
            return self.entry.summary or self.entry.description or self.entry.headline
        return self.entry.headline or self.entry.description or self.entry.name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.entry.name,
            "filename": self.entry.filename,
            "type": self.entry.type,
            "tier": self.tier,
            "headline": self.entry.headline,
            "summary": self.entry.summary,
            "content": self.surface(),
            "semanticScore": round(self.semantic_score, 4),
            "recencyScore": round(self.recency_score, 4),
            "lodScore": round(self.lod_score, 4),
            "hitCount": self.entry.hit_count,
            "lastAccessedAt": self.entry.last_accessed_at,
            "pinned": self.entry.pinned,
        }


def _days_since(iso_text: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_text.replace("Z", "+00:00"))
    except ValueError:
        return 365.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86_400.0)


def recency_score(entry: MemoryEntry, cfg: Optional[LODConfig] = None) -> float:
    cfg = cfg or LODConfig()
    days = _days_since(entry.last_accessed_at or entry.updated_at or entry.created_at)
    frequency = math.log1p(max(0, entry.hit_count))
    return max(0.0, min(1.0, math.exp(-cfg.decay_lambda * days / (1.0 + frequency))))


def tier_for_score(score: float, *, entry: MemoryEntry, cfg: LODConfig) -> str:
    if entry.pinned:
        return "full"
    if score >= cfg.full_threshold:
        return "full"
    if score >= cfg.summary_threshold:
        return "summary"
    return "headline"


async def search_lod(
    manager: MemoryManager,
    query: str,
    *,
    max_results: int = 100,
    alpha: float = 0.65,
    record_hits: bool = True,
) -> List[LODMemoryResult]:
    """Return mixed-resolution memory results for a query."""
    if not manager._entries:  # type: ignore[reportPrivateUsage]
        manager.load()
    cfg = LODConfig(alpha=max(0.0, min(1.0, alpha)))
    semantic_scores: Dict[str, float] = {}
    try:
        from .memory_semantic import semantic_search
        semantic_hits = await semantic_search(
            manager,
            query,
            max_results=max(max_results, 1),
            threshold=0.0,
        )
        semantic_scores = {entry.filename: float(score) for entry, score in semantic_hits}
    except Exception:
        semantic_scores = {}

    keyword_hits = manager.search(query, max_results=max_results, record_hits=False)
    entries: List[MemoryEntry]
    if semantic_scores:
        by_name = dict(manager._entries)  # type: ignore[reportPrivateUsage]
        ordered = [by_name[name] for name in semantic_scores if name in by_name]
        seen = {entry.filename for entry in ordered}
        ordered.extend(entry for entry in keyword_hits if entry.filename not in seen)
        entries = ordered[:max_results]
    else:
        entries = keyword_hits[:max_results]
        for idx, entry in enumerate(entries):
            semantic_scores[entry.filename] = max(0.0, 1.0 - (idx / max(len(entries), 1)))

    results: List[LODMemoryResult] = []
    full_count = 0
    summary_count = 0
    for entry in entries:
        semantic = max(0.0, min(1.0, semantic_scores.get(entry.filename, 0.0)))
        recency = recency_score(entry, cfg)
        score = cfg.alpha * semantic + (1.0 - cfg.alpha) * recency
        tier = tier_for_score(score, entry=entry, cfg=cfg)
        if tier == "full":
            full_count += 1
            if full_count > cfg.max_full:
                tier = "summary"
        if tier == "summary":
            summary_count += 1
            if summary_count > cfg.max_summary:
                tier = "headline"
        results.append(LODMemoryResult(entry, tier, semantic, recency, score))
    if record_hits:
        manager._record_retrieval([result.entry for result in results])  # type: ignore[reportPrivateUsage]
    return results


def expand_memory(manager: MemoryManager, name_or_filename: str) -> Optional[MemoryEntry]:
    if not manager._entries:  # type: ignore[reportPrivateUsage]
        manager.load()
    entry = manager.get(name_or_filename, record_hit=True)
    if entry is not None:
        return entry
    return manager._entries.get(name_or_filename)  # type: ignore[reportPrivateUsage]


def promote_memory(manager: MemoryManager, name_or_filename: str, *, pin: bool = True) -> Optional[MemoryEntry]:
    entry = expand_memory(manager, name_or_filename)
    if entry is None:
        return None
    entry.pinned = pin
    entry.touch()
    return manager.save(entry)


def render_lod_results(results: List[LODMemoryResult]) -> str:
    if not results:
        return "no memories found"
    chunks = []
    for result in results:
        chunks.append(
            f"## {result.entry.name} [{result.tier}] score={result.lod_score:.2f}\n"
            f"{result.surface()}"
        )
    return "\n\n---\n\n".join(chunks)
