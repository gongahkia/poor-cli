from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

import haus.chat_server as chat_server
import haus.mcp_server as mcp_server


@pytest.fixture()
def chat_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(mcp_server, "LAYOUT_PATH", tmp_path / "mcp-layout.json")
    app = chat_server.create_app(str(Path.cwd()))
    with TestClient(app) as client:
        yield client


def test_chat_routes_provider_and_default_model(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        captured["api_key"] = api_key
        captured["model"] = model
        captured["messages"] = messages
        return "ok", messages + [{"role": "assistant", "content": [{"type": "text", "text": "ok"}]}]

    monkeypatch.setitem(chat_server._CHAT_FNS, "openai", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "hello", "provider": "openai", "api_key": "test-key"},
    )
    assert res.status_code == 200
    body = res.json()

    assert body["response"] == "ok"
    assert body["provider"] == "openai"
    assert body["model"] == chat_server._DEFAULT_MODELS["openai"]
    assert captured["api_key"] == "test-key"
    assert captured["model"] == chat_server._DEFAULT_MODELS["openai"]


def test_chat_routes_provider_with_model_override(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        captured["model"] = model
        return "ok", messages

    monkeypatch.setitem(chat_server._CHAT_FNS, "openai", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={
            "message": "hello",
            "provider": "openai",
            "model": "gpt-test-model",
            "api_key": "test-key",
        },
    )
    assert res.status_code == 200
    assert res.json()["model"] == "gpt-test-model"
    assert captured["model"] == "gpt-test-model"


def test_chat_rejects_invalid_json_body(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/chat",
        content="{this-is-not-json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 400
    assert "Invalid JSON body" in res.json()["error"]


def test_chat_rejects_empty_message(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/chat",
        json={"message": "   ", "provider": "openai", "api_key": "test-key"},
    )
    assert res.status_code == 400
    assert "must not be empty" in res.json()["error"]


def test_chat_rejects_unsupported_provider(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/chat",
        json={"message": "hello", "provider": "unknown-provider", "api_key": "test-key"},
    )
    assert res.status_code == 400
    body = res.json()
    assert "not supported" in body["error"]
    assert "supported" in body


def test_chat_requires_api_key_for_provider(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = chat_client.post(
        "/api/chat",
        json={"message": "hello", "provider": "openai"},
    )
    assert res.status_code == 400
    assert "No API key" in res.json()["error"]


def test_chat_returns_action_log_payload_shape(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        dispatch("list_objects", {})
        return "done", messages + [{"role": "assistant", "content": [{"type": "text", "text": "done"}]}]

    monkeypatch.setitem(chat_server._CHAT_FNS, "openai", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "summarize", "provider": "openai", "api_key": "test-key"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["response"] == "done"
    assert isinstance(body["actions"], list)
    assert len(body["actions"]) == 1

    action = body["actions"][0]
    assert set(action.keys()) == {"tool", "args", "result", "elapsed_ms"}
    assert action["tool"] == "list_objects"
    assert action["args"] == {}
    assert isinstance(action["result"], str)
    assert isinstance(action["elapsed_ms"], int)
