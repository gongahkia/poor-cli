"""Tests for poor_cli.api_key_validator live probe dispatch."""
from __future__ import annotations
import io
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from poor_cli import api_key_validator as V


def test_empty_key_returns_invalid_not_crash():
    for provider in ("anthropic", "openai", "gemini", "openrouter"):
        r = V.validate(provider, "")
        assert r.status == V.INVALID
        assert r.provider == provider or (provider == "claude" and r.provider == "anthropic")


def test_unknown_provider_returns_unknown():
    r = V.validate("ollama", "whatever")
    assert r.status == V.UNKNOWN


def test_claude_alias_routes_to_anthropic():
    r = V.validate("claude", "")
    assert r.provider == "anthropic"


def _fake_response(status=200, body=b""):
    class _Resp:
        def __init__(self): self.status = status
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1): return body
    return _Resp()


def test_anthropic_200_is_valid():
    with patch("poor_cli.api_key_validator.urlopen", return_value=_fake_response(200, b'{"data":[]}')):
        r = V.validate_anthropic("sk-ant-test")
    assert r.status == V.VALID


def test_anthropic_401_is_invalid():
    err = HTTPError("url", 401, "Unauthorized", {}, io.BytesIO(b'{"error":"invalid key"}'))
    with patch("poor_cli.api_key_validator.urlopen", side_effect=err):
        r = V.validate_anthropic("sk-ant-bad")
    assert r.status == V.INVALID
    assert "401" in r.reason


def test_extract_message_from_openai_shape():
    body = '{"error": {"message": "Incorrect API key provided: sk-proj-xxxx", "type": "invalid_request_error"}}'
    msg = V._extract_message(body)
    assert msg == "Incorrect API key provided: sk-proj-xxxx"


def test_extract_message_from_anthropic_string_shape():
    body = '{"error": "invalid x-api-key"}'
    assert V._extract_message(body) == "invalid x-api-key"


def test_extract_message_from_top_level_message_field():
    body = '{"message": "quota exceeded"}'
    assert V._extract_message(body) == "quota exceeded"


def test_extract_message_handles_plain_text_body():
    body = "Unauthorized"
    assert V._extract_message(body) == "Unauthorized"


def test_extract_message_handles_empty_body():
    assert V._extract_message("") == ""
    assert V._extract_message(None) == ""  # type: ignore[arg-type]


def test_reason_prepends_http_code():
    body = '{"error": {"message": "bad key"}}'
    assert V._reason(401, body) == "HTTP 401: bad key"


def test_reason_network_error_no_body():
    assert V._reason(0, "") == "network error"


def test_openai_401_reason_contains_clean_message():
    raw = b'{"error": {"message": "Incorrect API key provided: sk-proj-yyyy", "type": "invalid_request_error"}}'
    err = HTTPError("url", 401, "Unauthorized", {}, io.BytesIO(raw))
    with patch("poor_cli.api_key_validator.urlopen", side_effect=err):
        r = V.validate_openai("sk-proj-yyyy")
    assert r.status == V.INVALID
    assert "HTTP 401" in r.reason
    assert "Incorrect API key provided" in r.reason
    # no raw JSON braces leaking through
    assert "{" not in r.reason


def test_anthropic_network_error_is_unknown():
    from urllib.error import URLError
    with patch("poor_cli.api_key_validator.urlopen", side_effect=URLError("unreachable")):
        r = V.validate_anthropic("sk-ant-test")
    assert r.status == V.UNKNOWN


def test_openai_403_is_invalid():
    err = HTTPError("url", 403, "Forbidden", {}, io.BytesIO(b'quota exceeded'))
    with patch("poor_cli.api_key_validator.urlopen", side_effect=err):
        r = V.validate_openai("sk-test")
    assert r.status == V.INVALID


def test_gemini_400_is_invalid():
    # gemini returns 400 for bad API keys, unlike the others
    err = HTTPError("url", 400, "Bad Request", {}, io.BytesIO(b'API_KEY_INVALID'))
    with patch("poor_cli.api_key_validator.urlopen", side_effect=err):
        r = V.validate_gemini("AIza-bad")
    assert r.status == V.INVALID


def test_openrouter_200_is_valid():
    with patch("poor_cli.api_key_validator.urlopen", return_value=_fake_response(200, b'{"data":{}}')):
        r = V.validate_openrouter("sk-or-test")
    assert r.status == V.VALID


def test_to_dict_shape():
    r = V.KeyValidityResult(provider="anthropic", status=V.VALID)
    d = r.to_dict()
    assert d == {"provider": "anthropic", "status": "valid", "reason": ""}
