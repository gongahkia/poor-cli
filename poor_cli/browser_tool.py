"""Browser automation tools using Playwright for headless browsing."""

from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)

_browser_context: Dict[str, Any] = {"browser": None, "page": None, "playwright": None}


async def _ensure_browser() -> Any:
    """Lazy-init headless Chromium, return active page."""
    if _browser_context["page"] is not None:
        return _browser_context["page"]
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed. Run: pip install playwright && playwright install chromium")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    _browser_context.update(playwright=pw, browser=browser, page=page)
    logger.info("launched headless Chromium")
    return page


async def shutdown_browser() -> None:
    """Clean up browser resources."""
    if _browser_context["browser"]:
        try:
            await _browser_context["browser"].close()
        except Exception:
            pass
    if _browser_context["playwright"]:
        try:
            await _browser_context["playwright"].stop()
        except Exception:
            pass
    _browser_context.update(browser=None, page=None, playwright=None)


async def browser_navigate(url: str, wait_until: str = "domcontentloaded") -> str:
    """Navigate to a URL and return page title + text excerpt."""
    page = await _ensure_browser()
    response = await page.goto(url, wait_until=wait_until, timeout=30000)
    status = response.status if response else "unknown"
    title = await page.title()
    text = await page.inner_text("body")
    text = text[:3000].strip() if text else ""
    return f"[{status}] {title}\n\n{text}"


async def browser_screenshot(selector: Optional[str] = None, full_page: bool = False) -> str:
    """Take a screenshot, return as base64 PNG."""
    page = await _ensure_browser()
    if selector:
        element = await page.query_selector(selector)
        if not element:
            return f"error: selector '{selector}' not found"
        screenshot_bytes = await element.screenshot(type="png")
    else:
        screenshot_bytes = await page.screenshot(type="png", full_page=full_page)
    encoded = base64.b64encode(screenshot_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


async def browser_click(selector: str) -> str:
    """Click an element by CSS selector."""
    page = await _ensure_browser()
    try:
        await page.click(selector, timeout=10000)
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        title = await page.title()
        return f"clicked '{selector}', page: {title}"
    except Exception as e:
        return f"error clicking '{selector}': {e}"


async def browser_type(selector: str, text: str, submit: bool = False) -> str:
    """Type text into an input field."""
    page = await _ensure_browser()
    try:
        await page.fill(selector, text, timeout=10000)
        if submit:
            await page.press(selector, "Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        return f"typed into '{selector}'"
    except Exception as e:
        return f"error typing into '{selector}': {e}"


async def browser_evaluate(expression: str) -> str:
    """Evaluate JavaScript in the page context."""
    page = await _ensure_browser()
    try:
        result = await page.evaluate(expression)
        return str(result)[:5000]
    except Exception as e:
        return f"error evaluating JS: {e}"


# tool declarations for registration
BROWSER_TOOL_DECLARATIONS = [
    {
        "name": "browser_navigate",
        "description": "Navigate to a URL in a headless browser and return page content",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "URL to navigate to"},
                "wait_until": {"type": "STRING", "description": "Wait condition: domcontentloaded, load, networkidle (default: domcontentloaded)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "Take a screenshot of the current page or a specific element",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "selector": {"type": "STRING", "description": "CSS selector of element to screenshot (omit for full page)"},
                "full_page": {"type": "BOOLEAN", "description": "Capture full scrollable page (default: false)"},
            },
            "required": [],
        },
    },
    {
        "name": "browser_click",
        "description": "Click an element on the page by CSS selector",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "selector": {"type": "STRING", "description": "CSS selector of element to click"},
            },
            "required": ["selector"],
        },
    },
    {
        "name": "browser_type",
        "description": "Type text into an input field on the page",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "selector": {"type": "STRING", "description": "CSS selector of input element"},
                "text": {"type": "STRING", "description": "Text to type"},
                "submit": {"type": "BOOLEAN", "description": "Press Enter after typing (default: false)"},
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "browser_evaluate",
        "description": "Evaluate JavaScript expression in the browser page context",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {"type": "STRING", "description": "JavaScript expression to evaluate"},
            },
            "required": ["expression"],
        },
    },
]

BROWSER_TOOLS = {
    "browser_navigate": browser_navigate,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_evaluate": browser_evaluate,
}
