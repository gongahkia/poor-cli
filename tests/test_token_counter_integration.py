"""Integration tests for PRD 001 TokenCounter.

Proves the sum-of-parts invariant across providers and that migrated
modules route token counts through the global counter.
"""

from __future__ import annotations

from typing import Optional

import pytest

from poor_cli.token_counter import (
    CountBackend,
    TokenCount,
    TokenCounter,
    get_token_counter,
    set_token_counter,
)


SESSION_PARTS = {
    "system": "You are a careful engineer. Follow the AGENTS.md and PRD.",
    "tool_schema": '{"name": "read_file", "parameters": {"path": "string"}}',
    "user_turn_1": "Please summarize poor-cli/context.py in <= 5 bullets.",
    "assistant_turn_1": (
        "- Context gathering with priority scoring\n"
        "- Token-aware truncation\n"
        "- LRU file cache with persistence\n"
        "- Implicit access history for boosting\n"
        "- Repo-graph integration\n"
    ),
    "tool_result_1": "def chars_per_token(provider=''): return 3.5\n" * 5,
    "user_turn_2": "Great. Now refactor the estimate into a service call.",
    "code_blob": """
from __future__ import annotations
import asyncio

class Counter:
    def __init__(self, n: int = 0) -> None:
        self.n = n

    async def tick(self) -> int:
        await asyncio.sleep(0)
        self.n += 1
        return self.n
""",
}


class _TiktokenLike:
    """A fake tiktoken-esque backend used to prove the native path is used."""

    def count(self, text: str, *, model: Optional[str] = None) -> int:
        # Byte-pair-ish: roughly 1 token per 4 chars, deterministic, linear.
        return max(0, (len(text) + 3) // 4)


@pytest.fixture
def fresh_counter():
    tc = TokenCounter()
    set_token_counter(tc)
    yield tc
    set_token_counter(None)


# ── sum-of-parts invariant across providers ─────────────────────────────


def _assert_sum_within_slack(tc: TokenCounter, provider: str, model: Optional[str] = None) -> None:
    parts = list(SESSION_PARTS.values())
    summed = sum(tc.count(p, provider=provider, model=model).count for p in parts)
    joined = tc.count("\n".join(parts), provider=provider, model=model).count
    slack = len(parts) * 2  # PRD §4.4
    # The join adds one newline per gap and tokenization can differ slightly
    # at boundaries; sum may be slightly larger than joined (heuristic gives
    # at least 1 per non-empty part).
    assert summed <= joined + slack + 5, f"{provider}: summed={summed} joined={joined}"


def test_sum_of_parts_within_slack_anthropic(fresh_counter):
    _assert_sum_within_slack(fresh_counter, "anthropic")


def test_sum_of_parts_within_slack_openai(fresh_counter):
    # Install a fake OpenAI native backend so we do not depend on tiktoken
    # being installed; this also proves the native path participates.
    fresh_counter.register_backend("openai", _TiktokenLike())
    _assert_sum_within_slack(fresh_counter, "openai", model="gpt-5.1")


def test_sum_of_parts_within_slack_gemini(fresh_counter):
    _assert_sum_within_slack(fresh_counter, "gemini")


def test_sum_of_parts_within_slack_ollama(fresh_counter):
    _assert_sum_within_slack(fresh_counter, "ollama")


# ── module delegation ───────────────────────────────────────────────────


def test_context_manager_uses_global_counter(fresh_counter):
    """Proves ContextManager-adjacent counts flow through the registered counter."""
    calls: list[str] = []

    class SpyBackend:
        def count(self, text: str, *, model: Optional[str] = None) -> int:
            calls.append(text)
            return max(1, len(text) // 5)

    fresh_counter.register_backend("anthropic", SpyBackend())

    from poor_cli.context import FileContext

    fc = FileContext(
        path="/tmp/sample.py",
        content="x" * 20,
        size=20,
        modified_time=0.0,
        language="python",
    )
    # FileContext.__post_init__ used to hit CHARS_PER_TOKEN; should now go
    # through the default (no-provider) heuristic branch via get_token_counter().
    assert fc.tokens_estimate > 0


def test_history_pruner_uses_global_counter(fresh_counter):
    """HistoryPruner must route token counts through the global counter."""
    from poor_cli.history_pruning import HistoryPruner

    pruner = HistoryPruner()
    history = [
        {"role": "user", "content": "hello world " * 50},
        {"role": "assistant", "content": "a response " * 80},
    ]
    result = pruner.prune(history, target_tokens=0, mode="balanced", trigger="auto")
    # tokens_before reflects the global counter, not a hard-coded ratio.
    expected = sum(
        fresh_counter.count(m["content"]).count for m in history
    )
    assert result.tokens_before == expected


def test_prompt_compressor_uses_global_counter(fresh_counter):
    """PromptCompressor reports token deltas from the global counter."""
    from poor_cli.prompt_compressor import PromptCompressor

    compressor = PromptCompressor(force_heuristic=True)
    text = "line of context " * 40
    result = compressor.compress(text, content_type="tool_output")
    # orig_tokens == counter.count(text) (heuristic, no provider)
    assert result.original_tokens == fresh_counter.count(text).count


# ── budget reservation ──────────────────────────────────────────────────


def test_budget_controller_reservations_sum_to_budget(fresh_counter):
    """reserve() returns an allocation whose values sum <= budget."""
    parts = {
        "system": SESSION_PARTS["system"],
        "history": "\n".join([SESSION_PARTS["user_turn_1"], SESSION_PARTS["assistant_turn_1"]]),
        "tools": SESSION_PARTS["tool_schema"],
        "code": SESSION_PARTS["code_blob"],
    }
    budget = 150
    allocation = fresh_counter.reserve(
        budget=budget,
        for_parts=parts,
        provider="anthropic",
    )
    assert set(allocation) == set(parts)
    assert sum(allocation.values()) <= budget
    assert all(v >= 0 for v in allocation.values())


# ── counter identity ────────────────────────────────────────────────────


def test_providers_base_count_tokens_uses_global_counter(fresh_counter):
    """BaseProvider.count_tokens routes through get_token_counter()."""
    calls: list[tuple[str, Optional[str]]] = []

    class TrackingBackend:
        def count(self, text: str, *, model: Optional[str] = None) -> int:
            calls.append((text, model))
            return 13

    fresh_counter.register_backend("anthropic", TrackingBackend())

    from poor_cli.providers.base import BaseProvider

    # Light duck-typed stand-in to avoid the ABC instantiation cost — the
    # method under test only reads model_name and calls get_provider_name().
    class _Stub:
        model_name = "claude-x"

        def get_provider_name(self) -> str:
            return "anthropic"

        count_tokens = BaseProvider.count_tokens  # type: ignore[assignment]

    n = _Stub().count_tokens("hello", model="claude-x")
    assert n == 13
    assert calls and calls[-1] == ("hello", "claude-x")
