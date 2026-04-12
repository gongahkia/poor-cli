# PRD 013: Sandbox the `browser_evaluate` tool

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (2–3d)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/browser_tool.py`
- **New files it adds:**
  - `tests/test_browser_tool_sandbox.py`

## 1. Problem

`browser_evaluate()` executes arbitrary JS in page context with no sandboxing, no output size limits, and no denylist. LONGTERM-TODO L3 and LEARNING.md §2.3 both flag this. "Do it before someone files a CVE."

## 2. Current state

`poor_cli/browser_tool.py::browser_evaluate(js)` runs `page.evaluate(js)` in Playwright (or similar) directly.

## 3. Goal & non-goals

**Goal:** the tool has output size limits, execution timeouts, a denylist for dangerous APIs (`localStorage.clear`, `document.cookie` writes, `navigator.sendBeacon`, `fetch` to third-party origins), and a Content-Security-Policy-aware evaluation wrapper that returns serializable values only.

**Non-goals:**
- Do not implement a full JS sandbox (out of scope; use Playwright's built-in isolation).
- Do not block all `fetch` (needed for some legitimate scraping flows).

## 4. Design

### 4.1 Wrapper

```python
DEFAULT_OUTPUT_LIMIT = 64_000  # chars
DEFAULT_TIMEOUT_MS  = 5_000

DANGEROUS_PATTERNS = [
    r"localStorage\s*\.\s*clear",
    r"sessionStorage\s*\.\s*clear",
    r"document\s*\.\s*cookie\s*=",
    r"navigator\s*\.\s*sendBeacon",
    r"window\s*\.\s*location\s*=",
    r"indexedDB\s*\.\s*deleteDatabase",
]

class BrowserEvalBlocked(Exception): ...

def browser_evaluate(js: str, *, allow_dangerous: bool = False, timeout_ms: int = DEFAULT_TIMEOUT_MS, max_output: int = DEFAULT_OUTPUT_LIMIT) -> BrowserEvalResult:
    if not allow_dangerous:
        for pat in DANGEROUS_PATTERNS:
            if re.search(pat, js):
                raise BrowserEvalBlocked(pat)
    # wrap js in an IIFE with a Promise.race against timeout
    # serialize result, truncate to max_output
```

### 4.2 Permission escalation

`allow_dangerous=True` requires an explicit user confirmation via the permission callback.

## 5. Files to create / modify / delete

**Create**
- `tests/test_browser_tool_sandbox.py`

**Modify**
- `poor_cli/browser_tool.py` — wrap `evaluate`, add policy, add timeout, add output truncation.

## 6. Implementation plan

1. Add the regex denylist + timeout + output-limit wrapper.
2. Gate `allow_dangerous` behind the permission callback.
3. Tests: each dangerous pattern raises; innocent JS passes; long output truncates; timeout produces a clean error.
4. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_localstorage_clear_blocked`
- `test_cookie_write_blocked`
- `test_innocent_js_runs`
- `test_output_truncated_above_limit`
- `test_timeout_produces_clean_error`
- `test_allow_dangerous_requires_permission`

**Done criterion**
- [ ] All dangerous patterns blocked by default.
- [ ] Timeout enforced.
- [ ] Output bounded.
- [ ] Permission path tested.

## 8. Rollback / risk

Low. Blocks may produce false positives on legitimate JS — `allow_dangerous` escape hatch exists.

## 9. Out-of-scope & boundary

- 🚫 Do not replace Playwright.
- 🚫 Do not add network proxying.

## 10. Related PRDs & references

- LONGTERM-TODO L3.
- LEARNING.md §2.3.
