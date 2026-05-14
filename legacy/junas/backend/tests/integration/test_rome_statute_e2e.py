from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.routers import rome_statute as rome_router_module


class StubRomeService:
    def list_parts(self) -> list[dict[str, Any]]:
        return [
            {
                "part_number": "2",
                "part_title": "Jurisdiction, Admissibility and Applicable Law",
                "article_count": 18,
            }
        ]

    def get_part(self, number: str) -> dict[str, Any] | None:
        if number != "2":
            return None
        return {
            "part_number": "2",
            "part_title": "Jurisdiction, Admissibility and Applicable Law",
            "articles": [
                {"article_number": "6", "article_title": "Genocide"},
                {"article_number": "7", "article_title": "Crimes against humanity"},
            ],
        }

    def get_article(self, number: str) -> dict[str, Any] | None:
        if number != "6":
            return None
        return {
            "article_number": "6",
            "article_title": "Genocide",
            "text": "For the purpose of this Statute, genocide means...",
            "part_number": "2",
            "part_title": "Jurisdiction, Admissibility and Applicable Law",
        }

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        del top_k
        if "genocide" not in query.lower():
            return []
        return [
            {
                "article_number": "6",
                "article_title": "Genocide",
                "part_number": "2",
                "part_title": "Jurisdiction, Admissibility and Applicable Law",
                "text_snippet": "For the purpose of this Statute, genocide means...",
                "score": 3.0,
            }
        ]


def test_rome_statute_full_browse_and_search_flow() -> None:
    app.dependency_overrides[rome_router_module.get_rome_statute_service] = lambda: StubRomeService()
    with TestClient(app) as client:
        try:
            parts_response = client.get("/api/v1/rome-statute/parts")
            part_response = client.get("/api/v1/rome-statute/part/2")
            article_response = client.get("/api/v1/rome-statute/article/6")
            search_response = client.get("/api/v1/rome-statute/search", params={"q": "genocide"})
        finally:
            app.dependency_overrides.clear()

    assert parts_response.status_code == 200
    assert part_response.status_code == 200
    assert article_response.status_code == 200
    assert search_response.status_code == 200

    assert parts_response.json()["parts"][0]["part_number"] == "2"
    assert part_response.json()["articles"][0]["article_number"] == "6"
    assert article_response.json()["article_title"] == "Genocide"
    assert search_response.json()["results"][0]["article_number"] == "6"
