from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.routers import predictions as predictions_router_module


class StubCourtPredictor:
    def predict_scotus(self, text: str, top_k: int = 3) -> dict[str, Any]:
        del text, top_k
        return {
            "prediction": {
                "issue_area": "Criminal Procedure",
                "issue_area_id": 0,
                "confidence": 0.87,
            },
            "alternatives": [
                {"issue_area": "Due Process", "issue_area_id": 3, "confidence": 0.08},
                {"issue_area": "Civil Rights", "issue_area_id": 1, "confidence": 0.03},
            ],
            "model_info": {"model": "scotus-classifier", "input_length": 5123},
        }

    def predict_ecthr(self, text: str, task: str = "violation", threshold: float = 0.5) -> dict[str, Any]:
        del text, threshold
        return {
            "predictions": [
                {
                    "article": "Article 3",
                    "article_id": 1,
                    "right": "Prohibition of torture",
                    "confidence": 0.91,
                }
            ],
            "no_violation_probability": 0.05,
            "task": task,
        }

    def predict_casehold(self, context: str, options: list[str]) -> dict[str, Any]:
        del context
        return {
            "selected_option": 2,
            "selected_text": options[2],
            "confidence": 0.78,
            "option_scores": [0.05, 0.08, 0.78, 0.06, 0.03],
        }

    def predict_eurlex(self, text: str, threshold: float = 0.3, max_labels: int = 10) -> dict[str, Any]:
        del text, threshold, max_labels
        return {
            "labels": [
                {"eurovoc_id": 42, "concept": "consumer protection", "confidence": 0.89},
                {"eurovoc_id": 17, "concept": "internal market", "confidence": 0.72},
            ],
            "total_labels": 2,
        }


class UnavailablePredictor:
    def predict_scotus(self, text: str, top_k: int = 3) -> dict[str, Any]:
        del text, top_k
        raise RuntimeError("SCOTUS model not loaded")


def test_predict_scotus_endpoint_returns_prediction() -> None:
    app.dependency_overrides[predictions_router_module.get_court_predictor] = lambda: StubCourtPredictor()
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/predict/scotus",
                json={"text": "Full opinion text", "top_k": 3},
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["prediction"]["issue_area"] == "Criminal Procedure"
    assert len(body["alternatives"]) == 2


def test_predict_ecthr_endpoint_returns_predictions() -> None:
    app.dependency_overrides[predictions_router_module.get_court_predictor] = lambda: StubCourtPredictor()
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/predict/ecthr",
                json={"text": "Case facts", "task": "violation", "threshold": 0.5},
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["task"] == "violation"
    assert body["predictions"][0]["article"] == "Article 3"


def test_predict_casehold_endpoint_returns_selected_option() -> None:
    app.dependency_overrides[predictions_router_module.get_court_predictor] = lambda: StubCourtPredictor()
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/predict/casehold",
                json={
                    "context": "The court held that <HOLDING>",
                    "options": [
                        "option 0",
                        "option 1",
                        "option 2",
                        "option 3",
                        "option 4",
                    ],
                },
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["selected_option"] == 2
    assert body["selected_text"] == "option 2"


def test_predict_eurlex_endpoint_returns_labels() -> None:
    app.dependency_overrides[predictions_router_module.get_court_predictor] = lambda: StubCourtPredictor()
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/predict/eurlex",
                json={"text": "EU regulation text", "threshold": 0.3, "max_labels": 10},
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total_labels"] == 2
    assert body["labels"][0]["eurovoc_id"] == 42


def test_predict_scotus_returns_503_when_model_missing() -> None:
    app.dependency_overrides[predictions_router_module.get_court_predictor] = lambda: UnavailablePredictor()
    with TestClient(app) as client:
        try:
            response = client.post(
                "/api/v1/predict/scotus",
                json={"text": "Opinion text"},
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "SCOTUS model not loaded"
