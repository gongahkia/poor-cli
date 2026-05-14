from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.routers import rome_statute as rome_router_module


class StubRomeStatuteService:
    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        del top_k
        return [
            {
                "article_number": "6",
                "article_title": "Genocide",
                "part_number": "2",
                "part_title": "Jurisdiction, Admissibility and Applicable Law",
                "text_snippet": "For the purpose of this Statute, \"genocide\" means...",
                "score": 3.0 if "genocide" in query.lower() else 1.0,
            }
        ]

    def get_article(self, article_number: str) -> dict[str, str] | None:
        if article_number != "6":
            return None
        return {
            "article_number": "6",
            "article_title": "Genocide",
            "text": "For the purpose of this Statute, genocide means...",
            "part_number": "2",
            "part_title": "Jurisdiction, Admissibility and Applicable Law",
        }

    def list_parts(self) -> list[dict[str, Any]]:
        return [
            {
                "part_number": "1",
                "part_title": "Establishment of the Court",
                "article_count": 4,
            },
            {
                "part_number": "2",
                "part_title": "Jurisdiction, Admissibility and Applicable Law",
                "article_count": 18,
            },
        ]

    def get_part(self, part_number: str) -> dict[str, Any] | None:
        if part_number != "2":
            return None
        return {
            "part_number": "2",
            "part_title": "Jurisdiction, Admissibility and Applicable Law",
            "articles": [
                {"article_number": "5", "article_title": "Crimes within the jurisdiction of the Court"},
                {"article_number": "6", "article_title": "Genocide"},
            ],
        }


def test_rome_statute_search_endpoint_returns_results() -> None:
    app.dependency_overrides[rome_router_module.get_rome_statute_service] = lambda: StubRomeStatuteService()
    with TestClient(app) as client:
        try:
            response = client.get("/api/v1/rome-statute/search", params={"q": "genocide"})
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["article_number"] == "6"


def test_rome_statute_parts_endpoint_returns_parts() -> None:
    app.dependency_overrides[rome_router_module.get_rome_statute_service] = lambda: StubRomeStatuteService()
    with TestClient(app) as client:
        try:
            response = client.get("/api/v1/rome-statute/parts")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["parts"]) == 2


def test_rome_statute_article_and_part_endpoints_handle_not_found() -> None:
    app.dependency_overrides[rome_router_module.get_rome_statute_service] = lambda: StubRomeStatuteService()
    with TestClient(app) as client:
        try:
            ok_article = client.get("/api/v1/rome-statute/article/6")
            missing_article = client.get("/api/v1/rome-statute/article/999")
            ok_part = client.get("/api/v1/rome-statute/part/2")
            missing_part = client.get("/api/v1/rome-statute/part/99")
        finally:
            app.dependency_overrides.clear()

    assert ok_article.status_code == 200
    assert missing_article.status_code == 404
    assert ok_part.status_code == 200
    assert missing_part.status_code == 404
