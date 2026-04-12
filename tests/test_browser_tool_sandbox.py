"""Tests for browser_evaluate policy hardening."""

from __future__ import annotations

import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.browser_tool import (
    BrowserEvalBlocked,
    BrowserEvalSerializationError,
    BrowserEvalTimeout,
    browser_evaluate,
    browser_navigate,
    set_browser_permission_callback,
    shutdown_browser,
    _browser_context,
    _scan_dangerous_js,
)


class BrowserEvalPolicyUnitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.audit = patch("poor_cli.browser_tool._log_browser_event").start()
        set_browser_permission_callback(None)
        _browser_context.update(browser=None, page=None, playwright=None)

    def tearDown(self) -> None:
        set_browser_permission_callback(None)
        _browser_context.update(browser=None, page=None, playwright=None)
        patch.stopall()

    def test_denylist_patterns_are_individual_regexes(self) -> None:
        cases = {
            "localStorage.clear()": r"localStorage\s*\.\s*clear",
            "sessionStorage . clear()": r"sessionStorage\s*\.\s*clear",
            'document.cookie = "x=1"': r"document\s*\.\s*cookie\s*=",
            'navigator.sendBeacon("/x")': r"navigator\s*\.\s*sendBeacon",
            'window.location = "/"': r"window\s*\.\s*location\s*=",
            'indexedDB.deleteDatabase("db")': r"indexedDB\s*\.\s*deleteDatabase",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(_scan_dangerous_js(source), [expected])

    async def test_local_storage_clear_blocked_before_browser_launch(self) -> None:
        with self.assertRaises(BrowserEvalBlocked):
            await browser_evaluate("localStorage.clear()")
        self.assertEqual(_browser_context["page"], None)

    async def test_allow_dangerous_without_permission_is_rejected(self) -> None:
        with self.assertRaises(BrowserEvalBlocked):
            await browser_evaluate("'ok'", allow_dangerous=True)

    async def test_allow_dangerous_routes_permission_callback(self) -> None:
        calls = []

        async def callback(tool_name, tool_args, preview):
            calls.append((tool_name, tool_args, preview))
            return {"allowed": True}

        page = MagicMock()
        page.url = "http://127.0.0.1/"
        page.title = AsyncMock(return_value="fixture")
        page.evaluate = AsyncMock(return_value=json.dumps("ok"))
        _browser_context.update(browser=MagicMock(), page=page, playwright=MagicMock())
        set_browser_permission_callback(callback)

        self.assertEqual(await browser_evaluate("'ok'", allow_dangerous=True), "ok")
        self.assertEqual(calls[0][0], "browser_evaluate")
        self.assertTrue(calls[0][1]["allow_dangerous"])

    async def test_audit_event_has_hash_and_outcome(self) -> None:
        page = MagicMock()
        page.url = "http://127.0.0.1/"
        page.title = AsyncMock(return_value="fixture")
        page.evaluate = AsyncMock(return_value=json.dumps(2))
        _browser_context.update(browser=MagicMock(), page=page, playwright=MagicMock())

        self.assertEqual(await browser_evaluate("1 + 1"), "2")
        args, kwargs = self.audit.call_args
        self.assertEqual(args[0], "evaluate")
        self.assertEqual(len(args[1]), 64)
        self.assertEqual(args[2]["outcome"], "success")
        self.assertTrue(kwargs["success"])

    async def test_fetch_allowlist_requires_permission(self) -> None:
        page = MagicMock()
        page.url = "http://127.0.0.1/"
        page.title = AsyncMock(return_value="fixture")
        page.evaluate = AsyncMock(return_value=json.dumps("bad"))
        _browser_context.update(browser=MagicMock(), page=page, playwright=MagicMock())

        with self.assertRaises(BrowserEvalBlocked):
            await browser_evaluate("'ok'", allowed_fetch_origins=["https://example.com"])
        page.evaluate.assert_not_called()


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/data":
            body = b"same-origin-ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"<html><head><title>fixture</title></head><body><div id='msg'>hello</div></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def _playwright_available() -> bool:
    try:
        return importlib.util.find_spec("playwright.async_api") is not None
    except ModuleNotFoundError:
        return False


@unittest.skipUnless(_playwright_available(), "playwright not installed")
class BrowserEvalLocalFixtureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.audit = patch("poor_cli.browser_tool._log_browser_event").start()
        set_browser_permission_callback(None)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    async def asyncSetUp(self) -> None:
        try:
            await browser_navigate(self.origin)
        except Exception as error:
            self.skipTest(str(error))

    async def asyncTearDown(self) -> None:
        await shutdown_browser()

    def tearDown(self) -> None:
        set_browser_permission_callback(None)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        patch.stopall()

    async def test_innocent_js_runs(self) -> None:
        self.assertEqual(await browser_evaluate("document.querySelector('#msg').textContent"), "hello")

    async def test_same_origin_fetch_allowed(self) -> None:
        self.assertEqual(await browser_evaluate("fetch('/data').then(r => r.text())"), "same-origin-ok")

    async def test_third_party_fetch_denied_by_default(self) -> None:
        with self.assertRaises(BrowserEvalBlocked):
            await browser_evaluate("fetch('https://example.com/leak')")

    async def test_output_truncated(self) -> None:
        self.assertEqual(await browser_evaluate("'abcdef'", max_output=3), "abc...[truncated 3 chars]")

    async def test_timeout_is_typed(self) -> None:
        with self.assertRaises(BrowserEvalTimeout):
            await browser_evaluate("new Promise(resolve => setTimeout(() => resolve('late'), 100))", timeout_ms=10)

    async def test_non_json_result_rejected(self) -> None:
        with self.assertRaises(BrowserEvalSerializationError):
            await browser_evaluate("undefined")
