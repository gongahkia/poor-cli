from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None
pytestmark = pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="Playwright is required for frontend E2E checks")
if HAS_PLAYWRIGHT:
    from playwright.sync_api import sync_playwright


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(url: str, proc: subprocess.Popen[str], timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise AssertionError(f"haus view exited early with {proc.returncode}: {stderr}")
        try:
            with urlopen(url, timeout=1.0) as res:
                if res.status < 500:
                    return
        except URLError as exc:
            last_error = exc
        time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


@pytest.fixture(scope="module")
def web_base_url() -> str:
    web_root = Path(__file__).resolve().parents[1] / "src" / "haus" / "web"

    class QuietStaticHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

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
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Playwright browser not available: {exc}")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            yield page
        finally:
            page.close()
            browser.close()


@pytest.fixture()
def haus_view_url():
    port = _free_port()
    env = os.environ.copy()
    env["BROWSER"] = "true"
    env["HAUS_ENABLE_WEB_SEARCH"] = "0"
    proc = subprocess.Popen(
        [sys.executable, "-m", "haus.cli", "view", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_http(f"{base}/api/health", proc)
        yield base
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


def _status_payload() -> dict[str, object]:
    return {
        "available": True,
        "providers_with_env_keys": [],
        "supported_providers": ["openai", "webllm", "codex"],
        "default_models": {"openai": "gpt-4o", "webllm": "Llama-3.1-8B-Instruct-q4f32_1-MLC", "codex": "default"},
        "providers": [
            {
                "id": "openai",
                "label": "OpenAI",
                "requires_api_key": True,
                "command_available": None,
                "capabilities": ["tools", "streaming"],
                "models": [{"id": "gpt-4o", "label": "GPT-4o", "default": True, "capabilities": ["tools"]}],
            },
            {
                "id": "webllm",
                "label": "WebLLM",
                "requires_api_key": False,
                "command_available": None,
                "capabilities": ["chat", "tools", "browser_runtime", "webgpu"],
                "models": [{"id": "Llama-3.1-8B-Instruct-q4f32_1-MLC", "label": "WebLLM default", "default": True}],
            },
            {
                "id": "codex",
                "label": "Codex runtime",
                "requires_api_key": False,
                "command_available": False,
                "capabilities": ["chat", "tools", "local_runtime"],
                "models": [{"id": "default", "label": "Codex default", "default": True}],
            },
        ],
        "capabilities": {
            "provider_native_streaming": True,
            "planner_modes": ["auto", "deterministic", "llm_reviewed", "llm_structured"],
            "default_planner_mode": "auto",
            "standards_profiles": ["apartment_compact", "accessible"],
            "image_mime_types": ["image/png", "image/jpeg", "image/webp"],
            "max_image_attachments": 3,
            "max_image_attachment_mb": 5,
        },
    }


def _mock_api(page) -> dict[str, object]:
    calls: dict[str, object] = {"sync": 0, "chat_payload": None}
    page.route("**/api/chat/status", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(_status_payload())))
    page.route("**/api/health", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})))
    page.route("**/api/chat/tools", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"tools": []})))

    def sync_handler(route) -> None:
        calls["sync"] = int(calls["sync"]) + 1
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "warnings": []}))

    def chat_handler(route) -> None:
        payload = json.loads(route.request.post_data or "{}")
        calls["chat_payload"] = payload
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "response": "Applied safely.",
                    "history": [{"role": "assistant", "content": [{"type": "text", "text": "Applied safely."}]}],
                    "provider": payload.get("provider"),
                    "model": "gpt-4o",
                    "actions": [],
                    "request_id": "chat-e2e-1",
                }
            ),
        )

    page.route("**/api/sync-layout", sync_handler)
    page.route("**/api/chat", chat_handler)
    return calls


def test_root_svelte_app_loads_and_drawers_toggle(browser_page, web_base_url: str) -> None:
    _mock_api(browser_page)
    browser_page.goto(f"{web_base_url}/")
    browser_page.wait_for_selector("text=Haus Planner")
    assert browser_page.locator(".scene-canvas canvas").count() == 1

    browser_page.click("#actions-toggle")
    assert "open" in browser_page.locator("#toolbar").get_attribute("class")
    browser_page.click("#tools-toggle")
    assert "open" in browser_page.locator("#sidebar").get_attribute("class")


def test_chat_syncs_browser_layout_before_backend_tools(browser_page, web_base_url: str) -> None:
    calls = _mock_api(browser_page)
    browser_page.add_init_script(
        """
        localStorage.setItem("haus.api_keys", JSON.stringify({ openai: "test-key" }));
        localStorage.setItem("haus.settings", JSON.stringify({ provider: "openai" }));
        """
    )
    browser_page.goto(f"{web_base_url}/")
    browser_page.wait_for_selector("#chat-input")
    browser_page.fill("#chat-input", "Move sofa 0.5m right")
    browser_page.click("#chat-send")
    browser_page.wait_for_selector("text=Applied safely.", timeout=6000)

    assert int(calls["sync"]) >= 1
    payload = calls["chat_payload"]
    assert isinstance(payload, dict)
    assert payload["provider"] == "openai"
    assert payload["project_context"]["layout"]["items"] == []


def test_catalog_search_places_item(browser_page, web_base_url: str) -> None:
    _mock_api(browser_page)
    browser_page.route(
        "**/api/catalog/ikea/search?*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "items": [{"id": "ikea-sofa", "name": "Test IKEA sofa", "category": "sofa"}], "catalog": {"fallback_used": False}}),
        ),
    )
    browser_page.route(
        "**/api/catalog/ikea/items/ikea-sofa/layout-item",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "ok": True,
                    "item": {"id": "ikea-sofa", "name": "Test IKEA sofa"},
                    "layout_item": {"id": "item-sofa", "type": "furniture", "pos": [0, 0.4, 0], "geo": [2, 0.8, 0.9], "rot": 0, "name": "Test IKEA sofa"},
                }
            ),
        ),
    )
    browser_page.goto(f"{web_base_url}/")
    browser_page.click("#tools-toggle")
    browser_page.fill("input[placeholder='sofa, desk, BILLY...']", "sofa")
    browser_page.click("section:has-text('IKEA Catalog') button")
    browser_page.wait_for_selector("text=Test IKEA sofa")
    browser_page.click("article:has-text('Test IKEA sofa') button")
    browser_page.wait_for_selector("text=1 items")


def test_haus_view_serves_root_app(haus_view_url: str) -> None:
    with urlopen(f"{haus_view_url}/", timeout=5) as res:
        html = res.read().decode("utf-8")
    assert res.status == 200
    assert "Haus Planner" in html or "/assets/" in html
