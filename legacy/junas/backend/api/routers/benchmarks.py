from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from api.celery_app import celery
from api.config import get_settings
from api.services.benchmarks import BenchmarkService

router = APIRouter(prefix="/benchmarks")


class BenchmarkRunRequest(BaseModel):
    model_name: str = Field(..., min_length=1)
    run_name: str = Field(..., min_length=1, max_length=100)
    tasks: list[str] | None = None
    model_path: str | None = None

    @field_validator("model_name", "run_name")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("tasks")
    @classmethod
    def _validate_tasks(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned:
            return None
        ordered: list[str] = []
        seen: set[str] = set()
        for item in cleaned:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered


class BenchmarkRegisterRequest(BaseModel):
    model_name: str = Field(..., min_length=1)
    run_name: str = Field(..., min_length=1, max_length=100)
    task: str = Field(..., min_length=1)
    micro_f1: float = Field(..., ge=0.0, le=1.0)
    macro_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None

    @field_validator("model_name", "run_name", "task")
    @classmethod
    def _validate_non_empty_value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


def get_benchmark_service(request: Request) -> BenchmarkService:
    service = getattr(request.app.state, "benchmark_service", None)
    if isinstance(service, BenchmarkService):
        return service

    settings = get_settings()
    service = BenchmarkService(
        database_url=settings.database_url,
        pg_pool=getattr(request.app.state, "pg_pool", None),
        celery_app=celery,
    )
    request.app.state.benchmark_service = service
    return service


@router.post("/run")
async def run_benchmark(
    body: BenchmarkRunRequest,
    service: BenchmarkService = Depends(get_benchmark_service),
) -> dict[str, Any]:
    try:
        return await service.create_run(
            model_name=body.model_name,
            run_name=body.run_name,
            tasks=body.tasks,
            model_path=body.model_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Benchmark run could not be started: {exc}") from exc


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=100, ge=1, le=500),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> dict[str, Any]:
    try:
        runs = await service.list_runs(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to list benchmark runs: {exc}") from exc
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_run_detail(
    run_id: str,
    service: BenchmarkService = Depends(get_benchmark_service),
) -> dict[str, Any]:
    try:
        payload = await service.get_run(run_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to load benchmark run: {exc}") from exc

    if payload is None:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return payload


@router.get("/leaderboard")
async def get_leaderboard(
    task: str | None = Query(default=None),
    sort_by: str = Query(default="avg_micro_f1"),
    service: BenchmarkService = Depends(get_benchmark_service),
) -> dict[str, Any]:
    try:
        return await service.leaderboard(task=task, sort_by=sort_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to load leaderboard: {exc}") from exc


@router.get("/tasks")
async def list_tasks(service: BenchmarkService = Depends(get_benchmark_service)) -> dict[str, Any]:
    return {"tasks": await service.list_tasks()}


@router.post("/register")
async def register_benchmark_result(
    body: BenchmarkRegisterRequest,
    service: BenchmarkService = Depends(get_benchmark_service),
) -> dict[str, Any]:
    try:
        return await service.register_run_result(
            model_name=body.model_name,
            run_name=body.run_name,
            task=body.task,
            micro_f1=body.micro_f1,
            macro_f1=body.macro_f1,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to register benchmark result: {exc}") from exc
