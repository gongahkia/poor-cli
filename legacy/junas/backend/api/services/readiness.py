import asyncio
from typing import Any

from fastapi import FastAPI


async def _check_postgres(pool: Any) -> bool:
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False


async def _check_elasticsearch(client: Any) -> bool:
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        return False


async def _check_qdrant(client: Any) -> bool:
    if client is None:
        return False
    try:
        await client.get_collections()
        return True
    except Exception:
        return False


async def _check_redis(client: Any) -> bool:
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        return False


async def collect_service_health(app: FastAPI) -> dict[str, bool]:
    checks = await asyncio.gather(
        _check_postgres(getattr(app.state, "pg_pool", None)),
        _check_elasticsearch(getattr(app.state, "elasticsearch", None)),
        _check_qdrant(getattr(app.state, "qdrant", None)),
        _check_redis(getattr(app.state, "redis", None)),
    )
    return {
        "postgres": checks[0],
        "elasticsearch": checks[1],
        "qdrant": checks[2],
        "redis": checks[3],
    }


def service_clients_from_state(app: FastAPI) -> dict[str, Any]:
    return {
        "postgres": getattr(app.state, "pg_pool", None),
        "elasticsearch": getattr(app.state, "elasticsearch", None),
        "qdrant": getattr(app.state, "qdrant", None),
        "redis": getattr(app.state, "redis", None),
    }
