"""Repo-graph weighted file selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import FileContext

DEFAULT_SELECTION_WEIGHTS = {"alpha": 0.4, "beta": 0.4, "gamma": 0.2}
FALLBACK_SELECTION_WEIGHTS = {"alpha": 0.6, "beta": 0.0, "gamma": 0.4}


@dataclass(frozen=True)
class SelectionWeights:
    alpha: float = DEFAULT_SELECTION_WEIGHTS["alpha"]
    beta: float = DEFAULT_SELECTION_WEIGHTS["beta"]
    gamma: float = DEFAULT_SELECTION_WEIGHTS["gamma"]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "SelectionWeights":
        data = data or {}
        return cls(
            alpha=_coerce_weight(data, "alpha", "recency", default=DEFAULT_SELECTION_WEIGHTS["alpha"]),
            beta=_coerce_weight(data, "beta", "pagerank", default=DEFAULT_SELECTION_WEIGHTS["beta"]),
            gamma=_coerce_weight(data, "gamma", "import_distance", default=DEFAULT_SELECTION_WEIGHTS["gamma"]),
        )

    def to_dict(self) -> dict[str, float]:
        return {"alpha": self.alpha, "beta": self.beta, "gamma": self.gamma}


@dataclass(frozen=True)
class RankedFileCandidate:
    file: FileContext
    score: float
    recency_score: float
    pagerank_score: float
    import_distance_score: float


class FileSelector:
    """Rank FileContext candidates by recency, PageRank, and graph adjacency."""

    def __init__(
        self,
        *,
        repo_graph: Any = None,
        weights: SelectionWeights | Mapping[str, Any] | None = None,
        graph_ready: bool = True,
    ) -> None:
        self.repo_graph = repo_graph
        base_weights = (
            weights
            if isinstance(weights, SelectionWeights)
            else SelectionWeights.from_mapping(weights)
        )
        self.weights = (
            base_weights
            if graph_ready and repo_graph is not None
            else SelectionWeights.from_mapping(FALLBACK_SELECTION_WEIGHTS)
        )

    def rank(
        self,
        candidates: Sequence[FileContext],
        *,
        prompt: str = "",
        pinned_paths: Sequence[str] = (),
        seed_paths: Sequence[str] = (),
    ) -> list[RankedFileCandidate]:
        del prompt
        normalized_pins = {_resolve_path(path) for path in pinned_paths}
        normalized_seeds = [_resolve_path(path) for path in seed_paths]
        recency = self._recency_scores(candidates)
        adjacency = self._import_distance_scores(candidates, normalized_seeds)
        ranked: list[RankedFileCandidate] = []
        for file_ctx in candidates:
            path = _resolve_path(file_ctx.path)
            pr_score = self._pagerank_score(path)
            score = (
                self.weights.alpha * recency.get(path, 0.0)
                + self.weights.beta * pr_score
                + self.weights.gamma * adjacency.get(path, 0.0)
            )
            if path in normalized_pins:
                score += 1_000_000.0
                file_ctx.selection_reason = "pinned"
            else:
                file_ctx.selection_reason = self._reason(file_ctx, pr_score, adjacency.get(path, 0.0))
            file_ctx.priority = score
            ranked.append(
                RankedFileCandidate(
                    file=file_ctx,
                    score=score,
                    recency_score=recency.get(path, 0.0),
                    pagerank_score=pr_score,
                    import_distance_score=adjacency.get(path, 0.0),
                )
            )
        return sorted(ranked, key=lambda item: (-item.score, item.file.path))

    def _pagerank_score(self, path: str) -> float:
        if self.repo_graph is None or self.weights.beta <= 0.0:
            return 0.0
        scorer = getattr(self.repo_graph, "pagerank_score", None)
        if scorer is None:
            return 0.0
        try:
            return max(0.0, min(1.0, float(scorer(path))))
        except Exception:
            return 0.0

    def _import_distance_scores(
        self,
        candidates: Sequence[FileContext],
        seed_paths: Sequence[str],
    ) -> dict[str, float]:
        paths = {_resolve_path(candidate.path) for candidate in candidates}
        if not paths or not seed_paths:
            return {path: 0.0 for path in paths}
        scores = {path: 1.0 for path in seed_paths if path in paths}
        related = getattr(self.repo_graph, "files_related_to", None)
        if self.repo_graph is not None and related is not None:
            for seed_path in seed_paths[:10]:
                try:
                    for related_path, raw_score in related(seed_path, max_depth=2):
                        normalized = _resolve_path(related_path)
                        if normalized in paths:
                            scores[normalized] = max(scores.get(normalized, 0.0), float(raw_score))
                except Exception:
                    continue
        for candidate in candidates:
            path = _resolve_path(candidate.path)
            if path not in scores and getattr(candidate, "source", "") == "graph":
                scores[path] = 0.5
        max_score = max(scores.values(), default=0.0)
        if max_score <= 0.0:
            return {path: 0.0 for path in paths}
        return {
            path: min(1.0, max(0.0, scores.get(path, 0.0) / max_score))
            for path in paths
        }

    def _recency_scores(self, candidates: Sequence[FileContext]) -> dict[str, float]:
        if not candidates:
            return {}
        mtimes = {
            _resolve_path(candidate.path): float(
                getattr(candidate, "modified_time", 0.0) or 0.0
            )
            for candidate in candidates
        }
        min_mtime = min(mtimes.values())
        max_mtime = max(mtimes.values())
        if max_mtime <= min_mtime:
            return {path: 1.0 for path in mtimes}
        return {path: (mtime - min_mtime) / (max_mtime - min_mtime) for path, mtime in mtimes.items()}

    @staticmethod
    def _reason(file_ctx: FileContext, pagerank: float, import_distance: float) -> str:
        if import_distance > 0.0:
            return "import-adjacent"
        if pagerank > 0.0:
            return "pagerank-hub"
        if getattr(file_ctx, "source", "") == "git":
            return "recent-open"
        return str(getattr(file_ctx, "selection_reason", "") or getattr(file_ctx, "source", "") or "selected")


def _coerce_weight(data: Mapping[str, Any], primary: str, alias: str, *, default: float) -> float:
    raw = data.get(primary, data.get(alias, default))
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return default


def _resolve_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())
