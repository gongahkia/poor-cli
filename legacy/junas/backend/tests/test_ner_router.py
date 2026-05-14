from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app


class StubExtractor:
    model_name = "ner-german-legal"
    multilingual_model_name = "ner-multilingual-legal"

    def model_name_for_language(self, language: str) -> str:
        return self.multilingual_model_name if language == "en" else self.model_name

    def extract(
        self,
        text: str,
        granularity: str = "fine",
        use_gazetteer: bool = True,
        language: str = "de",
    ) -> list[dict[str, Any]]:
        del text
        entity_type = "ORG" if granularity == "fine" else "ORG"
        payload: dict[str, Any] = {
            "text": "BGH" if language == "de" else "Supreme Court",
            "type": entity_type,
            "type_label": "Organization",
            "start": 4,
            "end": 7,
            "confidence": 0.97,
            "language": language,
        }
        if use_gazetteer:
            payload["gazetteer_match"] = True
        return [payload]


def test_entity_types_endpoint_returns_fine_and_coarse_mappings() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/ner/entity-types")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"fine_grained", "coarse_grained"}
    assert any(item["tag"] == "PER" for item in body["fine_grained"])
    assert any(item["tag"] == "REG" for item in body["coarse_grained"])


def test_extract_endpoint_returns_503_when_model_not_loaded() -> None:
    with TestClient(app) as client:
        previous = getattr(app.state, "entity_extractor", None)
        app.state.entity_extractor = None
        try:
            response = client.post(
                "/api/v1/ner/extract",
                json={"text": "Der BGH entschied.", "granularity": "fine"},
            )
        finally:
            app.state.entity_extractor = previous

    assert response.status_code == 503
    assert response.json()["detail"] == "NER model is not loaded"


def test_extract_endpoint_uses_language_specific_model_name() -> None:
    with TestClient(app) as client:
        previous = getattr(app.state, "entity_extractor", None)
        app.state.entity_extractor = StubExtractor()
        try:
            response = client.post(
                "/api/v1/ner/extract",
                json={
                    "text": "The Supreme Court considered the appeal.",
                    "language": "en",
                    "granularity": "fine",
                    "use_gazetteer": False,
                },
            )
        finally:
            app.state.entity_extractor = previous

    assert response.status_code == 200
    body = response.json()
    assert body["model_info"]["model"] == "ner-multilingual-legal"
    assert body["model_info"]["language"] == "en"
    assert body["entity_counts"] == {"ORG": 1}
    assert body["entities"][0]["language"] == "en"


def test_batch_endpoint_returns_results_for_each_text() -> None:
    with TestClient(app) as client:
        previous = getattr(app.state, "entity_extractor", None)
        app.state.entity_extractor = StubExtractor()
        try:
            response = client.post(
                "/api/v1/ner/batch",
                json={
                    "texts": ["Der BGH entschied.", "Das BAG urteilte."],
                    "language": "de",
                    "granularity": "fine",
                    "use_gazetteer": False,
                },
            )
        finally:
            app.state.entity_extractor = previous

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert all(item["model_info"]["language"] == "de" for item in body)


def test_extract_endpoint_rejects_unknown_language() -> None:
    with TestClient(app) as client:
        previous = getattr(app.state, "entity_extractor", None)
        app.state.entity_extractor = StubExtractor()
        try:
            response = client.post(
                "/api/v1/ner/extract",
                json={
                    "text": "Der BGH entschied.",
                    "language": "fr",
                    "granularity": "fine",
                },
            )
        finally:
            app.state.entity_extractor = previous

    assert response.status_code == 422
