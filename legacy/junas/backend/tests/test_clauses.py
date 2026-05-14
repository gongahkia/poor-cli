"""Tests for clause library router."""
import pytest
from fastapi.testclient import TestClient
from api.main import create_app

app = create_app()
client = TestClient(app)

def test_list_clauses():
    resp = client.get("/api/v1/clauses")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 6
    assert data[0]["id"] == "force-majeure-sg"

def test_list_clauses_search():
    resp = client.get("/api/v1/clauses?query=liability")
    assert resp.status_code == 200
    data = resp.json()
    assert any("Liability" in c["name"] for c in data)

def test_get_clause_by_id():
    resp = client.get("/api/v1/clauses/confidentiality-sg")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Confidentiality"
    assert "standard" in data
    assert "aggressive" in data

def test_get_clause_not_found():
    resp = client.get("/api/v1/clauses/nonexistent")
    assert resp.status_code == 404

def test_get_clause_tone():
    resp = client.get("/api/v1/clauses/force-majeure-sg/tone/aggressive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tone"] == "aggressive"
    assert "wording" in data

def test_get_clause_invalid_tone():
    resp = client.get("/api/v1/clauses/force-majeure-sg/tone/invalid")
    assert resp.status_code == 400
