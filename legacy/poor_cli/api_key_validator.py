"""Lightweight remote API-key validity probe.

Invoked at server initialize time to detect keys that are *configured* but
*no longer valid* (revoked, rotated, rate-exhausted, billing lapse). The
regular startup path only checks that an env var is non-empty — this
module actually hits the provider's cheapest authed endpoint and parses
the response code.

Design:
- Each provider has a tiny synchronous probe that returns a
  ``KeyValidityResult`` (valid / invalid / unknown + reason).
- 2 second per-provider timeout; degrades to ``unknown`` rather than
  blocking startup if the network is slow.
- Only cloud providers with explicit auth are probed: Anthropic, OpenAI,
  Gemini, OpenRouter. Local providers (ollama, hf_local, vllm, etc.)
  return ``unknown`` — not a concept for them.
- CLI and JSON-RPC clients can surface this as an actionable setup error.

The probes use plain stdlib urllib to avoid an async dependency during
startup and to keep the per-provider probe code under ~10 lines each.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROBE_TIMEOUT_SEC = 2.0

VALID = "valid"
INVALID = "invalid"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class KeyValidityResult:
    provider: str
    status: str  # "valid" | "invalid" | "unknown"
    reason: str = ""

    def to_dict(self) -> dict:
        return {"provider": self.provider, "status": self.status, "reason": self.reason}


def _probe(url: str, headers: Optional[dict] = None) -> tuple[int, str]:
    """Return (http_status, body_snippet). body trimmed to 200 chars."""
    req = Request(url, headers=headers or {})
    try:
        with urlopen(req, timeout=PROBE_TIMEOUT_SEC) as resp:
            body = resp.read(1024)
            return resp.status, body.decode("utf-8", errors="replace")[:200]
    except HTTPError as exc:
        try:
            body = exc.read(1024).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return exc.code, body
    except (URLError, OSError, TimeoutError) as exc:
        return 0, str(exc)[:200]


def _extract_message(body: str) -> str:
    """Extract the human-readable error message from a provider JSON body.

    Providers wrap errors differently. Walks known shapes in order:
    - Anthropic/OpenAI:  ``{"error": {"message": "..."}}``
    - Gemini:            ``{"error": {"message": "..."}}`` (same)
    - OpenRouter:        ``{"error": {"message": "..."}}`` or top-level ``"message"``
    - Fallback:          first 80 chars of body.
    Always returns a single-line string.
    """
    body = (body or "").strip()
    if not body:
        return ""
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return body.replace("\n", " ")[:120]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg:
                return msg.replace("\n", " ")[:200]
        elif isinstance(err, str) and err:
            return err.replace("\n", " ")[:200]
        msg = data.get("message")
        if isinstance(msg, str) and msg:
            return msg.replace("\n", " ")[:200]
    return body.replace("\n", " ")[:120]


def _reason(code: int, body: str) -> str:
    message = _extract_message(body)
    prefix = f"HTTP {code}" if code else "network error"
    if message:
        return f"{prefix}: {message}"
    return prefix


def validate_anthropic(api_key: str) -> KeyValidityResult:
    if not api_key:
        return KeyValidityResult("anthropic", INVALID, "no key")
    code, body = _probe(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
    )
    if code == 200:
        return KeyValidityResult("anthropic", VALID)
    if code in (401, 403):
        return KeyValidityResult("anthropic", INVALID, _reason(code, body))
    return KeyValidityResult("anthropic", UNKNOWN, _reason(code, body) if code else "network unreachable")


def validate_openai(api_key: str) -> KeyValidityResult:
    if not api_key:
        return KeyValidityResult("openai", INVALID, "no key")
    code, body = _probe(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if code == 200:
        return KeyValidityResult("openai", VALID)
    if code in (401, 403):
        return KeyValidityResult("openai", INVALID, _reason(code, body))
    return KeyValidityResult("openai", UNKNOWN, _reason(code, body) if code else "network unreachable")


def validate_gemini(api_key: str) -> KeyValidityResult:
    if not api_key:
        return KeyValidityResult("gemini", INVALID, "no key")
    code, body = _probe(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
    )
    if code == 200:
        return KeyValidityResult("gemini", VALID)
    if code in (400, 401, 403):
        return KeyValidityResult("gemini", INVALID, _reason(code, body))
    return KeyValidityResult("gemini", UNKNOWN, _reason(code, body) if code else "network unreachable")


def validate_openrouter(api_key: str) -> KeyValidityResult:
    if not api_key:
        return KeyValidityResult("openrouter", INVALID, "no key")
    code, body = _probe(
        "https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if code == 200:
        return KeyValidityResult("openrouter", VALID)
    if code in (401, 403):
        return KeyValidityResult("openrouter", INVALID, _reason(code, body))
    return KeyValidityResult("openrouter", UNKNOWN, _reason(code, body) if code else "network unreachable")


_VALIDATORS = {
    "anthropic": validate_anthropic,
    "claude": validate_anthropic,
    "openai": validate_openai,
    "gemini": validate_gemini,
    "openrouter": validate_openrouter,
}


def validate(provider: str, api_key: str) -> KeyValidityResult:
    """Validate ``api_key`` for ``provider``. Returns UNKNOWN for local
    or unsupported providers.
    """
    p = (provider or "").strip().lower()
    fn = _VALIDATORS.get(p)
    if fn is None:
        return KeyValidityResult(p or "unknown", UNKNOWN, "not a cloud provider")
    try:
        return fn(api_key)
    except Exception as exc:  # pragma: no cover — defensive
        return KeyValidityResult(p, UNKNOWN, f"probe crashed: {exc}")
