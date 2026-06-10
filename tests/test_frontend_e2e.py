from __future__ import annotations

import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api", reason="Playwright is required for frontend E2E checks")


@pytest.fixture(scope="module")
def viewer_base_url() -> str:
    project_root = Path(__file__).resolve().parents[1]

    class QuietStaticHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(project_root), **kwargs)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietStaticHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def browser_page():
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - environment dependent
            pytest.skip(f"Playwright browser not available: {exc}")
        page = browser.new_page()
        try:
            yield page
        finally:
            page.close()
            browser.close()


def _mock_editor_backend(page) -> None:
    page.route(
        "**/api/chat/status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "available": True,
                    "providers_with_env_keys": [],
                    "supported_providers": ["openai", "anthropic", "gemini"],
                    "default_models": {"openai": "gpt-4o"},
                    "search_providers_configured": ["duckduckgo"],
                    "search_providers_available": ["duckduckgo"],
                    "search_fallback_provider": "duckduckgo",
                    "capabilities": {
                        "web_search": True,
                        "web_fetch": True,
                        "image_references": True,
                        "design_plans": True,
                        "planner_requires_api_key": False,
                        "planner_modes": ["auto", "deterministic", "llm_reviewed", "llm_structured"],
                        "default_planner_mode": "auto",
                        "destructive_confirmation": True,
                        "strict_tool_validation": True,
                        "standards_profiles": [
                            "apartment_compact",
                            "compact_hdb",
                            "comfortable_home",
                            "accessible",
                            "rental_room",
                            "hdb_bto",
                            "kitchen_basic",
                            "bedroom_basic",
                            "bathroom_basic",
                        ],
                        "max_image_attachments": 3,
                        "max_image_attachment_mb": 5,
                        "image_mime_types": ["image/png", "image/jpeg", "image/webp", "image/gif"],
                    },
                }
            ),
        ),
    )
    page.route(
        "**/viewer/mcp-layout.json*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"version": 1, "items": [], "_stamp": 1}),
        ),
    )


def test_sync_retries_after_failed_pushes(browser_page, viewer_base_url: str) -> None:
    _mock_editor_backend(browser_page)

    attempts = {"count": 0}

    def sync_handler(route) -> None:
        attempts["count"] += 1
        if attempts["count"] < 3:
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"ok": False}))
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

    browser_page.route("**/api/sync-layout", sync_handler)
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.wait_for_timeout(7000)
    assert attempts["count"] >= 3


def test_import_json_warns_on_malformed_layout(browser_page, viewer_base_url: str) -> None:
    _mock_editor_backend(browser_page)
    browser_page.route(
        "**/api/sync-layout",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})),
    )

    browser_page.add_init_script(
        """
        window.__hausWarnings = [];
        const originalWarn = console.warn.bind(console);
        console.warn = (...args) => {
          window.__hausWarnings.push(args.map(String).join(" "));
          originalWarn(...args);
        };
        """
    )
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.set_input_files(
        "#json-input",
        {
            "name": "malformed-layout.json",
            "mimeType": "application/json",
            "buffer": json.dumps({"unexpected": "shape"}).encode("utf-8"),
        },
    )
    browser_page.wait_for_function(
        """
        () => window.__hausWarnings?.some((warning) =>
          warning.includes("JSON import missing items array")
        )
        """
    )


