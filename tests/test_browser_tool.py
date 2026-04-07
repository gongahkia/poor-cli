"""Tests for browser automation tool declarations and state management."""
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from poor_cli.browser_tool import (
    BROWSER_TOOLS,
    BROWSER_TOOL_DECLARATIONS,
    _browser_context,
    shutdown_browser,
)


class TestBrowserToolDeclarations(unittest.TestCase):
    def test_five_tools_declared(self):
        self.assertEqual(len(BROWSER_TOOL_DECLARATIONS), 5)

    def test_five_tools_in_dict(self):
        self.assertEqual(len(BROWSER_TOOLS), 5)

    def test_declaration_names_match_dict(self):
        decl_names = {d["name"] for d in BROWSER_TOOL_DECLARATIONS}
        dict_names = set(BROWSER_TOOLS.keys())
        self.assertEqual(decl_names, dict_names)

    def test_expected_tool_names(self):
        names = {d["name"] for d in BROWSER_TOOL_DECLARATIONS}
        expected = {"browser_navigate", "browser_screenshot", "browser_click", "browser_type", "browser_evaluate"}
        self.assertEqual(names, expected)

    def test_all_declarations_have_required_fields(self):
        for decl in BROWSER_TOOL_DECLARATIONS:
            self.assertIn("name", decl)
            self.assertIn("description", decl)
            self.assertIn("parameters", decl)
            self.assertIn("type", decl["parameters"])
            self.assertEqual(decl["parameters"]["type"], "OBJECT")

    def test_navigate_requires_url(self):
        nav = next(d for d in BROWSER_TOOL_DECLARATIONS if d["name"] == "browser_navigate")
        self.assertIn("url", nav["parameters"]["properties"])
        self.assertIn("url", nav["parameters"]["required"])

    def test_click_requires_selector(self):
        click = next(d for d in BROWSER_TOOL_DECLARATIONS if d["name"] == "browser_click")
        self.assertIn("selector", click["parameters"]["properties"])
        self.assertIn("selector", click["parameters"]["required"])

    def test_type_requires_selector_and_text(self):
        t = next(d for d in BROWSER_TOOL_DECLARATIONS if d["name"] == "browser_type")
        self.assertIn("selector", t["parameters"]["required"])
        self.assertIn("text", t["parameters"]["required"])

    def test_evaluate_requires_expression(self):
        ev = next(d for d in BROWSER_TOOL_DECLARATIONS if d["name"] == "browser_evaluate")
        self.assertIn("expression", ev["parameters"]["required"])

    def test_screenshot_no_required_params(self):
        ss = next(d for d in BROWSER_TOOL_DECLARATIONS if d["name"] == "browser_screenshot")
        self.assertEqual(ss["parameters"].get("required", []), [])


class TestBrowserToolCallable(unittest.TestCase):
    def test_all_tools_are_coroutines(self):
        import inspect
        for name, fn in BROWSER_TOOLS.items():
            self.assertTrue(inspect.iscoroutinefunction(fn), f"{name} should be async")


class TestBrowserContextState(unittest.TestCase):
    def test_initial_state_is_none(self):
        # after module load, no browser should be running
        self.assertIsNone(_browser_context["browser"])
        self.assertIsNone(_browser_context["page"])
        self.assertIsNone(_browser_context["playwright"])

    def test_shutdown_clears_state(self):
        _browser_context["browser"] = MagicMock()
        _browser_context["browser"].close = AsyncMock()
        _browser_context["playwright"] = MagicMock()
        _browser_context["playwright"].stop = AsyncMock()
        _browser_context["page"] = MagicMock()
        asyncio.run(shutdown_browser())
        self.assertIsNone(_browser_context["browser"])
        self.assertIsNone(_browser_context["page"])
        self.assertIsNone(_browser_context["playwright"])

    def test_shutdown_tolerates_none(self):
        _browser_context.update(browser=None, page=None, playwright=None)
        asyncio.run(shutdown_browser()) # should not raise


class TestEnsureBrowserImportError(unittest.TestCase):
    def test_raises_on_missing_playwright(self):
        from poor_cli.browser_tool import _ensure_browser
        _browser_context.update(browser=None, page=None, playwright=None)
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            with self.assertRaises(Exception): # RuntimeError or ImportError
                asyncio.run(_ensure_browser())


class TestBrowserCrashRecovery(unittest.TestCase):
    def test_dead_page_triggers_relaunch(self):
        from poor_cli.browser_tool import _ensure_browser
        mock_page = MagicMock()
        mock_page.title = AsyncMock(side_effect=Exception("page crashed"))
        _browser_context.update(browser=MagicMock(), page=mock_page, playwright=MagicMock())
        _browser_context["browser"].close = AsyncMock()
        _browser_context["playwright"].stop = AsyncMock()
        # should attempt relaunch (and fail at playwright import)
        with patch.dict("sys.modules", {"playwright": None, "playwright.async_api": None}):
            with self.assertRaises(Exception):
                asyncio.run(_ensure_browser())
        # context should be cleared from shutdown
        self.assertIsNone(_browser_context["browser"])


class TestBrowserAuditLogging(unittest.TestCase):
    @patch("poor_cli.browser_tool._log_browser_event")
    def test_log_helper_callable(self, mock_log):
        from poor_cli.browser_tool import _log_browser_event
        _log_browser_event("test", "target", {"key": "val"})
        # just verify it doesn't crash


if __name__ == "__main__":
    unittest.main()
