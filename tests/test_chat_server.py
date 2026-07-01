from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import haus.chat_server as chat_server
import haus.mcp_server as mcp_server
from haus.llm.providers import local_cli
from haus.llm.providers import openai_compatible


@pytest.fixture()
def chat_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(mcp_server, "LAYOUT_PATH", tmp_path / "mcp-layout.json")
    chat_server._DESIGN_PLAN_CACHE.clear()
    chat_server._DESIGN_PLAN_ORDER.clear()
    chat_server._TOOL_CONFIRMATION_CACHE.clear()
    chat_server._TOOL_CONFIRMATION_ORDER.clear()
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

    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "hello", "provider": "ollama"},
    )
    assert res.status_code == 200
    body = res.json()

    assert body["response"] == "ok"
    assert body["provider"] == "ollama"
    assert body["model"] == chat_server._DEFAULT_MODELS["ollama"]
    assert captured["api_key"] == "local"
    assert captured["model"] == chat_server._DEFAULT_MODELS["ollama"]


def test_chat_status_reports_reference_capabilities(chat_client: TestClient) -> None:
    res = chat_client.get("/api/chat/status")
    assert res.status_code == 200

    capabilities = res.json()["capabilities"]
    assert capabilities["web_search"] is True
    assert capabilities["web_fetch"] is True
    assert capabilities["image_references"] is True
    assert capabilities["room_capture"] is True
    assert capabilities["ikea_catalog"] is True
    assert capabilities["design_plans"] is True
    assert capabilities["planner_requires_api_key"] is False
    assert capabilities["destructive_confirmation"] is True
    assert capabilities["strict_tool_validation"] is True
    assert "llm_reviewed" in capabilities["planner_modes"]
    assert "apartment_compact" in capabilities["standards_profiles"]
    assert "accessible" in capabilities["standards_profiles"]
    assert capabilities["max_image_attachments"] == 3
    assert "image/png" in capabilities["image_mime_types"]


def test_health_route_reports_web_deploy_contract(chat_client: TestClient) -> None:
    res = chat_client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["service"] == "haus-api"
    assert body["persistence"] == "browser-indexeddb"
    assert body["features"]["mcp_scratch_layout"] is True


def test_cors_allows_vite_dev_origin(chat_client: TestClient) -> None:
    res = chat_client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_chat_models_reports_provider_metadata(chat_client: TestClient) -> None:
    res = chat_client.get("/api/chat/models")
    assert res.status_code == 200
    body = res.json()

    assert "ollama" in body["supported_providers"]
    assert "openai-compatible-local" in body["supported_providers"]
    assert "webllm" in body["supported_providers"]
    providers = {item["id"]: item for item in body["providers"]}
    assert "openai" not in providers
    assert "anthropic" not in providers
    assert "gemini" not in providers
    assert "codex" not in providers
    assert "gemini-cli" not in providers
    assert "claude-code" not in providers
    assert "opencode" not in providers
    assert "aider" not in providers
    assert providers["ollama"]["requires_api_key"] is False
    assert providers["openai-compatible-local"]["base_url"] == "http://localhost:1234/v1"
    assert "browser_runtime" in providers["webllm"]["capabilities"]
    assert "tools" in providers["webllm"]["capabilities"]
    assert "streaming" in providers["ollama"]["capabilities"]
    assert providers["ollama"]["models"]


def test_chat_tools_route_returns_full_tool_catalog(chat_client: TestClient) -> None:
    res = chat_client.get("/api/chat/tools")
    assert res.status_code == 200
    body = res.json()
    names = {tool["name"] for tool in body["tools"]}
    assert "list_objects" in names
    assert "add_furniture" in names
    assert "web_search" in names


def test_browser_tool_dispatch_route_calls_haus_tool(chat_client: TestClient) -> None:
    res = chat_client.post("/api/chat/tools/dispatch", json={"name": "list_objects", "arguments": {}})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["actions"][0]["tool"] == "list_objects"