def test_chat_transcript_persists_across_reload(browser_page, viewer_base_url: str) -> None:
    _mock_editor_backend(browser_page)
    browser_page.route(
        "**/api/sync-layout",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})),
    )

    def chat_handler(route) -> None:
        request_payload = json.loads(route.request.post_data or "{}")
        text = request_payload.get("message", "")
        history = request_payload.get("history", [])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "response": "Applied safely.",
                    "history": history
                    + [
                        {"role": "user", "content": text},
                        {"role": "assistant", "content": [{"type": "text", "text": "Applied safely."}]},
                    ],
                    "provider": "openai",
                    "model": "gpt-4o",
                    "actions": [],
                    "request_id": "chat-e2e-1",
                }
            ),
        )

    browser_page.route("**/api/chat", chat_handler)
    browser_page.add_init_script(
        """
        localStorage.setItem("haus_api_keys", JSON.stringify({ openai: "test-key" }));
        localStorage.setItem("haus_chat_provider", "openai");
        if (!sessionStorage.getItem("haus_chat_e2e_seeded")) {
          localStorage.removeItem("haus_chat_history");
          localStorage.removeItem("haus_chat_transcript");
          sessionStorage.setItem("haus_chat_e2e_seeded", "1");
        }
        """
    )
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.click("#chat-btn")
    browser_page.fill("#chat-input", "Move sofa 0.5m right")
    browser_page.click("#chat-send")
    browser_page.wait_for_selector(".chat-assistant", timeout=6000)

    transcript_before = browser_page.locator("#chat-messages").inner_text()
    assert "Move sofa 0.5m right" in transcript_before
    assert "Applied safely." in transcript_before

    browser_page.reload(wait_until="domcontentloaded")
    browser_page.wait_for_selector("#chat-btn")
    browser_page.click("#chat-btn")
    browser_page.wait_for_function(
        """
        () => document.querySelector("#chat-panel")?.classList.contains("open")
          && document.querySelector("#chat-messages")?.innerText.includes("Applied safely.")
        """
    )

    transcript_after = browser_page.locator("#chat-messages").inner_text()
    assert "Move sofa 0.5m right" in transcript_after
    assert "Applied safely." in transcript_after


def test_chat_sends_image_reference_attachment(browser_page, viewer_base_url: str) -> None:
    _mock_editor_backend(browser_page)
    browser_page.route(
        "**/api/sync-layout",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})),
    )

    captured: dict[str, object] = {}

    def chat_handler(route) -> None:
        payload = json.loads(route.request.post_data or "{}")
        captured["payload"] = payload
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "response": "Reference applied.",
                    "history": [{"role": "assistant", "content": [{"type": "text", "text": "Reference applied."}]}],
                    "provider": "openai",
                    "model": "gpt-4o",
                    "actions": [],
                    "request_id": "chat-e2e-image-1",
                }
            ),
        )

    browser_page.route("**/api/chat", chat_handler)
    browser_page.add_init_script(
        """
        localStorage.setItem("haus_api_keys", JSON.stringify({ openai: "test-key" }));
        localStorage.setItem("haus_chat_provider", "openai");
        localStorage.removeItem("haus_chat_history");
        localStorage.removeItem("haus_chat_transcript");
        """
    )
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.click("#chat-btn")
    browser_page.set_input_files(
        "#chat-image-input",
        {
            "name": "reference.png",
            "mimeType": "image/png",
            "buffer": b"\x89PNG\r\n\x1a\nreference",
        },
    )
    browser_page.fill("#chat-input", "Replicate this vibe")
    browser_page.click("#chat-send")
    browser_page.wait_for_selector(".chat-assistant", timeout=6000)

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["message"] == "Replicate this vibe"
    assert len(payload["attachments"]) == 1
    assert payload["attachments"][0]["name"] == "reference.png"
    assert payload["attachments"][0]["mime_type"] == "image/png"
    assert payload["attachments"][0]["data_url"].startswith("data:image/png;base64,")

    transcript = browser_page.locator("#chat-messages").inner_text()
    assert "Attached 1 image reference: reference.png" in transcript
    assert "Reference applied." in transcript
    stored_transcript = browser_page.evaluate("() => localStorage.getItem('haus_chat_transcript')")
    assert "data:image/png;base64" not in stored_transcript


