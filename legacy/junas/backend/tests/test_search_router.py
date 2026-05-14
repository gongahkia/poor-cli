from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.routers import search as search_router_module


class StubCaseService:
    def search_cases(
        self,
        query: str,
        top_k: int = 10,
        stages: list[str] | None = None,
        include_scores: bool = True,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "results": [
                {
                    "case_id": "1001",
                    "case_name": "测试案件",
                    "facts": "案件事实",
                    "judgment": "判决结果",
                    "charges": ["危险驾驶罪"],
                    "relevance_score": 0.9 if include_scores else None,
                    "retrieval_stage": "rerank",
                }
            ],
            "retrieval_info": {
                "stages_used": stages or ["bm25", "dense", "rerank"],
                "bm25_candidates": 100,
                "dense_candidates": 100,
                "total_time_ms": 120,
            },
        }

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        if case_id != "1001":
            return None
        return {
            "case_id": "1001",
            "case_name": "测试案件",
            "facts": "案件事实",
            "judgment": "判决结果",
            "full_text": "全文",
            "charges": ["危险驾驶罪"],
        }

    def list_charges(self) -> list[str]:
        return ["危险驾驶罪", "盗窃罪"]

    def get_metrics(self) -> dict[str, Any]:
        return {"published": {"BM25": {"NDCG@10": 0.731}}}


def test_search_cases_endpoint_returns_ranked_results() -> None:
    with TestClient(app) as client:
        previous = getattr(app.state, "case_retrieval_service", None)
        app.state.case_retrieval_service = StubCaseService()
        try:
            response = client.post(
                "/api/v1/search/cases",
                json={
                    "query": "醉驾案件",
                    "top_k": 5,
                    "stages": ["bm25", "dense", "rerank"],
                    "include_scores": True,
                },
            )
        finally:
            app.state.case_retrieval_service = previous

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "醉驾案件"
    assert body["results"][0]["case_id"] == "1001"


def test_get_case_details_returns_404_for_unknown_case() -> None:
    with TestClient(app) as client:
        previous = getattr(app.state, "case_retrieval_service", None)
        app.state.case_retrieval_service = StubCaseService()
        try:
            response = client.get("/api/v1/search/cases/missing")
        finally:
            app.state.case_retrieval_service = previous

    assert response.status_code == 404
    assert response.json()["detail"] == "Case not found"


def test_list_charges_and_metrics_endpoints() -> None:
    with TestClient(app) as client:
        previous = getattr(app.state, "case_retrieval_service", None)
        app.state.case_retrieval_service = StubCaseService()
        try:
            charges_response = client.get("/api/v1/search/charges")
            metrics_response = client.get("/api/v1/search/metrics")
        finally:
            app.state.case_retrieval_service = previous

    assert charges_response.status_code == 200
    assert charges_response.json()["charges"] == ["危险驾驶罪", "盗窃罪"]
    assert metrics_response.status_code == 200
    assert "published" in metrics_response.json()


def test_search_cases_returns_503_when_service_unavailable(monkeypatch: Any) -> None:
    def _return_none(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(search_router_module, "create_case_retrieval_service", _return_none)
    with TestClient(app) as client:
        previous = getattr(app.state, "case_retrieval_service", None)
        app.state.case_retrieval_service = None
        try:
            response = client.post("/api/v1/search/cases", json={"query": "测试"})
        finally:
            app.state.case_retrieval_service = previous

    assert response.status_code == 503
    assert response.json()["detail"] == "Case retrieval service is unavailable"
