from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data.parsers.lecard_parser import (
    attach_candidate_charges,
    build_candidate_charge_map,
    build_corpus,
    discover_lecard_data_root,
    load_all_candidates,
    load_baseline_predictions,
    load_criminal_charges,
    load_labels,
    load_queries,
    load_stopwords,
)
from ml.evaluation.lecard_eval import evaluate_predictions
from ml.retrieval.case_retrieval import (
    DEFAULT_BIENCODER_MODEL,
    DEFAULT_CROSS_ENCODER_MODEL,
    CaseRetrievalPipeline,
)

DEFAULT_METRICS_PATH = "models/case-retrieval/eval_results.json"
PUBLISHED_BASELINES = {
    "BM25": {"NDCG@10": 0.731, "NDCG@20": 0.773, "NDCG@30": 0.812, "P@5": 0.640, "P@10": 0.580, "MAP": 0.484},
    "TFIDF": {"NDCG@10": 0.715, "NDCG@20": 0.759, "NDCG@30": 0.800, "P@5": 0.626, "P@10": 0.570, "MAP": 0.471},
    "LM": {"NDCG@10": 0.728, "NDCG@20": 0.768, "NDCG@30": 0.807, "P@5": 0.637, "P@10": 0.575, "MAP": 0.479},
    "BERT": {"NDCG@10": 0.830, "NDCG@20": 0.867, "NDCG@30": 0.899, "P@5": 0.746, "P@10": 0.668, "MAP": 0.568},
}


class CaseRetrievalService:
    def __init__(
        self,
        pipeline: CaseRetrievalPipeline,
        corpus: dict[str, dict[str, Any]],
        known_charges: list[str],
        labels: dict[str, dict[str, int]],
        baseline_predictions: dict[str, dict[str, list[str]]],
        metrics_path: str | Path = DEFAULT_METRICS_PATH,
    ):
        self.pipeline = pipeline
        self.corpus = corpus
        self.known_charges = sorted(set(known_charges))
        self.labels = labels
        self.baseline_predictions = baseline_predictions
        self.metrics_path = Path(metrics_path)

    def search_cases(
        self,
        query: str,
        top_k: int = 10,
        stages: list[str] | None = None,
        include_scores: bool = True,
    ) -> dict[str, Any]:
        payload = self.pipeline.search(query_text=query, top_k=top_k, stages=stages)
        results = payload["results"]
        if not include_scores:
            for row in results:
                row.pop("relevance_score", None)
        return {
            "query": query,
            "results": results,
            "retrieval_info": payload["retrieval_info"],
        }

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        row = self.corpus.get(case_id)
        if row is None:
            return None
        return {
            "case_id": case_id,
            "ajId": row.get("ajId", ""),
            "case_name": row.get("ajName", ""),
            "facts": row.get("ajjbqk", ""),
            "judgment": row.get("pjjg", ""),
            "full_text": row.get("qw", ""),
            "charges": row.get("charges", []),
            "writ_id": row.get("writId", ""),
            "writ_name": row.get("writName", ""),
        }

    def list_charges(self) -> list[str]:
        charges = set(self.known_charges)
        for row in self.corpus.values():
            for charge in row.get("charges", []):
                charge_str = str(charge).strip()
                if charge_str:
                    charges.add(charge_str)
        return sorted(charges)

    def get_metrics(self) -> dict[str, Any]:
        latest: dict[str, Any] | None = None
        if self.metrics_path.exists() and self.metrics_path.is_file():
            try:
                latest = json.loads(self.metrics_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                latest = None

        computed_baselines = {
            name.upper(): evaluate_predictions(predictions, self.labels)
            for name, predictions in self.baseline_predictions.items()
            if predictions
        }

        return {
            "published": PUBLISHED_BASELINES,
            "computed_baselines": computed_baselines,
            "latest": latest,
        }


def create_case_retrieval_service(
    data_root: str | Path | None = None,
    qdrant_url: str = "http://localhost:6333",
    biencoder_model_path: str = DEFAULT_BIENCODER_MODEL,
    cross_encoder_model_path: str = DEFAULT_CROSS_ENCODER_MODEL,
    metrics_path: str | Path = DEFAULT_METRICS_PATH,
) -> CaseRetrievalService | None:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    if not root.exists() or not root.is_dir():
        return None

    queries = load_queries(root)
    labels = load_labels(root)
    all_candidates = load_all_candidates(queries, root)
    corpus = build_corpus(all_candidates)
    if not corpus:
        return None

    charge_map = build_candidate_charge_map(queries, all_candidates)
    corpus = attach_candidate_charges(corpus, charge_map)

    pipeline = CaseRetrievalPipeline(
        corpus=corpus,
        stopwords=load_stopwords(root),
        qdrant_url=qdrant_url,
        biencoder_model_path=biencoder_model_path,
        cross_encoder_model_path=cross_encoder_model_path,
    )

    return CaseRetrievalService(
        pipeline=pipeline,
        corpus=corpus,
        known_charges=load_criminal_charges(root),
        labels=labels,
        baseline_predictions=load_baseline_predictions(root),
        metrics_path=metrics_path,
    )
