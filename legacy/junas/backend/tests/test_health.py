from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint_returns_service_map() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"services"}
    assert set(body["services"].keys()) == {"postgres", "elasticsearch", "qdrant", "redis"}
    assert all(isinstance(value, bool) for value in body["services"].values())


def test_metrics_endpoint_returns_platform_stats_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    body = response.json()

    assert isinstance(body.get("uptime_seconds"), int)
    assert isinstance(body.get("models_loaded"), list)
    assert isinstance(body.get("indices"), dict)
    assert isinstance(body.get("qdrant_collections"), dict)
    assert isinstance(body.get("benchmark_runs"), int)
    assert isinstance(body.get("conversations"), int)