def test_chat_allows_deterministic_planner_without_key(browser_page, viewer_base_url: str) -> None:
    _mock_editor_backend(browser_page)
    browser_page.route(
        "**/api/sync-layout",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})),
    )
    captured: dict[str, object] = {}

    def chat_handler(route) -> None:
        payload = json.loads(route.request.post_data or "{}")
        captured["payload"] = payload
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "response": "Drafted deterministic plan.",
                    "history": [{"role": "assistant", "content": [{"type": "text", "text": "Drafted deterministic plan."}]}],
                    "provider": "haus-planner",
                    "model": "deterministic-concept-planner",
                    "actions": [],
                    "request_id": "chat-no-key",
                }
            ),
        )

    browser_page.route("**/api/chat", chat_handler)
    browser_page.add_init_script(
        """
        localStorage.removeItem("haus_api_keys");
        localStorage.removeItem("haus_chat_provider");
        localStorage.removeItem("haus_chat_history");
        localStorage.removeItem("haus_chat_transcript");
        """
    )
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.fill("#chat-input", "Design a compact 4-room HDB")
    browser_page.click("#chat-send")
    browser_page.wait_for_selector(".chat-assistant", timeout=6000)
    assert captured["payload"]["api_key"] == ""
    assert captured["payload"]["planner_mode"] == "auto"
    assert "Drafted deterministic plan." in browser_page.locator("#chat-messages").inner_text()


def test_chat_renders_pending_plan_and_plan_actions(browser_page, viewer_base_url: str) -> None:
    _mock_editor_backend(browser_page)
    browser_page.route(
        "**/api/sync-layout",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})),
    )

    plan = {
        "id": "plan-e2e-1",
        "title": "Whole-flat concept plan",
        "brief": "Design a compact 4-room HDB",
        "scope": "whole_flat",
        "status": "draft",
        "web_references": [
            {
                "title": "HDB design reference",
                "url": "https://example.com/hdb",
                "snippet": "Reference",
                "source_provider": "serper",
                "published_date": None,
                "retrieved_at": "2026-06-03T00:00:00Z",
            }
        ],
        "zones": [
            {
                "name": "Living",
                "intent": "family living",
                "target_center": {"x": 0, "z": 0},
                "planned_furniture": [
                    {"label": "lounge sofa", "furniture_type": "sofa_l"},
                    {"label": "tv console", "furniture_type": "tv_console"},
                ],
                "estimated_area_m2": 10.5,
                "circulation_notes": "Keep a clear primary walkway.",
            }
        ],
        "planned_items": [],
        "metrics": {
            "zone_count": 1,
            "planned_item_count": 2,
            "walkway_target_m": 0.9,
            "reference_count": 1,
        },
        "planner": {"mode": "llm_reviewed", "label": "LLM-reviewed Haus planner"},
        "confidence": "medium-high",
        "standards_profile": {
            "id": "comfortable_home",
            "label": "Comfortable home circulation",
            "notes": "Everyday comfort target for repeated use.",
        },
        "apply_readiness": "ready_to_apply",
        "assumptions": [],
        "validation_targets": [],
        "rationale": [],
    }

    def chat_handler(route) -> None:
        payload = json.loads(route.request.post_data or "{}")
        assert payload.get("api_key", "") == "test-key"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "response": "Drafted a concept plan.",
                    "history": [{"role": "assistant", "content": [{"type": "text", "text": "Drafted a concept plan."}]}],
                    "provider": "haus-planner",
                    "model": "deterministic-concept-planner",
                    "actions": [],
                    "pending_plan": plan,
                    "references": plan["web_references"],
                    "request_id": "chat-plan-e2e",
                }
            ),
        )

    apply_calls = {"count": 0}

    def apply_handler(route) -> None:
        apply_calls["count"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "ok": True,
                    "summary": "Applied plan plan-e2e-1: added 2 item(s) across 1 zone(s).",
                    "plan": {**plan, "status": "applied"},
                    "actions": [{"tool": "tag_room", "args": {"indices": [0, 1]}, "result": "Tagged 2 object(s)."}],
                    "validation": {"layout_summary": "Total objects: 2"},
                }
            ),
        )

    browser_page.route("**/api/chat", chat_handler)
    browser_page.route("**/api/design-plans/plan-e2e-1/apply", apply_handler)
    browser_page.add_init_script(
        """
        localStorage.setItem("haus_api_keys", JSON.stringify({ openai: "test-key" }));
        localStorage.setItem("haus_chat_provider", "openai");
        localStorage.removeItem("haus_chat_history");
        localStorage.removeItem("haus_chat_transcript");
        """
    )
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.click("#chat-btn")
    browser_page.fill("#chat-input", "Design a compact 4-room HDB")
    browser_page.click("#chat-send")
    browser_page.wait_for_selector(".chat-plan-card", timeout=6000)

    card_text = browser_page.locator(".chat-plan-card").inner_text()
    assert "Whole-flat concept plan" in card_text
    assert "0.9m" in card_text
    assert "LLM-reviewed Haus planner" in card_text
    assert "Comfortable home circulation" in card_text
    assert "HDB design reference" in card_text

    browser_page.get_by_role("button", name="Revise").click()
    assert browser_page.locator("#chat-input").input_value() == "Revise plan plan-e2e-1: "

    browser_page.get_by_role("button", name="Apply").click()
    browser_page.wait_for_function(
        "() => document.querySelector('#chat-messages')?.innerText.includes('Applied plan plan-e2e-1')"
    )
    assert apply_calls["count"] == 1


