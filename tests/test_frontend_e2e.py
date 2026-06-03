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

    warnings: list[str] = []

    def on_console(msg) -> None:
        if msg.type == "warning":
            warnings.append(msg.text)

    browser_page.on("console", on_console)
    browser_page.goto(f"{viewer_base_url}/viewer/editor.html")

    browser_page.set_input_files(
        "#json-input",
        {
            "name": "malformed-layout.json",
            "mimeType": "application/json",
            "buffer": json.dumps({"unexpected": "shape"}).encode("utf-8"),
        },
    )
    browser_page.wait_for_timeout(400)

    assert any("JSON import missing items array" in warning for warning in warnings)


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

    browser_page.reload(wait_until="networkidle")
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
