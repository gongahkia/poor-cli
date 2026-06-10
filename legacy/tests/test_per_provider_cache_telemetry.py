"""SBP1: per-provider cache telemetry (anthropic vs openai breakdown)."""
from __future__ import annotations
from typing import Any, Dict

import pytest


class _FakeProvider:
    def __init__(self, name: str) -> None: self.name = name


class _StubCore:
    """Minimal stand-in exposing just the attributes _track_cost touches."""
    def __init__(self, provider_name: str = "anthropic") -> None:
        self.provider = _FakeProvider(provider_name)
        self._session_total_input_tokens = 0
        self._session_total_output_tokens = 0
        self._session_total_cost_usd = 0.0
        self._session_cache_creation_input_tokens = 0
        self._session_cache_read_input_tokens = 0
        self._session_provider_cache_hits = 0
        self._session_provider_cache_misses = 0
        self._session_estimated_cache_savings_usd = 0.0
        self._session_provider_cache_stats: Dict[str, Dict[str, Any]] = {}
        self._task_input_tokens = 0
        self._task_output_tokens = 0
        self._task_cost_usd = 0.0
        self._task_cache_creation_input_tokens = 0
        self._task_cache_read_input_tokens = 0

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        # flat $0.001 per 1k input, $0.003 per 1k output
        return input_tokens / 1000 * 0.001 + output_tokens / 1000 * 0.003


def _track_cost(core: _StubCore, *args, **kwargs) -> float:
    from poor_cli.core_turn_lifecycle import TurnLifecycle as _TL
    # stub needs _resolve_current_provider_name since _track_cost calls it
    if not hasattr(core, "_resolve_current_provider_name"):
        core._resolve_current_provider_name = _TL._resolve_current_provider_name.__get__(core, _StubCore)
    bound = _TL._track_cost.__get__(core, _StubCore)
    return bound(*args, **kwargs)


def _resolve_provider(core: _StubCore) -> str | None:
    from poor_cli.core_turn_lifecycle import TurnLifecycle as _TL
    bound = _TL._resolve_current_provider_name.__get__(core, _StubCore)
    return bound()


def _build_breakdown(core: _StubCore) -> Dict[str, Any]:
    from poor_cli.core_turn_lifecycle import TurnLifecycle as _TL
    bound = _TL._build_provider_cache_breakdown.__get__(core, _StubCore)
    return bound()


def test_resolve_provider_from_provider_name() -> None:
    core = _StubCore(provider_name="Anthropic")
    assert _resolve_provider(core) == "anthropic"


def test_single_provider_hit_and_miss_aggregation() -> None:
    core = _StubCore(provider_name="anthropic")
    # first call: cache miss (cache_write + input tokens, no read)
    _track_cost(core, 1000, 500, cache_creation_input_tokens=200, cache_read_input_tokens=0)
    # second call: cache hit (read tokens present)
    _track_cost(core, 100, 300, cache_creation_input_tokens=0, cache_read_input_tokens=800)
    breakdown = _build_breakdown(core)
    anth = breakdown["anthropic"]
    assert anth["hits"] == 1
    assert anth["misses"] == 1
    assert anth["hit_rate_pct"] == 50.0
    assert anth["read_tokens"] == 800
    assert anth["write_tokens"] == 200


def test_mixed_provider_breakdown_isolates_stats() -> None:
    core = _StubCore(provider_name="anthropic")
    _track_cost(core, 500, 200, cache_read_input_tokens=400)
    _track_cost(core, 500, 200, cache_read_input_tokens=400)
    # switch provider
    core.provider = _FakeProvider("openai")
    _track_cost(core, 800, 300, cache_read_input_tokens=0, cache_creation_input_tokens=100)
    breakdown = _build_breakdown(core)
    assert breakdown["anthropic"]["hits"] == 2
    assert breakdown["anthropic"]["misses"] == 0
    assert breakdown["openai"]["hits"] == 0
    assert breakdown["openai"]["misses"] == 1
    assert breakdown["openai"]["write_tokens"] == 100


def test_explicit_provider_kwarg_overrides_active_provider() -> None:
    core = _StubCore(provider_name="anthropic")
    _track_cost(core, 100, 50, cache_read_input_tokens=10, provider="gemini")
    breakdown = _build_breakdown(core)
    assert "gemini" in breakdown
    assert "anthropic" not in breakdown


def test_no_call_paths_do_not_inflate_miss_count() -> None:
    core = _StubCore(provider_name="anthropic")
    # degenerate call: 0 input, 0 output, 0 cache — should NOT register a miss
    _track_cost(core, 0, 0, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    breakdown = _build_breakdown(core)
    if "anthropic" in breakdown:
        assert breakdown["anthropic"]["misses"] == 0
        assert breakdown["anthropic"]["hits"] == 0