def test_chat_renders_and_confirms_destructive_tool_card(browser_page, viewer_base_url: str) -> None:
    _mock_editor_backend(browser_page)
    browser_page.route(
        "**/api/sync-layout",
        lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})),
    )
    browser_page.route(
        "**/api/chat",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "response": "Confirm before removing.",
                    "history": [{"role": "assistant", "content": [{"type": "text", "text": "Confirm before removing."}]}],
                    "provider": "openai",
                    "model": "gpt-4o",
                    "actions": [
                        {
                            "tool": "remove_object",
                            "args": {"index": 0},
                            "result": json.dumps(
                                {
                                    "ok": False,
                                    "requires_confirmation": True,
                                    "confirmation": {
                                        "token": "confirm-e2e",
                                        "tool": "remove_object",
                                        "args": {"index": 0},
                                        "summary": "Remove object index 0 from the current layout.",
                                    },
                                }
                            ),
                            "result_json": {
                                "ok": False,
                                "requires_confirmation": True,
                                "confirmation": {
                                    "token": "confirm-e2e",
                                    "tool": "remove_object",
                                    "args": {"index": 0},
                                    "summary": "Remove object index 0 from the current layout.",
                                },
                            },
                            "elapsed_ms": 2,
                        }
                    ],
                    "request_id": "chat-confirm-card",
                }
            ),
        ),
    )
    browser_page.route(
        "**/api/tool-confirmations/confirm-e2e/confirm",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "ok": True,
                    "summary": "Removed [0] chair.",
                    "actions": [{"tool": "remove_object", "args": {"index": 0}, "result": "Removed [0] chair.", "elapsed_ms": 1}],
                }
            ),
        ),
    )
    browser_page.add_init_script(
        """
        localStorage.setItem("haus_api_keys", JSON.stringify({ openai: "test-key" }));
        localStorage.setItem("haus_chat_provider", "openai");
        localStorage.removeItem("haus_chat_history");
        localStorage.removeItem("haus_chat_transcript");
        """
    )
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.fill("#chat-input", "Remove object 0")
    browser_page.click("#chat-send")
    browser_page.wait_for_selector(".chat-confirm-card", timeout=6000)
    assert "Confirmation required" in browser_page.locator(".chat-confirm-card").inner_text()

    browser_page.get_by_role("button", name="Confirm").click()
    browser_page.wait_for_function(
        "() => document.querySelector('#chat-messages')?.innerText.includes('Removed [0] chair.')"
    )
