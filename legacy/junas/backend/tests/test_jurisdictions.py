"""Tests for jurisdiction router."""
from fastapi.testclient import TestClient
from api.main import create_app

app = create_app()
client = TestClient(app)

def test_list_jurisdictions():
    resp = client.get("/api/v1/jurisdictions")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [j["id"] for j in data]
    assert "sg" in ids
    assert "my" in ids
    assert "us" in ids
    assert "eu" in ids
    assert "intl" in ids

def test_get_singapore():
    resp = client.get("/api/v1/jurisdictions/sg")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Singapore"
    assert len(data["citation_patterns"]) >= 5

def test_get_nonexistent():
    resp = client.get("/api/v1/jurisdictions/xx")
    assert resp.status_code == 404
