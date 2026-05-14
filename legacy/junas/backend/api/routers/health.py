from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request

from api.services.readiness import collect_service_health

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, dict[str, bool]]:
    services = await collect_service_health(request.app)
    return {"services": services}


async def _collect_indices(es_client: Any, index_names: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    if es_client is None:
        return output

    for index_name in index_names:
        try:
            count_response = await es_client.count(index=index_name)
            doc_count = int(count_response.get("count", 0) or 0)
        except Exception:
            output[index_name] = {"doc_count": 0, "status": "unavailable"}
            continue

        try:
            health_response = await es_client.cluster.health(index=index_name, level="indices")
            status = str(health_response.get("status") or "unknown")
        except Exception:
            status = "unknown"

        output[index_name] = {
            "doc_count": doc_count,
            "status": status,
        }

    return output


async def _collect_qdrant_collections(client: Any, collection_names: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    if client is None:
        return output

    for name in collection_names:
        try:
            info = await client.get_collection(name)
            vectors_count = getattr(info, "vectors_count", None)
            if vectors_count is None and hasattr(info, "result"):
                vectors_count = getattr(info.result, "vectors_count", None)
            output[name] = {"vectors_count": int(vectors_count or 0)}
        except Exception:
            output[name] = {"vectors_count": 0}

    return output


async def _count_rows(pool: Any, table_name: str) -> int:
    if pool is None:
        return 0
    try:
        async with pool.acquire() as connection:
            value = await connection.fetchval(f"SELECT COUNT(*) FROM {table_name}")
        return int(value or 0)
    except Exception:
        return 0


@router.get("/metrics")
async def metrics(request: Request) -> dict[str, Any]:
    app = request.app
    start_time = float(getattr(app.state, "start_time", time.time()))
    uptime_seconds = max(0, int(time.time() - start_time))

    models_loaded: list[str] = []
    if getattr(app.state, "entity_extractor", None) is not None:
        models_loaded.append("ner-german-legal")
    if getattr(app.state, "contract_classifier", None) is not None:
        models_loaded.append("ledgar-classifier")
    if getattr(app.state, "tos_scanner", None) is not None:
        models_loaded.append("unfair-tos-classifier")
    if getattr(app.state, "court_predictor", None) is not None:
        models_loaded.append("court-prediction-suite")
    if getattr(app.state, "rome_statute_service", None) is not None:
        models_loaded.append("rome-statute-service")

    indices = await _collect_indices(
        getattr(app.state, "elasticsearch", None),
        ["junas_glossary", "junas_statutes", "junas_rome_statute"],
    )
    qdrant_collections = await _collect_qdrant_collections(
        getattr(app.state, "qdrant", None),
        ["junas_statutes", "lecard_cases", "junas_rome_statute"],
    )

    pg_pool = getattr(app.state, "pg_pool", None)
    benchmark_runs = await _count_rows(pg_pool, "benchmark_runs")
    conversations = await _count_rows(pg_pool, "conversations")

    return {
        "uptime_seconds": uptime_seconds,
        "models_loaded": models_loaded,
        "indices": indices,
        "qdrant_collections": qdrant_collections,
        "benchmark_runs": benchmark_runs,
        "conversations": conversations,
    }
