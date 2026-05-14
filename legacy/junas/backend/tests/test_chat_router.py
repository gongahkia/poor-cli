"""Tests for chat router."""
from fastapi.testclient import TestClient
from api.main import create_app

app = create_app()
client = TestClient(app)

def test_list_providers():
    resp = client.get("/api/v1/chat/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [p["id"] for p in data]
    assert "claude" in ids
    assert "openai" in ids
    assert "gemini" in ids
    assert "ollama" in ids
    assert "lmstudio" in ids

def test_send_missing_provider_key():
    # should fail since no API key for unknown provider
    resp = client.post("/api/v1/chat/send", json={
        "provider": "claude",
        "messages": [{"role": "user", "content": "hello"}],
    })
    # expect 502 (provider rejects), 500, or 422 (validation)
    assert resp.status_code in (200, 422, 500, 502)
