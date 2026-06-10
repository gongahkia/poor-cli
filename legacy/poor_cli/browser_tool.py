"""Browser automation tools using Playwright for headless browsing."""

from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import re
from typing import Any, Awaitable, Callable, Dict, Optional
from urllib.parse import urlparse

from .exceptions import setup_logger

logger = setup_logger(__name__)

_browser_context: Dict[str, Any] = {"browser": None, "page": None, "playwright": None}
_browser_permission_callback: Optional[Callable[..., Awaitable[Any]]] = None

DEFAULT_OUTPUT_LIMIT = 64_000
DEFAULT_TIMEOUT_MS = 5_000
_JS_MAX_EXPRESSION_LENGTH = 128_000


class BrowserEvalBlocked(RuntimeError):
    """blocked browser_evaluate policy violation."""


class BrowserEvalTimeout(TimeoutError):
    """browser_evaluate timeout."""


class BrowserEvalSerializationError(RuntimeError):
    """browser_evaluate returned non-JSON-serializable data."""


def _log_browser_event(
    operation: str,
    target: str = "",
    details: dict = None,
    *,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """log browser operation to audit trail."""
    try:
        from .audit_log import get_audit_logger, AuditEventType, AuditSeverity
        get_audit_logger().log_event(
            AuditEventType.TOOL_EXECUTION,
            operation=f"browser:{operation}",
            target=target,
            details=details,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            success=success,
            error_message=error_message,
        )
    except Exception:
        pass


def set_browser_permission_callback(callback: Optional[Callable[..., Awaitable[Any]]]) -> None:
    global _browser_permission_callback
    _browser_permission_callback = callback


async def _ensure_browser() -> Any:
    """lazy-init headless chromium, return active page."""
    if _browser_context["page"] is not None:
        try: # crash recovery: verify page still alive
            await _browser_context["page"].title()
            return _browser_context["page"]
        except Exception:
            logger.warning("browser page dead, relaunching")
            await shutdown_browser()
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed. Run: pip install playwright && playwright install chromium")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    page.set_default_timeout(30000)
    _browser_context.update(playwright=pw, browser=browser, page=page)
    logger.info("launched headless chromium")
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
    _log_browser_event("navigate", url, {"wait_until": wait_until})
    page = await _ensure_browser()
    response = await page.goto(url, wait_until=wait_until, timeout=30000)
    status = response.status if response else "unknown"
    title = await page.title()
    text = await page.inner_text("body")
    text = text[:3000].strip() if text else ""
    return f"[{status}] {title}\n\n{text}"


async def browser_screenshot(selector: Optional[str] = None, full_page: bool = False) -> str:
    """Take a screenshot, return as base64 PNG."""
    _log_browser_event("screenshot", selector or "full_page", {"full_page": full_page})
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
    _log_browser_event("click", selector)
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
    _log_browser_event("type", selector, {"submit": submit})
    page = await _ensure_browser()
    try:
        await page.fill(selector, text, timeout=10000)
        if submit:
            await page.press(selector, "Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        return f"typed into '{selector}'"
    except Exception as e:
        return f"error typing into '{selector}': {e}"


_JS_DENYLIST_PATTERNS = (
    r"localStorage\s*\.\s*clear",
    r"sessionStorage\s*\.\s*clear",
    r"document\s*\.\s*cookie\s*=",
    r"navigator\s*\.\s*sendBeacon",
    r"window\s*\.\s*location\s*=",
    r"indexedDB\s*\.\s*deleteDatabase",
)
_JS_DENYLIST_RE = tuple((p, re.compile(p, re.IGNORECASE)) for p in _JS_DENYLIST_PATTERNS)
_FETCH_LITERAL_RE = re.compile(r"\bfetch\s*\(\s*(?P<q>['\"`])(?P<url>.*?)(?P=q)", re.IGNORECASE | re.DOTALL)


def _command_hash(expression: str) -> str:
    return hashlib.sha256(expression.encode("utf-8", errors="replace")).hexdigest()


def _origin_for_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_fetch_origins(origins: Optional[list[str]]) -> list[str]:
    normalized: list[str] = []
    for origin in origins or []:
        value = str(origin or "").rstrip("/")
        parsed_origin = _origin_for_url(value)
        if parsed_origin and parsed_origin not in normalized:
            normalized.append(parsed_origin)
    return normalized


def _scan_dangerous_js(expression: str) -> list[str]:
    if len(expression) > _JS_MAX_EXPRESSION_LENGTH:
        return [f"expression length > {_JS_MAX_EXPRESSION_LENGTH}"]
    return [pattern for pattern, compiled in _JS_DENYLIST_RE if compiled.search(expression)]


def _scan_fetch_policy(expression: str, page_url: str, allowed_origins: list[str]) -> tuple[list[str], list[str], list[str]]:
    page_origin = _origin_for_url(page_url)
    blocked: list[str] = []
    warnings: list[str] = []
    external_origins: list[str] = []
    for match in _FETCH_LITERAL_RE.finditer(expression):
        raw_url = match.group("url")
        if "${" in raw_url:
            warnings.append("dynamic fetch URL could not be statically verified")
            continue
        target_origin = _origin_for_url(raw_url)
        if not target_origin:
            continue
        if target_origin == page_origin:
            continue
        if target_origin not in allowed_origins:
            blocked.append(f"third-party fetch:{target_origin}")
            continue
        if target_origin not in external_origins:
            external_origins.append(target_origin)
    if "fetch" in expression.lower() and not _FETCH_LITERAL_RE.search(expression):
        warnings.append("dynamic fetch call could not be statically verified")
    return blocked, warnings, external_origins


async def _authorize_browser_evaluate(
    expression: str,
    *,
    allow_dangerous: bool,
    matched_patterns: list[str],
    external_fetch_origins: list[str],
) -> None:
    if not allow_dangerous and not external_fetch_origins:
        return
    if _browser_permission_callback is None:
        raise BrowserEvalBlocked("permission callback required for browser_evaluate policy opt-in")
    decision = await _browser_permission_callback(
        "browser_evaluate",
        {
            "expression_hash": _command_hash(expression),
            "allow_dangerous": allow_dangerous,
            "matched_patterns": matched_patterns,
            "external_fetch_origins": external_fetch_origins,
        },
        {"kind": "browser_evaluate_policy_opt_in"},
    )
    allowed = bool(decision.get("allowed", False)) if isinstance(decision, dict) else bool(decision)
    if not allowed:
        raise BrowserEvalBlocked("permission denied for browser_evaluate policy opt-in")


def _wrap_browser_expression(expression: str) -> str:
    return f"""async (policy) => {{
  const allowedOrigins = new Set(policy.allowedFetchOrigins || []);
  const originalFetch = window.fetch;
  window.fetch = function(input, init) {{
    const rawUrl = typeof input === "string" ? input : input && input.url;
    const target = new URL(String(rawUrl || ""), window.location.href);
    if (target.origin !== window.location.origin && !allowedOrigins.has(target.origin)) {{
      throw new Error("BrowserEvalBlocked: third-party fetch " + target.origin);
    }}
    return originalFetch.apply(this, arguments);
  }};
  const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error("BrowserEvalTimeout")), policy.timeoutMs));
  const run = async () => {{
    const value = ({expression});
    const resolved = typeof value === "function" ? await value() : await value;
    let serialized;
    try {{
      serialized = JSON.stringify(resolved);
    }} catch (error) {{
      throw new Error("BrowserEvalSerializationError: " + error.message);
    }}
    if (typeof serialized !== "string") {{
      throw new Error("BrowserEvalSerializationError");
    }}
    return serialized;
  }};
  try {{
    return await Promise.race([run(), timeout]);
  }} finally {{
    window.fetch = originalFetch;
  }}
}}"""


def _format_serialized_result(serialized: str, max_output: int) -> str:
    try:
        value = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise BrowserEvalSerializationError(str(error)) from error
    output = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(output) <= max_output:
        return output
    omitted = len(output) - max_output
    return output[:max_output] + f"...[truncated {omitted} chars]"


async def browser_evaluate(
    expression: str,
    max_output: int = DEFAULT_OUTPUT_LIMIT,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    allow_dangerous: bool = False,
    allowed_fetch_origins: Optional[list[str]] = None,
) -> str:
    """Evaluate JavaScript in the page context with policy checks."""
    command_hash = _command_hash(expression)
    outcome = "error"
    details: Dict[str, Any] = {
        "commandHash": command_hash,
        "maxOutput": max_output,
        "timeoutMs": timeout_ms,
        "allowDangerous": allow_dangerous,
    }
    try:
        max_output = max(1, int(max_output or DEFAULT_OUTPUT_LIMIT))
        timeout_ms = max(1, int(timeout_ms or DEFAULT_TIMEOUT_MS))
        matched_patterns = _scan_dangerous_js(expression)
        details["matchedPatterns"] = matched_patterns
        if matched_patterns and not allow_dangerous:
            raise BrowserEvalBlocked(", ".join(matched_patterns))
        if allow_dangerous:
            await _authorize_browser_evaluate(
                expression,
                allow_dangerous=True,
                matched_patterns=matched_patterns,
                external_fetch_origins=[],
            )
        page = await _ensure_browser()
        allowed_origins = _normalize_fetch_origins(allowed_fetch_origins)
        fetch_blocks, warnings, external_fetch_origins = _scan_fetch_policy(expression, page.url, allowed_origins)
        details.update({
            "warnings": warnings,
            "externalFetchOrigins": external_fetch_origins,
            "allowedFetchOrigins": allowed_origins,
        })
        if fetch_blocks:
            raise BrowserEvalBlocked(", ".join(fetch_blocks))
        if allowed_origins:
            await _authorize_browser_evaluate(
                expression,
                allow_dangerous=False,
                matched_patterns=matched_patterns,
                external_fetch_origins=external_fetch_origins or allowed_origins,
            )
        wrapper = _wrap_browser_expression(expression)
        try:
            serialized = await asyncio.wait_for(
                page.evaluate(wrapper, {"timeoutMs": timeout_ms, "allowedFetchOrigins": allowed_origins}),
                timeout=(timeout_ms / 1000) + 1,
            )
        except asyncio.TimeoutError as error:
            raise BrowserEvalTimeout(f"timed out after {timeout_ms}ms") from error
        except Exception as error:
            message = str(error)
            if "BrowserEvalTimeout" in message:
                raise BrowserEvalTimeout(f"timed out after {timeout_ms}ms") from error
            if "BrowserEvalBlocked" in message:
                raise BrowserEvalBlocked(message) from error
            if "BrowserEvalSerializationError" in message or "Do not know how to serialize" in message:
                raise BrowserEvalSerializationError(message) from error
            raise
        output = _format_serialized_result(serialized, max_output)
        outcome = "success"
        details["outputChars"] = len(output)
        return output
    except (BrowserEvalBlocked, BrowserEvalTimeout, BrowserEvalSerializationError) as error:
        outcome = error.__class__.__name__
        details["error"] = str(error)
        raise
    except Exception as error:
        details["error"] = str(error)
        raise
    finally:
        details["outcome"] = outcome
        _log_browser_event(
            "evaluate",
            command_hash,
            details,
            success=outcome == "success",
            error_message=None if outcome == "success" else details.get("error", outcome),
        )


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
                "max_output": {"type": "INTEGER", "description": "Maximum returned characters (default 64000)"},
                "timeout_ms": {"type": "INTEGER", "description": "Execution timeout in milliseconds (default 5000)"},
                "allow_dangerous": {"type": "BOOLEAN", "description": "Request permission-gated bypass for denylisted APIs"},
                "allowed_fetch_origins": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Permission-gated third-party fetch origin allowlist",
                },
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
