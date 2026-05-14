from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.routers import ner as ner_router_module


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
        del text, granularity, use_gazetteer
        return [
            {
                "text": "BGH" if language == "de" else "Supreme Court",
                "type": "ORG",
                "type_label": "Organization",
                "start": 0,
                "end": 3,
                "confidence": 0.95,
                "language": language,
            }
        ]


def test_ner_extract_flow_supports_german_and_english() -> None:
    app.dependency_overrides[ner_router_module.get_entity_extractor] = lambda: StubExtractor()
    with TestClient(app) as client:
        try:
            de_response = client.post(
                "/api/v1/ner/extract",
                json={"text": "Der BGH entschied.", "language": "de", "granularity": "fine"},
            )
            en_response = client.post(
                "/api/v1/ner/extract",
                json={"text": "The Supreme Court ruled.", "language": "en", "granularity": "fine"},
            )
        finally:
            app.dependency_overrides.clear()

    assert de_response.status_code == 200
    assert en_response.status_code == 200

    de_body = de_response.json()
    en_body = en_response.json()
    assert de_body["model_info"]["language"] == "de"
    assert en_body["model_info"]["language"] == "en"
    assert de_body["entity_counts"] == {"ORG": 1}
    assert en_body["entity_counts"] == {"ORG": 1}
