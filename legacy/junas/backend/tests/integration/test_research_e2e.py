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
        del top_k
        return {
            "answer": f"Answer for: {question}",
            "sources": [
                {
                    "source_id": "Rome Statute Art. 6",
                    "source_type": "treaty",
                    "text_snippet": "For the purpose of this Statute, genocide means...",
                    "metadata": {"article_number": "6"},
                    "relevance_score": 0.88,
                }
            ],
            "citations": {
                "citations": [
                    {
                        "citation": "Rome Statute Art. 6",
                        "type": "generic",
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
            "conversation_id": conversation_id or "conv-treaty",
            "echo_sources": sources,
        }

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        if conversation_id != "conv-treaty":
            return None
        return {
            "conversation_id": conversation_id,
            "turns": [
                {"role": "user", "content": "What is genocide?"},
                {"role": "assistant", "content": "See Rome Statute Art. 6."},
            ],
        }

    async def delete_conversation(self, conversation_id: str) -> bool:
        return conversation_id == "conv-treaty"


def test_research_ask_flow_accepts_treaty_source() -> None:
    app.dependency_overrides[research_router_module.get_legal_qa_service] = lambda: StubLegalQAService()
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/research/ask",
                json={
                    "question": "What is genocide under the Rome Statute?",
                    "sources": ["treaty", "statute"],
                    "top_k": 8,
                },
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conv-treaty"
    assert body["sources"][0]["source_type"] == "treaty"
    assert body["citations"]["total_citations"] == 1
