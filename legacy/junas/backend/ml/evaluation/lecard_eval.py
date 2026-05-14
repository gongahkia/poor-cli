from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.config import get_settings
from data.parsers.lecard_parser import (
    attach_candidate_charges,
    build_candidate_charge_map,
    build_corpus,
    discover_lecard_data_root,
    load_all_candidates,
    load_baseline_predictions,
    load_labels,
    load_queries,
    load_stopwords,
)
from ml.retrieval.case_retrieval import CaseRetrievalPipeline


def _optional_import(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def _database_url_for_asyncpg(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def ndcg_at_k(predicted_ids: list[str], label_map: dict[str, int], k: int) -> float:
    ideal = sorted(label_map.values(), reverse=True)[:k]
    if not ideal or sum(ideal) == 0:
        return 0.0

    gains = [label_map.get(str(case_id), 0) for case_id in predicted_ids[:k]]
    if len(gains) < k:
        gains.extend([0] * (k - len(gains)))

    dcg = 0.0
    idcg = 0.0
    for idx in range(k):
        discount = math.log2(idx + 2)
        dcg += gains[idx] / discount
        idcg += ideal[idx] / discount
    return dcg / idcg if idcg > 0 else 0.0


def precision_at_k(predicted_ids: list[str], label_map: dict[str, int], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = 0
    for case_id in predicted_ids[:k]:
        if label_map.get(str(case_id), 0) == 3:
            hits += 1
    return hits / k


def mean_average_precision(predictions: dict[str, list[str]], labels: dict[str, dict[str, int]]) -> float:
    ap_values: list[float] = []
    for ridx, label_map in labels.items():
        predicted = [case_id for case_id in predictions.get(ridx, []) if case_id in label_map]
        relevant_total = sum(1 for score in label_map.values() if int(score) == 3)
        if relevant_total == 0:
            ap_values.append(0.0)
            continue

        score_sum = 0.0
        hit_count = 0
        for rank, case_id in enumerate(predicted, start=1):
            if int(label_map.get(case_id, 0)) == 3:
                hit_count += 1
                score_sum += hit_count / rank
        ap_values.append(score_sum / relevant_total if hit_count else 0.0)
    return sum(ap_values) / len(ap_values) if ap_values else 0.0


def evaluate_predictions(predictions: dict[str, list[str]], labels: dict[str, dict[str, int]]) -> dict[str, float]:
    query_ids = [query_id for query_id in labels.keys() if query_id in predictions]
    if not query_ids:
        return {
            "NDCG@10": 0.0,
            "NDCG@20": 0.0,
            "NDCG@30": 0.0,
            "P@5": 0.0,
            "P@10": 0.0,
            "MAP": 0.0,
        }

    ndcg10 = sum(ndcg_at_k(predictions[qid], labels[qid], 10) for qid in query_ids) / len(query_ids)
    ndcg20 = sum(ndcg_at_k(predictions[qid], labels[qid], 20) for qid in query_ids) / len(query_ids)
    ndcg30 = sum(ndcg_at_k(predictions[qid], labels[qid], 30) for qid in query_ids) / len(query_ids)
    p5 = sum(precision_at_k(predictions[qid], labels[qid], 5) for qid in query_ids) / len(query_ids)
    p10 = sum(precision_at_k(predictions[qid], labels[qid], 10) for qid in query_ids) / len(query_ids)
    map_score = mean_average_precision({qid: predictions[qid] for qid in query_ids}, labels)

    return {
        "NDCG@10": ndcg10,
        "NDCG@20": ndcg20,
        "NDCG@30": ndcg30,
        "P@5": p5,
        "P@10": p10,
        "MAP": map_score,
    }


def _run_junas_predictions(
    queries: list[dict[str, Any]],
    pipeline: CaseRetrievalPipeline,
    stages: list[str],
) -> dict[str, list[str]]:
    predictions: dict[str, list[str]] = {}
    for query in queries:
        ridx = str(query.get("ridx", "")).strip()
        query_text = str(query.get("q", "")).strip()
        if not ridx or not query_text:
            continue
        response = pipeline.search(query_text=query_text, top_k=30, stages=stages)
        predictions[ridx] = [str(result["case_id"]) for result in response["results"]]
    return predictions


async def _register_metrics_in_db(
    payload: dict[str, Any],
    database_url: str,
    model_path: str,
) -> bool:
    asyncpg = _optional_import("asyncpg")
    if asyncpg is None:
        return False

    connection = None
    try:
        connection = await asyncpg.connect(_database_url_for_asyncpg(database_url))
        await connection.execute(
            """
            INSERT INTO models(name, task, dataset_name, model_path, metrics, status)
            VALUES($1, $2, $3, $4, $5::jsonb, $6)
            """,
            "case-retrieval-junas",
            "case_retrieval",
            "LeCaRD",
            model_path,
            json.dumps(payload, ensure_ascii=False),
            "ready",
        )
        return True
    except Exception:
        return False
    finally:
        if connection is not None:
            await connection.close()


def evaluate_lecard(
    data_root: str | Path | None = None,
    output_path: str | Path = "models/case-retrieval/eval_results.json",
    include_junas: bool = True,
    database_url: str | None = None,
) -> dict[str, Any]:
    root = Path(data_root) if data_root is not None else discover_lecard_data_root()
    labels = load_labels(root)
    baselines = load_baseline_predictions(root)

    baseline_metrics = {
        name.upper(): evaluate_predictions(prediction_rows, labels)
        for name, prediction_rows in baselines.items()
        if prediction_rows
    }

    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_root": str(root),
        "query_count": len(labels),
        "baselines": baseline_metrics,
    }

    if include_junas:
        queries = load_queries(root)
        all_candidates = load_all_candidates(queries, root)
        corpus = build_corpus(all_candidates)
        charge_map = build_candidate_charge_map(queries, all_candidates)
        corpus = attach_candidate_charges(corpus, charge_map)
        pipeline = CaseRetrievalPipeline(corpus=corpus, stopwords=load_stopwords(root))

        bm25_predictions = _run_junas_predictions(queries, pipeline, stages=["bm25"])
        full_predictions = _run_junas_predictions(queries, pipeline, stages=["bm25", "dense", "rerank"])

        payload["junas"] = {
            "bm25_only": evaluate_predictions(bm25_predictions, labels),
            "three_stage": evaluate_predictions(full_predictions, labels),
            "query_count": len(queries),
            "corpus_size": len(corpus),
        }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(output)

    settings = get_settings()
    resolved_db_url = database_url or settings.database_url
    loop = asyncio.new_event_loop()
    try:
        payload["registered_in_db"] = bool(
            loop.run_until_complete(
                _register_metrics_in_db(payload=payload, database_url=resolved_db_url, model_path=str(output.parent))
            )
        )
    finally:
        loop.close()

    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Junas LeCaRD retrieval metrics")
    parser.add_argument("--data-root", type=str, default=None)
    parser.add_argument("--output", type=str, default="models/case-retrieval/eval_results.json")
    parser.add_argument("--skip-junas", action="store_true")
    parser.add_argument("--database-url", type=str, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = evaluate_lecard(
        data_root=args.data_root,
        output_path=args.output,
        include_junas=not args.skip_junas,
        database_url=args.database_url,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
