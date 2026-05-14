"""Tests for template library router."""
import pytest
from fastapi.testclient import TestClient
from api.main import create_app

app = create_app()
client = TestClient(app)

def test_list_templates():
    resp = client.get("/api/v1/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 6

def test_get_template():
    resp = client.get("/api/v1/templates/nda-sg")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Non-Disclosure Agreement"
    assert len(data["variables"]) > 0

def test_get_template_not_found():
    resp = client.get("/api/v1/templates/nonexistent")
    assert resp.status_code == 404

def test_render_template():
    resp = client.post("/api/v1/templates/nda-sg/render", json={
        "values": {"discloser": "Acme Pte Ltd", "recipient": "Beta Corp", "purpose": "testing", "duration": "3", "date": "2026-01-01"}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "Acme Pte Ltd" in data["rendered"]
    assert "Beta Corp" in data["rendered"]
