"""Unit tests for poor_cli.token_counter — PRD 001."""

from __future__ import annotations

import threading
from typing import Optional

import pytest

from poor_cli.token_counter import (
    HEURISTIC_CHARS_PER_TOKEN,
    TokenCount,
    TokenCounter,
    _lookup_ratio,
    count_text,
    get_token_counter,
    set_token_counter,
)


@pytest.fixture
def fresh_counter():
    tc = TokenCounter()
    set_token_counter(tc)
    yield tc
    set_token_counter(None)


# ── heuristic fallback ──────────────────────────────────────────────────


def test_heuristic_fallback_uses_calibration_table(fresh_counter):
    text = "x" * 35  # 35 chars
    # anthropic -> 3.5 chars/token => 10 tokens
    result = fresh_counter.count(text, provider="anthropic", model="claude-3")
    assert result.source == "heuristic"
    assert result.provider == "anthropic"
    assert result.count == int(35 / 3.5)


def test_heuristic_fallback_for_model_specific_override(fresh_counter):
    # gpt-5.1 has a model-specific override (3.7)
    fresh_counter._tiktoken_disabled = True
    text = "x" * 370
    result = fresh_counter.count(text, provider="openai", model="gpt-5.1")
    assert result.count == int(370 / 3.7)


def test_lookup_ratio_falls_back_through_layers():
    # exact (provider, model)
    assert _lookup_ratio("openai", "gpt-5.1") == HEURISTIC_CHARS_PER_TOKEN[("openai", "gpt-5.1")]
    # provider wildcard
    assert _lookup_ratio("anthropic", "claude-unknown") == HEURISTIC_CHARS_PER_TOKEN[("anthropic", "*")]
    # unknown provider -> last resort
    assert _lookup_ratio("unknownprovider", "foo") == HEURISTIC_CHARS_PER_TOKEN[(None, "*")]
    # no provider
    assert _lookup_ratio(None, None) == HEURISTIC_CHARS_PER_TOKEN[(None, "*")]


def test_empty_text_returns_zero(fresh_counter):
    assert fresh_counter.count("").count == 0
    assert fresh_counter.count("", provider="anthropic").count == 0


# ── native backend path ─────────────────────────────────────────────────


class _StubBackend:
    def __init__(self, fixed: int = 42) -> None:
        self.fixed = fixed
        self.calls: list[tuple[str, Optional[str]]] = []

    def count(self, text: str, *, model: Optional[str] = None) -> int:
        self.calls.append((text, model))
        return self.fixed


def test_native_backend_preferred_over_heuristic(fresh_counter):
    stub = _StubBackend(fixed=99)
    fresh_counter.register_backend("anthropic", stub)
    result = fresh_counter.count("hello world", provider="anthropic", model="claude-x")
    assert result.source == "native"
    assert result.count == 99
    assert stub.calls == [("hello world", "claude-x")]


def test_native_backend_failure_falls_back_to_heuristic(fresh_counter):
    class Boom:
        def count(self, text: str, *, model: Optional[str] = None) -> int:
            raise RuntimeError("sdk offline")

    fresh_counter.register_backend("anthropic", Boom())
    result = fresh_counter.count("x" * 35, provider="anthropic")
    assert result.source == "heuristic"
    assert result.count > 0


# ── unknown provider ────────────────────────────────────────────────────


def test_unknown_provider_falls_back_cleanly(fresh_counter):
    result = fresh_counter.count("hi there", provider="someprovider")
    assert result.source == "heuristic"
    assert result.count >= 1


def test_missing_provider_still_counts(fresh_counter):
    result = fresh_counter.count("x" * 38)
    assert result.source == "heuristic"
    assert result.count == int(38 / HEURISTIC_CHARS_PER_TOKEN[(None, "*")])


# ── thread safety ───────────────────────────────────────────────────────


def test_counter_is_thread_safe(fresh_counter):
    stub = _StubBackend(fixed=7)
    fresh_counter.register_backend("anthropic", stub)

    results: list[TokenCount] = []
    errors: list[BaseException] = []

    def worker():
        try:
            for _ in range(50):
                r = fresh_counter.count("text", provider="anthropic")
                results.append(r)
        except BaseException as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 200
    assert all(r.count == 7 for r in results)


# ── count_messages ──────────────────────────────────────────────────────


def test_count_messages_sums_across_messages_within_slack(fresh_counter):
    msgs = [
        {"role": "user", "content": "x" * 35},
        {"role": "assistant", "content": "y" * 70},
        {"role": "tool", "content": [{"text": "z" * 35}]},
    ]
    combined = fresh_counter.count("x" * 35 + "\n" + "y" * 70 + "\n" + "z" * 35,
                                   provider="anthropic").count
    summed = fresh_counter.count_messages(msgs, provider="anthropic").count
    # Summing parts is within a small slack of summing joined text (heuristic is linear in len)
    assert abs(summed - combined) <= 3


def test_count_messages_handles_empty_list(fresh_counter):
    assert fresh_counter.count_messages([], provider="anthropic").count == 0


# ── reserve / budget ────────────────────────────────────────────────────


def test_reserve_allocates_proportionally(fresh_counter):
    parts = {
        "system": "s" * 100,
        "history": "h" * 400,
        "tools": "t" * 500,
    }
    allocation = fresh_counter.reserve(
        budget=100,
        for_parts=parts,
        provider="anthropic",
    )
    assert set(allocation) == {"system", "history", "tools"}
    assert sum(allocation.values()) <= 100
    # largest part gets the largest allocation
    assert allocation["tools"] >= allocation["history"] >= allocation["system"]


def test_reserve_returns_counts_when_within_budget(fresh_counter):
    parts = {"a": "x" * 35, "b": "y" * 70}
    total = fresh_counter.count(parts["a"], provider="anthropic").count + \
            fresh_counter.count(parts["b"], provider="anthropic").count
    allocation = fresh_counter.reserve(budget=10_000, for_parts=parts, provider="anthropic")
    assert sum(allocation.values()) == total


def test_reserve_with_zero_budget(fresh_counter):
    parts = {"a": "hello", "b": "world"}
    allocation = fresh_counter.reserve(budget=0, for_parts=parts)
    assert allocation == {"a": 0, "b": 0}


# ── singleton plumbing ──────────────────────────────────────────────────


def test_get_token_counter_is_singleton():
    set_token_counter(None)
    a = get_token_counter()
    b = get_token_counter()
    assert a is b


def test_set_token_counter_replaces_instance():
    custom = TokenCounter()
    set_token_counter(custom)
    assert get_token_counter() is custom
    set_token_counter(None)


def test_count_text_shortcut(fresh_counter):
    n = count_text("x" * 35, provider="anthropic")
    assert isinstance(n, int)
    assert n == fresh_counter.count("x" * 35, provider="anthropic").count


# ── async variant ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_acount_matches_sync(fresh_counter):
    text = "x" * 35
    sync = fresh_counter.count(text, provider="anthropic")
    a = await fresh_counter.acount(text, provider="anthropic")
    assert a.count == sync.count
    assert a.source == sync.source
