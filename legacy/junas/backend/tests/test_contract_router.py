from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app


class StubContractClassifier:
    def classify_contract(self, text: str, top_k_types: int = 3) -> list[dict[str, Any]]:
        return [
            {
                "segment_index": 0,
                "text": text,
                "start": 0,
                "end": len(text),
                "clause_type": "Definitions",
                "confidence": 0.95,
                "alternatives": [
                    {"type": "Applicable Laws", "confidence": 0.03},
                    {"type": "Termination", "confidence": 0.02},
                ][: max(0, top_k_types - 1)],
            }
        ]


class StubToSScanner:
    def scan_tos(self, text: str, threshold: float = 0.5) -> dict[str, Any]:
        return {
            "total_sentences": 2,
            "unfair_count": 1,
            "fair_count": 1,
            "severity_score": 0.5,
            "sentences": [
                {
                    "index": 0,
                    "text": "By using this service, you agree.",
                    "is_unfair": True,
                    "unfair_categories": [{"category": "Contract by Using", "confidence": max(threshold, 0.8)}],
                },
                {"index": 1, "text": "We provide support.", "is_unfair": False, "unfair_categories": []},
            ],
            "summary": {"Contract by Using": 1},
        }


def test_contract_classify_endpoint_returns_clauses() -> None:
    with TestClient(app) as client:
        previous_classifier = getattr(app.state, "contract_classifier", None)
        app.state.contract_classifier = StubContractClassifier()
        try:
            response = client.post(
                "/api/v1/contracts/classify",
                json={"text": "SECTION 1. DEFINITIONS. ...", "top_k_types": 3},
            )
        finally:
            app.state.contract_classifier = previous_classifier

    assert response.status_code == 200
    body = response.json()
    assert body["total_clauses"] == 1
    assert body["clause_distribution"] == {"Definitions": 1}


def test_contract_scan_tos_endpoint_returns_summary() -> None:
    with TestClient(app) as client:
        previous_scanner = getattr(app.state, "tos_scanner", None)
        app.state.tos_scanner = StubToSScanner()
        try:
            response = client.post(
                "/api/v1/contracts/scan-tos",
                json={"text": "By using this service, you agree. We provide support.", "threshold": 0.5},
            )
        finally:
            app.state.tos_scanner = previous_scanner

    assert response.status_code == 200
    body = response.json()
    assert body["unfair_count"] == 1
    assert body["summary"] == {"Contract by Using": 1}


def test_contract_classify_endpoint_returns_503_when_model_missing() -> None:
    with TestClient(app) as client:
        previous_classifier = getattr(app.state, "contract_classifier", None)
        app.state.contract_classifier = None
        try:
            response = client.post("/api/v1/contracts/classify", json={"text": "SECTION 1. ..."})
        finally:
            app.state.contract_classifier = previous_classifier

    assert response.status_code == 503
    assert response.json()["detail"] == "Contract classifier model is not loaded"


def test_contract_scan_tos_endpoint_returns_503_when_model_missing() -> None:
    with TestClient(app) as client:
        previous_scanner = getattr(app.state, "tos_scanner", None)
        app.state.tos_scanner = None
        try:
            response = client.post("/api/v1/contracts/scan-tos", json={"text": "By using this service..."})
        finally:
            app.state.tos_scanner = previous_scanner

    assert response.status_code == 503
    assert response.json()["detail"] == "ToS scanner model is not loaded"
