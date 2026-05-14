from __future__ import annotations

import asyncio
import importlib
from typing import Any

from prefect import flow, task

from data.parsers.lecard_parser import (
    attach_candidate_charges,
    build_candidate_charge_map,
    build_corpus,
    discover_lecard_data_root,
    load_all_candidates,
    load_criminal_charges,
    load_labels,
    load_queries,
    load_stopwords,
    unzip_candidates,
)
from ml.retrieval.case_retrieval import index_corpus_to_qdrant

INDEX_NAME = "junas_cases"
ES_BATCH_SIZE = 200

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "zh_text": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "cjk_width"],
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "case_id": {"type": "keyword"},
            "ajId": {"type": "keyword"},
            "ajName": {"type": "text", "analyzer": "zh_text"},
            "ajjbqk": {"type": "text", "analyzer": "zh_text"},
            "pjjg": {"type": "text", "analyzer": "zh_text"},
            "qw": {"type": "text", "index": False},
            "writId": {"type": "keyword"},
            "writName": {"type": "text", "analyzer": "zh_text"},
            "charges": {"type": "keyword"},
        }
    },
}


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None
    if attr_name is None:
        return module
    return getattr(module, attr_name, None)


AsyncElasticsearch = _optional_import("elasticsearch", "AsyncElasticsearch")


@task
def prepare_dataset(data_root: str | None = None) -> dict[str, Any]:
    root = discover_lecard_data_root() if data_root is None else data_root
    unzip_candidates(root)
    queries = load_queries(root)
    labels = load_labels(root)
    all_candidates = load_all_candidates(queries, root)
    corpus = build_corpus(all_candidates)
    charge_map = build_candidate_charge_map(queries, all_candidates)
    corpus = attach_candidate_charges(corpus, charge_map)
    stopwords = load_stopwords(root)
    known_charges = load_criminal_charges(root)

    return {
        "data_root": str(root),
        "queries": queries,
        "labels": labels,
        "all_candidates": all_candidates,
        "corpus": corpus,
        "stopwords": stopwords,
        "known_charges": known_charges,
    }


@task
async def create_case_index(es: Any) -> None:
    if await es.indices.exists(index=INDEX_NAME):
        await es.indices.delete(index=INDEX_NAME)
    await es.indices.create(index=INDEX_NAME, body=MAPPING)


@task
async def index_case_batch(es: Any, batch: list[dict[str, Any]]) -> int:
    operations: list[dict[str, Any]] = []
    for row in batch:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            continue
        operations.append({"index": {"_index": INDEX_NAME, "_id": case_id}})
        operations.append(
            {
                "case_id": case_id,
                "ajId": row.get("ajId", ""),
                "ajName": row.get("ajName", ""),
                "ajjbqk": row.get("ajjbqk", ""),
                "pjjg": row.get("pjjg", ""),
                "qw": row.get("qw", ""),
                "writId": row.get("writId", ""),
                "writName": row.get("writName", ""),
                "charges": row.get("charges", []),
            }
        )
    if operations:
        await es.bulk(operations=operations, refresh=False)
    return len(batch)


@flow(name="ingest-lecard")
async def ingest_lecard(data_root: str | None = None) -> dict[str, Any]:
    if AsyncElasticsearch is None:
        raise RuntimeError("elasticsearch client is not installed")

    prepared = prepare_dataset(data_root)
    corpus = prepared["corpus"]
    corpus_rows = list(corpus.values())

    es = AsyncElasticsearch("http://localhost:9200")
    await create_case_index(es)
    for start in range(0, len(corpus_rows), ES_BATCH_SIZE):
        batch = corpus_rows[start : start + ES_BATCH_SIZE]
        await index_case_batch(es, batch)
    await es.indices.refresh(index=INDEX_NAME)
    await es.close()

    qdrant_vectors = 0
    qdrant_status = "skipped"
    try:
        qdrant_vectors = index_corpus_to_qdrant(corpus)
        qdrant_status = "indexed"
    except Exception as exc:
        qdrant_status = f"skipped: {exc}"

    return {
        "queries": len(prepared["queries"]),
        "labels": len(prepared["labels"]),
        "corpus_documents": len(corpus),
        "known_charges": len(prepared["known_charges"]),
        "qdrant_vectors": qdrant_vectors,
        "qdrant_status": qdrant_status,
    }


def run() -> dict[str, Any]:
    return asyncio.run(ingest_lecard())


if __name__ == "__main__":
    print(run())
