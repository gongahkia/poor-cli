"""Tests for documents router."""
from fastapi.testclient import TestClient
from api.main import create_app
import io

app = create_app()
client = TestClient(app)

def test_parse_no_file():
    resp = client.post("/api/v1/documents/parse")
    assert resp.status_code == 422  # missing file

def test_parse_unsupported():
    resp = client.post("/api/v1/documents/parse", files={"file": ("test.txt", b"hello", "text/plain")})
    assert resp.status_code == 400