def test_browser_tool_dispatch_validates_args(chat_client: TestClient) -> None:
    res = chat_client.post("/api/chat/tools/dispatch", json={"name": "move_object", "arguments": {"index": 0}})
    assert res.status_code == 400
    body = res.json()
    assert body["ok"] is False
    assert "invalid arguments" in body["result"]


def test_room_capture_route_returns_layout(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/room-capture/layout",
        json={"measurements": {"width_m": 3.0, "depth_m": 2.8, "height_m": 2.6}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["layout"]["room_capture"]["measurements"]["depth_m"] == 2.8
    assert len(body["layout"]["items"]) == 5


def test_room_capture_route_returns_bad_input_error(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/room-capture/layout",
        json={
            "measurements": {"width_m": 3.0, "depth_m": 2.8, "height_m": 2.6},
            "openings": [{"wall": "ceiling"}],
        },
    )
    assert res.status_code == 400
    assert res.json()["ok"] is False


def test_floorplan_vectorize_route_returns_layout(
    chat_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_RUNTIME_ROOT", str(tmp_path))

    def fake_run_vectorize(config: object) -> dict[str, object]:
        out_dir = getattr(config, "out_dir")
        out_dir.mkdir(parents=True, exist_ok=True)
        layout_path = out_dir / "layout.json"
        layout_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "metadata": {"wall_count": 5, "opening_count": 1, "scale_m_per_px": 0.01},
                    "items": [{"type": "wall", "pos": [0, 1.3, 0], "geo": [3, 2.6, 0.15], "rot": 0}],
                }
            ),
            encoding="utf-8",
        )
        return {
            "output_layout": str(layout_path),
            "output_glb": str(out_dir / "model.glb"),
            "scale": {"m_per_px": 0.01},
            "walls": {"total_segments": 5},
            "openings": {"total": 1},
        }

    monkeypatch.setattr(chat_server, "run_vectorize", fake_run_vectorize)

    res = chat_client.post(
        "/api/floorplans/vectorize",
        data={"scale_m_per_px": "0.01", "wall_height_m": "2.7"},
        files={"file": ("plan.png", b"not-real-png", "image/png")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["layout"]["metadata"]["source_type"] == "upload"
    assert body["layout"]["metadata"]["source_filename"] == "plan.png"
    assert body["layout"]["metadata"]["calibration"]["scale_m_per_px"] == 0.01
    assert body["layout"]["items"][0]["type"] == "wall"
    assert body["artifacts"]["upload_id"]


def test_floorplan_vectorize_rejects_unsupported_file(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/floorplans/vectorize",
        files={"file": ("plan.txt", b"bad", "text/plain")},
    )

    assert res.status_code == 400
    assert res.json()["ok"] is False


def test_floorplan_vectorize_reports_failed_vectorization(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_vectorize(config: object) -> dict[str, object]:
        raise RuntimeError("vectorization failed")

    monkeypatch.setattr(chat_server, "run_vectorize", fail_vectorize)

    res = chat_client.post(
        "/api/floorplans/vectorize",
        files={"file": ("plan.png", b"not-real-png", "image/png")},
    )

    assert res.status_code == 500
    body = res.json()
    assert body["ok"] is False
    assert "vectorization failed" in body["error"]


def test_catalog_routes_return_seed_and_layout_item(
    chat_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    res = chat_client.get("/api/catalog/ikea/search?q=BILLY")
    assert res.status_code == 200
    search_body = res.json()
    assert search_body["catalog"]["source_providers"]
    item = search_body["items"][0]

    res = chat_client.post(f"/api/catalog/ikea/items/{item['id']}/layout-item", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["layout_item"]["type"] == "furniture"
    assert body["layout_item"]["catalog"]["source"] == "ikea"


def test_generic_catalog_routes_return_sources_and_non_ikea_item(
    chat_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_CATALOG_ROOT", str(tmp_path))
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    res = chat_client.get("/api/catalog/sources")
    assert res.status_code == 200
    assert any(source["id"] == "wayfair" for source in res.json()["sources"])

    res = chat_client.get("/api/catalog/search?q=sofa&sources=wayfair")
    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["source"] == "wayfair"

    res = chat_client.post(f"/api/catalog/items/{item['id']}/layout-item", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["layout_item"]["catalog"]["source"] == "wayfair"


def test_chat_status_reports_search_provider_configuration(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HAUS_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("HAUS_SEARCH_PROVIDERS", "serper,exa,tinyfish,duckduckgo")

    res = chat_client.get("/api/chat/status")
    assert res.status_code == 200
    body = res.json()

    assert body["search_providers_configured"] == ["duckduckgo"]
    assert body["search_providers_available"] == ["duckduckgo"]
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
    monkeypatch.setenv("HAUS_SEARCH_PROVIDERS", "duckduckgo")

    def fake_duckduckgo(query: str, max_results: int) -> list[dict[str, object]]:
        return [
            {
                "title": "HDB Storage",
                "url": "https://example.com/storage?utm_source=test",
                "snippet": "Built-in storage ideas",
                "source_provider": "serper",
                "published_date": None,
                "retrieved_at": "2026-06-03T00:00:00Z",
            },
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

    monkeypatch.setitem(chat_server._SEARCH_FNS, "duckduckgo", fake_duckduckgo)

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

    monkeypatch.setitem(chat_server._CHAT_FNS, "openai-compatible-local", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={
            "message": "hello",
            "provider": "openai-compatible-local",
            "model": "gpt-test-model",
        },
    )
    assert res.status_code == 200
    assert res.json()["model"] == "gpt-test-model"
    assert captured["model"] == "gpt-test-model"


def test_chat_routes_local_ollama_without_api_key(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        assert api_key == "local"
        return "local ok", messages

    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)

    res = chat_client.post("/api/chat", json={"message": "hello", "provider": "ollama"})
    assert res.status_code == 200
    body = res.json()
    assert body["response"] == "local ok"
    assert body["provider"] == "ollama"


def test_chat_rejects_agent_cli_provider_by_default(chat_client: TestClient) -> None:
    res = chat_client.post("/api/chat", json={"message": "hello", "provider": "opencode"})
    assert res.status_code == 400
    body = res.json()
    assert "not supported" in body["error"]
    assert "opencode" not in body["supported"]


@pytest.mark.parametrize("provider", ["openai-compatible-local"])
def test_chat_routes_new_local_providers_without_api_key(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
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
        return "runtime ok", messages + [{"role": "assistant", "content": [{"type": "text", "text": "runtime ok"}]}]

    monkeypatch.setitem(chat_server._CHAT_FNS, provider, fake_provider)

    res = chat_client.post("/api/chat", json={"message": "hello", "provider": provider})
    assert res.status_code == 200
    body = res.json()
    assert body["response"] == "runtime ok"
    assert body["provider"] == provider
    assert captured["api_key"] == "local"
    assert captured["model"] == chat_server._DEFAULT_MODELS[provider]


def test_openai_compatible_local_posts_chat_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(payload: dict[str, object], api_key: str) -> dict[str, object]:
        captured["payload"] = payload
        captured["api_key"] = api_key
        return {"choices": [{"message": {"content": "local response"}}]}

    monkeypatch.setattr(openai_compatible, "_post_chat", fake_post)

    text, updated = openai_compatible.chat(
        "local",
        [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        "local-model",
        lambda name, args: "{}",
        system="system",
        tools_spec=[],
        max_tool_steps=1,
    )

    assert text == "local response"
    assert captured["api_key"] == ""
    assert captured["payload"]["model"] == "local-model"
    assert updated[-1]["content"][0]["text"] == "local response"


def test_local_cli_runtime_json_tool_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        json.dumps({"tool_calls": [{"name": "list_objects", "arguments": {}}], "response": ""}),
        json.dumps({"tool_calls": [], "response": "done"}),
    ]
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_run(cmd: list[str], prompt: str, *, prompt_as_arg: bool = False) -> str:
        assert "Available Haus tools" in prompt
        return responses.pop(0)

    def dispatch(name: str, args: dict[str, object]) -> str:
        calls.append((name, args))
        return "[]"

    monkeypatch.setattr(local_cli, "_run", fake_run)
    text, updated = local_cli.chat_codex(
        "local",
        [{"role": "user", "content": [{"type": "text", "text": "what is here?"}]}],
        "default",
        dispatch,
        system="system",
        tools_spec=[{"name": "list_objects", "description": "List objects", "parameters": {"type": "object", "properties": {}}}],
        max_tool_steps=3,
    )

    assert text == "done"
    assert calls == [("list_objects", {})]
    assert updated[-1]["content"][0]["text"] == "done"


def test_local_cli_runtime_does_not_surface_invalid_agent_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        "I'm running as opencode, not inside Haus.",
        "Still not JSON.",
    ]

    def fake_run(cmd: list[str], prompt: str, *, prompt_as_arg: bool = False) -> str:
        return responses.pop(0)

    monkeypatch.setattr(local_cli, "_run", fake_run)
    text, updated = local_cli.chat_opencode(
        "local",
        [{"role": "user", "content": [{"type": "text", "text": "where are they?"}]}],
        "default",
        lambda name, args: "{}",
        system="system",
        tools_spec=[],
        max_tool_steps=2,
    )

    assert text == "The selected local model did not return a valid Haus tool response. No changes were applied."
    assert "opencode" not in updated[-1]["content"][0]["text"]


def test_chat_stream_returns_sse_events(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_stream(api_key: str, messages: list[dict[str, object]], model: str, dispatch):
        yield chat_server.ChatChunk("text", {"delta": "hel"})
        yield chat_server.ChatChunk(
            "done",
            {
                "response": "hel",
                "history": messages + [{"role": "assistant", "content": [{"type": "text", "text": "hel"}]}],
            },
        )

    monkeypatch.setitem(chat_server._STREAM_FNS, "ollama", fake_stream)

    with chat_client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "hello", "provider": "ollama"},
    ) as res:
        body = res.read().decode("utf-8")

    assert res.status_code == 200
    assert "event: meta" in body
    assert 'data: {"delta":"hel"}' in body
    assert "event: done" in body
    assert '"provider":"ollama"' in body


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
        json={"message": "   ", "provider": "openai"},
    )
    assert res.status_code == 400
    assert "must not be empty" in res.json()["error"]


def test_chat_rejects_unsupported_provider(chat_client: TestClient) -> None:
    res = chat_client.post(
        "/api/chat",
        json={"message": "hello", "provider": "unknown-provider"},
    )
    assert res.status_code == 400
    body = res.json()
    assert "not supported" in body["error"]
    assert "supported" in body


def test_chat_rejects_removed_hosted_provider(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = chat_client.post(
        "/api/chat",
        json={"message": "hello", "provider": "openai"},
    )
    assert res.status_code == 400
    assert "not supported" in res.json()["error"]


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

    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "summarize", "provider": "ollama"},
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

    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={
            "message": "make it look like this",
            "provider": "ollama",
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
            "provider": "ollama",
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
    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "find live storage references", "provider": "ollama"},
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
            "provider": "ollama",
        },
    )
    assert res.status_code == 200
    body = res.json()

    assert body["provider"] == "haus-planner"
    assert body["model"] == "llm_reviewed-concept-planner"
    assert body["pending_plan"]["status"] == "draft"
    assert body["pending_plan"]["scope"] == "whole_flat"
    assert body["pending_plan"]["planner"]["mode"] == "llm_reviewed"
    assert body["pending_plan"]["standards_profile"]["id"] == "apartment_compact"
    assert body["pending_plan"]["metrics"]["planned_item_count"] > 0
    assert body["references"][0]["url"] == "https://example.com/hdb-living"
    assert mcp_server._load_layout()["items"] == []


def test_concept_chat_without_provider_key_uses_deterministic_planner(chat_client: TestClient) -> None:
    res = chat_client.post("/api/chat", json={"message": "Design a whole 4-room HDB flat"})

    assert res.status_code == 200
    body = res.json()
    assert body["model"] == "deterministic-concept-planner"
    assert body["pending_plan"]["planner"]["mode"] == "deterministic"


def test_chat_request_can_disable_web_search_for_plans_and_tools(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_search(query: str, max_results: int = 5) -> list[dict[str, object]]:
        raise AssertionError("search_references should not be called")

    monkeypatch.setattr(chat_server, "search_references", fail_search)

    draft = chat_client.post(
        "/api/chat",
        json={"message": "Design a living room concept", "web_search_disabled": True},
    )
    assert draft.status_code == 200
    body = draft.json()
    assert body["references"] == []
    assert body["actions"][0]["args"]["web_search_disabled"] is True

    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        result = dispatch("web_search", {"query": "current furniture prices", "max_results": 1})
        return result, messages + [{"role": "assistant", "content": [{"type": "text", "text": result}]}]

    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)
    routed = chat_client.post(
        "/api/chat",
        json={
            "message": "What should I buy?",
            "provider": "ollama",
            "web_search_disabled": True,
        },
    )
    assert routed.status_code == 200
    routed_body = routed.json()
    assert "disabled by this chat session's privacy settings" in routed_body["response"]
    assert routed_body["actions"][0]["tool"] == "web_search"


def test_apply_design_plan_mutates_layout_and_tags_rooms(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_server, "search_references", lambda query, max_results=5: [])

    draft = chat_client.post(
        "/api/chat",
        json={
            "message": "Design a living room layout with clear TV sightline",
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
    assert body["validation"]["quality_profile"] == "apartment_compact"
    assert "Layout profile:" in body["validation"]["layout_quality"]

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
        json={"message": "Design a study room layout"},
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


def test_destructive_tool_requires_backend_confirmation(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert mcp_server._save_layout(
        {
            "version": 1,
            "items": [
                {
                    "type": "furniture",
                    "furnitureType": "chair",
                    "pos": [0.0, 0.225, 0.0],
                    "rot": 0.0,
                    "visible": True,
                    "geo": [0.5, 0.45, 0.5],
                    "color": 0x333333,
                }
            ],
        }
    ) is None

    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        dispatch("remove_object", {"index": 0})
        return "confirm first", messages

    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "remove the chair", "provider": "ollama"},
    )
    assert res.status_code == 200
    action = res.json()["actions"][0]
    assert action["result_json"]["requires_confirmation"] is True
    assert len(mcp_server._load_layout()["items"]) == 1

    token = action["result_json"]["confirmation"]["token"]
    confirmed = chat_client.post(f"/api/tool-confirmations/{token}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["ok"] is True
    assert mcp_server._load_layout()["items"] == []


def test_expired_confirmation_token_returns_recovery_error(chat_client: TestClient) -> None:
    res = chat_client.post("/api/tool-confirmations/expired-token/confirm")

    assert res.status_code == 404
    body = res.json()
    assert body["ok"] is False
    assert "expired" in body["error"]


def test_tool_args_reject_unknown_fields_without_executing(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_provider(
        api_key: str,
        messages: list[dict[str, object]],
        model: str,
        dispatch,
    ) -> tuple[str, list[dict[str, object]]]:
        dispatch("add_furniture", {"furniture_type": "chair", "x": 0, "z": 0, "surprise": True})
        return "done", messages

    monkeypatch.setitem(chat_server._CHAT_FNS, "ollama", fake_provider)

    res = chat_client.post(
        "/api/chat",
        json={"message": "add a chair", "provider": "ollama"},
    )
    assert res.status_code == 200
    action = res.json()["actions"][0]
    assert "invalid arguments" in action["result"]
    assert mcp_server._load_layout()["items"] == []
