from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.routers import research as research_router_module


class StubLegalQAService:
    async def answer(
        self,
        question: str,
        sources: list[Any] | None = None,
        conversation_id: str | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        del sources, top_k
        return {
            "answer": f"Answer for: {question}",
            "sources": [
                {
                    "source_id": "ORS 685.010",
                    "source_type": "statute",
                    "text_snippet": "As used in this chapter...",
                    "metadata": {"name": "Definitions", "chapter": "685"},
                    "relevance_score": 0.91,
                }
            ],
            "citations": {
                "citations": [
                    {
                        "citation": "ORS 685.010",
                        "type": "statute",
                        "in_context": True,
                        "exists_in_index": True,
                        "position": [0, 10],
                    }
                ],
                "total_citations": 1,
                "verified_citations": 1,
                "hallucinated_citations": [],
                "citation_rate": 0.5,
            },
            "conversation_id": conversation_id or "conv-123",
        }

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        if conversation_id != "conv-123":
            return None
        return {
            "conversation_id": conversation_id,
            "turns": [
                {"role": "user", "content": "What is a naturopathic physician?"},
                {"role": "assistant", "content": "See ORS 685.010."},
            ],
        }

    async def delete_conversation(self, conversation_id: str) -> bool:
        return conversation_id == "conv-123"


def test_research_ask_endpoint_returns_answer_payload() -> None:
    app.dependency_overrides[research_router_module.get_legal_qa_service] = lambda: StubLegalQAService()
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/research/ask",
                json={
                    "question": "What is a naturopathic physician in Oregon?",
                    "sources": ["statute", "glossary", "treaty"],
                    "top_k": 6,
                },
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conv-123"
    assert body["sources"][0]["source_id"] == "ORS 685.010"


def test_research_conversation_get_and_delete() -> None:
    app.dependency_overrides[research_router_module.get_legal_qa_service] = lambda: StubLegalQAService()
    with TestClient(app) as client:
        try:
            get_response = client.get("/api/v1/research/conversations/conv-123")
            delete_response = client.delete("/api/v1/research/conversations/conv-123")
            missing_response = client.get("/api/v1/research/conversations/missing")
        finally:
            app.dependency_overrides.clear()

    assert get_response.status_code == 200
    assert len(get_response.json()["turns"]) == 2

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    assert missing_response.status_code == 404


def test_research_config_endpoint_returns_provider_info() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/research/config")

    assert response.status_code == 200
    body = response.json()
    assert "provider" in body
    assert "model" in body
    assert "available_sources" in body


def test_research_config_includes_treaty_when_service_loaded() -> None:
    previous = getattr(app.state, "rome_statute_service", None)
    app.state.rome_statute_service = object()
    with TestClient(app) as client:
        try:
            response = client.get("/api/v1/research/config")
        finally:
            app.state.rome_statute_service = previous

    assert response.status_code == 200
    assert "treaty" in response.json().get("available_sources", [])
