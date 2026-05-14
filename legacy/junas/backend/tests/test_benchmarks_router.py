from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.routers import benchmarks as benchmarks_router_module


class StubBenchmarkService:
    async def create_run(
        self,
        model_name: str,
        run_name: str,
        tasks: list[str] | None = None,
        model_path: str | None = None,
    ) -> dict[str, Any]:
        return {
            "run_id": "11111111-1111-1111-1111-111111111111",
            "status": "pending",
            "message": "Benchmark run queued",
            "model_name": model_name,
            "run_name": run_name,
            "tasks": tasks or [],
            "model_path": model_path,
        }

    async def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "run_id": "11111111-1111-1111-1111-111111111111",
                "run_name": "legal-bert-baseline",
                "model_name": "nlpaueb/legal-bert-base-uncased",
                "status": "completed",
                "tasks_completed": 7,
                "tasks_total": 7,
                "avg_micro_f1": 0.823,
                "avg_macro_f1": 0.731,
                "completed_at": "2026-04-01T15:30:00+00:00",
                "is_published_baseline": False,
                "created_at": "2026-04-01T14:00:00+00:00",
            }
        ][:limit]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        if run_id != "11111111-1111-1111-1111-111111111111":
            return None
        return {
            "run_id": run_id,
            "run_name": "legal-bert-baseline",
            "model_name": "nlpaueb/legal-bert-base-uncased",
            "status": "completed",
            "requested_tasks": ["ledgar", "unfair_tos"],
            "results": {
                "tasks": {
                    "ledgar": {"task_name": "LEDGAR", "micro_f1": 0.882, "macro_f1": 0.830},
                    "unfair_tos": {"task_name": "UNFAIR-ToS", "micro_f1": 0.960, "macro_f1": 0.830},
                },
                "aggregate": {"avg_micro_f1": 0.921, "avg_macro_f1": 0.830, "tasks_completed": 2, "tasks_total": 2},
            },
            "scores": [],
            "error": None,
            "tasks_completed": 2,
            "tasks_total": 2,
            "avg_micro_f1": 0.921,
            "avg_macro_f1": 0.830,
            "is_published_baseline": False,
            "started_at": "2026-04-01T15:00:00+00:00",
            "completed_at": "2026-04-01T15:10:00+00:00",
            "created_at": "2026-04-01T14:00:00+00:00",
            "updated_at": "2026-04-01T15:10:00+00:00",
        }

    async def leaderboard(self, task: str | None = None, sort_by: str = "avg_micro_f1") -> dict[str, Any]:
        del task, sort_by
        return {
            "leaderboard": [
                {
                    "rank": 1,
                    "run_name": "legal-bert-baseline",
                    "model_name": "nlpaueb/legal-bert-base-uncased",
                    "avg_micro_f1": 0.823,
                    "task_scores": {"ledgar": 0.882, "unfair_tos": 0.960},
                }
            ],
            "baselines": [
                {
                    "name": "Legal-BERT (published)",
                    "source": "Chalkidis et al., ACL 2022",
                    "task_scores": {"ledgar": 0.882, "unfair_tos": 0.960},
                }
            ],
            "task_labels": {"ledgar": "LEDGAR", "unfair_tos": "UNFAIR-ToS"},
        }

    async def list_tasks(self) -> list[dict[str, Any]]:
        return [
            {"name": "LEDGAR", "task": "ledgar", "task_type": "multi_class", "num_labels": 100},
            {"name": "UNFAIR-ToS", "task": "unfair_tos", "task_type": "multi_label", "num_labels": 8},
        ]

    async def register_run_result(
        self,
        model_name: str,
        run_name: str,
        task: str,
        micro_f1: float,
        macro_f1: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "run_id": "11111111-1111-1111-1111-111111111111",
            "run_name": run_name,
            "model_name": model_name,
            "task": task,
            "status": "completed",
            "aggregate": {
                "avg_micro_f1": micro_f1,
                "avg_macro_f1": macro_f1 or 0.0,
                "tasks_completed": 1,
                "tasks_total": 1,
            },
            "metadata": metadata or {},
        }


def test_queue_benchmark_run_endpoint() -> None:
    stub = StubBenchmarkService()
    app.dependency_overrides[benchmarks_router_module.get_benchmark_service] = lambda: stub
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/benchmarks/run",
                json={
                    "model_name": "nlpaueb/legal-bert-base-uncased",
                    "run_name": "legal-bert-baseline",
                    "tasks": ["ledgar", "unfair_tos"],
                },
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["run_id"] == "11111111-1111-1111-1111-111111111111"


def test_list_runs_and_tasks_endpoints() -> None:
    stub = StubBenchmarkService()
    app.dependency_overrides[benchmarks_router_module.get_benchmark_service] = lambda: stub
    with TestClient(app) as client:
        try:
            runs_response = client.get("/api/v1/benchmarks/runs")
            tasks_response = client.get("/api/v1/benchmarks/tasks")
        finally:
            app.dependency_overrides.clear()

    assert runs_response.status_code == 200
    assert runs_response.json()["runs"][0]["run_name"] == "legal-bert-baseline"

    assert tasks_response.status_code == 200
    assert tasks_response.json()["tasks"][0]["task"] == "ledgar"


def test_run_detail_returns_not_found_for_unknown_run() -> None:
    stub = StubBenchmarkService()
    app.dependency_overrides[benchmarks_router_module.get_benchmark_service] = lambda: stub
    with TestClient(app) as client:
        try:
            response = client.get("/api/v1/benchmarks/runs/missing")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Benchmark run not found"


def test_leaderboard_endpoint_returns_payload() -> None:
    stub = StubBenchmarkService()
    app.dependency_overrides[benchmarks_router_module.get_benchmark_service] = lambda: stub
    with TestClient(app) as client:
        try:
            response = client.get("/api/v1/benchmarks/leaderboard")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["leaderboard"][0]["run_name"] == "legal-bert-baseline"
    assert body["baselines"][0]["name"] == "Legal-BERT (published)"


def test_register_benchmark_result_endpoint_returns_payload() -> None:
    stub = StubBenchmarkService()
    app.dependency_overrides[benchmarks_router_module.get_benchmark_service] = lambda: stub
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/benchmarks/register",
                json={
                    "model_name": "nlpaueb/legal-bert-base-uncased",
                    "run_name": "scotus-phase9",
                    "task": "scotus",
                    "micro_f1": 0.761,
                    "macro_f1": 0.665,
                    "metadata": {"model_path": "models/scotus-classifier/best"},
                },
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["task"] == "scotus"
