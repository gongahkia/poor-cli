from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import haus.chat_server as chat_server
import haus.mcp_server as mcp_server


@pytest.fixture()
def chat_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(mcp_server, "LAYOUT_PATH", tmp_path / "mcp-layout.json")
    chat_server._DESIGN_PLAN_CACHE.clear()
    chat_server._DESIGN_PLAN_ORDER.clear()
    app = chat_server.create_app(str(Path.cwd()))
    with TestClient(app) as client:
        yield client


def _encoded_image(data: bytes = b"sample-image") -> str:
    return base64.b64encode(data).decode("ascii")


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


def test_chat_status_reports_reference_capabilities(chat_client: TestClient) -> None:
    res = chat_client.get("/api/chat/status")
    assert res.status_code == 200

    capabilities = res.json()["capabilities"]
    assert capabilities["web_search"] is True
    assert capabilities["web_fetch"] is True
    assert capabilities["image_references"] is True
    assert capabilities["design_plans"] is True
    assert capabilities["planner_requires_api_key"] is True
    assert capabilities["max_image_attachments"] == 3
    assert "image/png" in capabilities["image_mime_types"]


def test_chat_status_reports_search_provider_configuration(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("HAUS_SEARCH_PROVIDERS", "serper,exa,tinyfish,duckduckgo")
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("TINYFISH_API_KEY", "tinyfish-key")

    res = chat_client.get("/api/chat/status")
    assert res.status_code == 200
    body = res.json()

    assert body["search_providers_configured"] == ["serper", "exa", "tinyfish", "duckduckgo"]
    assert body["search_providers_available"] == ["serper", "tinyfish", "duckduckgo"]
    assert body["search_fallback_provider"] == "duckduckgo"


def test_web_search_can_be_disabled(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_ENABLE_WEB_SEARCH", "0")

    res = chat_client.get("/api/chat/status")
    assert res.status_code == 200
    body = res.json()

    assert body["capabilities"]["web_search"] is False
    assert body["search_providers_configured"] == []
    assert body["search_providers_available"] == []
    assert chat_server._web_search("hdb storage ideas") == "Web search is disabled by HAUS_ENABLE_WEB_SEARCH=0."


def test_search_references_normalizes_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("HAUS_SEARCH_PROVIDERS", "serper,exa,duckduckgo")
    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("EXA_API_KEY", "exa-key")

    def fake_serper(query: str, max_results: int) -> list[dict[str, object]]:
        return [
            {
                "title": "HDB Storage",
                "url": "https://example.com/storage?utm_source=test",
                "snippet": "Built-in storage ideas",
                "source_provider": "serper",
                "published_date": None,
                "retrieved_at": "2026-06-03T00:00:00Z",
            }
        ]

    def fake_exa(query: str, max_results: int) -> list[dict[str, object]]:
        return [
            {
                "title": "Duplicate HDB Storage",
                "url": "https://example.com/storage",
                "snippet": "Duplicate URL",
                "source_provider": "exa",
                "published_date": "2026",
                "retrieved_at": "2026-06-03T00:00:00Z",
            },
            {
                "title": "Circulation",
                "url": "https://example.com/circulation",
                "snippet": "Walkway guidance",
                "source_provider": "exa",
                "published_date": None,
                "retrieved_at": "2026-06-03T00:00:00Z",
            },
        ]

    monkeypatch.setitem(chat_server._SEARCH_FNS, "serper", fake_serper)
    monkeypatch.setitem(chat_server._SEARCH_FNS, "exa", fake_exa)
    monkeypatch.setitem(chat_server._SEARCH_FNS, "duckduckgo", lambda query, max_results: [])

    results = chat_server.search_references("hdb storage", max_results=5)

    assert [item["url"] for item in results] == [
        "https://example.com/storage?utm_source=test",
        "https://example.com/circulation",
    ]
    assert results[0]["source_provider"] == "serper"
    assert results[1]["source_provider"] == "exa"


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


def test_chat_passes_image_references_and_redacts_returned_history(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    image_data = _encoded_image(b"reference-image-bytes")

    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        captured["messages"] = messages
        return "replicated", messages + [{"role": "assistant", "content": [{"type": "text", "text": "replicated"}]}]

    monkeypatch.setitem(chat_server._CHAT_FNS, "openai", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={
            "message": "make it look like this",
            "provider": "openai",
            "api_key": "test-key",
            "attachments": [
                {
                    "name": "living-room.png",
                    "mime_type": "image/png",
                    "data_base64": image_data,
                }
            ],
        },
    )
    assert res.status_code == 200

    messages = captured["messages"]
    assert isinstance(messages, list)
    content = messages[-1]["content"]  # type: ignore[index]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "living-room.png" in content[0]["text"]
    assert content[1]["type"] == "image"
    assert content[1]["source"]["media_type"] == "image/png"
    assert content[1]["source"]["data"] == image_data

    body = res.json()
    assert body["response"] == "replicated"
    assert image_data not in json.dumps(body["history"])


def test_chat_rejects_invalid_image_reference(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/chat",
        json={
            "message": "use this",
            "provider": "openai",
            "api_key": "test-key",
            "attachments": [
                {
                    "name": "bad.txt",
                    "mime_type": "text/plain",
                    "data_base64": _encoded_image(),
                }
            ],
        },
    )
    assert res.status_code == 400
    assert "must be one of" in res.json()["error"]


def test_chat_dispatches_web_search_tool(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_search(query: str, max_results: int = 5) -> str:
        return f"Web search results for: {query}\n[1] HDB storage\nURL: https://example.com"

    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        dispatch("web_search", {"query": "current HDB storage ideas", "max_results": 1})
        return "used sources", messages

    monkeypatch.setattr(chat_server, "_web_search", fake_search)
    monkeypatch.setitem(chat_server._CHAT_FNS, "openai", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "find live storage references", "provider": "openai", "api_key": "test-key"},
    )
    assert res.status_code == 200

    action = res.json()["actions"][0]
    assert action["tool"] == "web_search"
    assert action["args"]["query"] == "current HDB storage ideas"
    assert "https://example.com" in action["result"]


def test_fetch_web_page_rejects_private_network_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAUS_ENABLE_WEB_SEARCH", "1")
    result = chat_server._fetch_web_page("http://127.0.0.1:8080/internal")
    assert "Private network URLs are not allowed" in result


def test_concept_chat_drafts_plan_without_mutating_layout(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_server,
        "search_references",
        lambda query, max_results=5: [
            {
                "title": "HDB living room guide",
                "url": "https://example.com/hdb-living",
                "snippet": "Use compact furniture and clear circulation.",
                "source_provider": "serper",
                "published_date": None,
                "retrieved_at": "2026-06-03T00:00:00Z",
            }
        ],
    )

    res = chat_client.post(
        "/api/chat",
        json={
            "message": "Design a whole 4-room HDB flat with Japandi storage",
            "provider": "openai",
            "api_key": "test-key",
        },
    )
    assert res.status_code == 200
    body = res.json()

    assert body["provider"] == "haus-planner"
    assert body["pending_plan"]["status"] == "draft"
    assert body["pending_plan"]["scope"] == "whole_flat"
    assert body["pending_plan"]["metrics"]["planned_item_count"] > 0
    assert body["references"][0]["url"] == "https://example.com/hdb-living"
    assert mcp_server._load_layout()["items"] == []


def test_concept_chat_requires_provider_key(chat_client: TestClient) -> None:
    res = chat_client.post("/api/chat", json={"message": "Design a whole 4-room HDB flat"})

    assert res.status_code == 400
    assert "API key" in res.json()["error"]


def test_apply_design_plan_mutates_layout_and_tags_rooms(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_server, "search_references", lambda query, max_results=5: [])

    draft = chat_client.post(
        "/api/chat",
        json={
            "message": "Design a living room layout with clear TV sightline",
            "provider": "openai",
            "api_key": "test-key",
        },
    )
    assert draft.status_code == 200
    plan_id = draft.json()["pending_plan"]["id"]

    res = chat_client.post(f"/api/design-plans/{plan_id}/apply")
    assert res.status_code == 200
    body = res.json()

    assert body["ok"] is True
    assert body["plan"]["status"] == "applied"
    assert body["applied_by_room"]["Living"]
    assert "layout_summary" in body["validation"]

    layout = mcp_server._load_layout()
    assert len(layout["items"]) > 0
    assert {item.get("room") for item in layout["items"]} == {"Living"}


def test_revise_design_plan_preserves_id_and_updates_report(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_server,
        "search_references",
        lambda query, max_results=5: [
            {
                "title": "Compact study reference",
                "url": "https://example.com/study",
                "snippet": "Reference",
                "source_provider": "exa",
                "published_date": "2026",
                "retrieved_at": "2026-06-03T00:00:00Z",
            }
        ],
    )

    draft = chat_client.post(
        "/api/chat",
        json={"message": "Design a study room layout", "provider": "openai", "api_key": "test-key"},
    )
    assert draft.status_code == 200
    plan_id = draft.json()["pending_plan"]["id"]

    revised = chat_client.post(
        f"/api/design-plans/{plan_id}/revise",
        json={"revision": "Add more bookshelf capacity and keep the desk near daylight"},
    )
    assert revised.status_code == 200
    revised_plan = revised.json()["plan"]
    assert revised_plan["id"] == plan_id
    assert revised_plan["status"] == "revised_draft"
    assert "bookshelf capacity" in revised_plan["brief"]

    report = chat_client.get(f"/api/design-plans/{plan_id}/report")
    assert report.status_code == 200
    assert "## Metrics" in report.text
    assert "https://example.com/study" in report.text
