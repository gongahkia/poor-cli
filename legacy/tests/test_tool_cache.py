"""Tests for poor_cli.tool_cache + dispatcher cache integration (E.1a)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import TextBlock, ToolResult
from poor_cli.tool_cache import ToolCache, _hash_args
from poor_cli.tool_dispatcher import dispatch_one
from poor_cli.tools import _registry


def _ctx(cache=None):
    return SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_cache=cache,
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _snapshot_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


# ──────────────── _hash_args canonicalization ────────────────


def test_hash_canonicalizes_key_order():
    assert _hash_args({"a": 1, "b": 2}) == _hash_args({"b": 2, "a": 1})


def test_hash_differs_for_different_values():
    assert _hash_args({"a": 1}) != _hash_args({"a": 2})


def test_hash_handles_nested_structures():
    a = {"list": [1, 2, {"x": "y"}], "n": 3}
    b = {"n": 3, "list": [1, 2, {"x": "y"}]}
    assert _hash_args(a) == _hash_args(b)


# ──────────────── ToolCache unit tests ────────────────


def test_cache_get_on_empty_returns_none():
    c = ToolCache()
    assert c.get("t.x", {}, ttl_s=60) is None


def test_cache_put_then_get_returns_result():
    c = ToolCache()
    res = ToolResult.text("cached")
    c.put("t.x", {"a": 1}, res)
    hit = c.get("t.x", {"a": 1}, ttl_s=60)
    assert hit is res


def test_cache_ttl_expiry():
    c = ToolCache()
    res = ToolResult.text("cached")
    c.put("t.x", {}, res)
    # Mutate created_at far into the past to simulate stale entry
    key = list(c._entries.keys())[0]
    c._entries[key].created_at -= 1000
    assert c.get("t.x", {}, ttl_s=60) is None


def test_cache_invalidate_tool_drops_matching_entries():
    c = ToolCache()
    c.put("t.a", {"x": 1}, ToolResult.text("a1"))
    c.put("t.a", {"x": 2}, ToolResult.text("a2"))
    c.put("t.b", {"x": 1}, ToolResult.text("b1"))
    dropped = c.invalidate_tool("t.a")
    assert dropped == 2
    assert c.get("t.a", {"x": 1}, ttl_s=60) is None
    assert c.get("t.b", {"x": 1}, ttl_s=60) is not None


def test_cache_invalidate_many():
    c = ToolCache()
    for name in ("t.a", "t.b", "t.c"):
        c.put(name, {}, ToolResult.text(name))
    assert c.invalidate_many(["t.a", "t.c"]) == 2
    assert c.get("t.a", {}, ttl_s=60) is None
    assert c.get("t.b", {}, ttl_s=60) is not None


def test_cache_lru_eviction():
    c = ToolCache(max_entries=10)  # min floor 8 but we picked 10
    for i in range(15):
        c.put("t.x", {"i": i}, ToolResult.text(str(i)))
    # Only the most recent 10 entries should survive
    assert c.stats()["entries"] == 10


def test_cache_stats_track_hits_and_misses():
    c = ToolCache()
    c.put("t.x", {}, ToolResult.text("ok"))
    c.get("t.x", {}, ttl_s=60)
    c.get("t.x", {}, ttl_s=60)
    c.get("t.y", {}, ttl_s=60)  # miss
    stats = c.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1


# ──────────────── dispatcher integration ────────────────


def _register(name, handler, **kwargs):
    # Schema intentionally permissive — these tests vary args to trigger cache
    # miss/hit behavior, so we don't want T1 validation to reject {q: 1} etc.
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "additionalProperties": True},
        handler=handler,
        **kwargs,
    )


def test_exclusive_and_cacheable_downgrades_to_not_cacheable():
    """Invariant: exclusive tools never cache, even if caller passes cacheable=True."""
    _register("t.mut", lambda **_: None, exclusive=True, cacheable=True)
    spec = _registry.get("t.mut")
    assert spec.exclusive is True
    assert spec.cacheable is False


def test_dispatch_cache_miss_invokes_handler():
    calls = {"n": 0}

    async def h(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text(f"call-{calls['n']}")

    _register("t.cm", h, cacheable=True)
    cache = ToolCache()
    ctx = _ctx(cache=cache)
    result, rec = _run(dispatch_one("t.cm", {"q": 1}, ctx=ctx))
    assert calls["n"] == 1
    assert result.metadata.get("cache_hit") is None
    # Second call with the same args → handler NOT invoked again
    result2, rec2 = _run(dispatch_one("t.cm", {"q": 1}, ctx=ctx))
    assert calls["n"] == 1  # no additional invocation
    assert result2.metadata["cache_hit"] is True
    assert rec2.wall_time_ms == 0


def test_dispatch_cache_miss_on_different_args():
    calls = {"n": 0}

    async def h(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("t.dm", h, cacheable=True)
    cache = ToolCache()
    ctx = _ctx(cache=cache)
    _run(dispatch_one("t.dm", {"a": 1}, ctx=ctx))
    _run(dispatch_one("t.dm", {"a": 2}, ctx=ctx))
    assert calls["n"] == 2


def test_exclusive_tool_never_caches_even_with_cache_attached():
    calls = {"n": 0}

    async def h(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("t.ex", h, exclusive=True)
    cache = ToolCache()
    ctx = _ctx(cache=cache)
    _run(dispatch_one("t.ex", {}, ctx=ctx))
    _run(dispatch_one("t.ex", {}, ctx=ctx))
    assert calls["n"] == 2


def test_dispatch_without_ctx_cache_still_works():
    """Backward compat: ctx without tool_cache must not raise."""
    async def h(*, ctx, args):
        return ToolResult.text("ok")

    _register("t.nc", h, cacheable=True)
    ctx = _ctx(cache=None)
    result, _ = _run(dispatch_one("t.nc", {}, ctx=ctx))
    assert not result.is_error


def test_errored_calls_not_cached():
    calls = {"n": 0}

    async def h(*, ctx, args):
        calls["n"] += 1
        return ToolResult.error("nope")

    _register("t.err", h, cacheable=True)
    cache = ToolCache()
    ctx = _ctx(cache=cache)
    _run(dispatch_one("t.err", {}, ctx=ctx))
    _run(dispatch_one("t.err", {}, ctx=ctx))
    assert calls["n"] == 2  # both invoked — no cached error


def test_invalidation_chain_wipes_dependents():
    calls = {"reader": 0}

    async def read_handler(*, ctx, args):
        calls["reader"] += 1
        return ToolResult.text("reader-output")

    async def mutate_handler(*, ctx, args):
        return ToolResult.text("mutated")

    _register("t.read", read_handler, cacheable=True)
    _register("t.mutate", mutate_handler, exclusive=True, invalidates=["t.read"])

    cache = ToolCache()
    ctx = _ctx(cache=cache)
    # First read populates cache
    _run(dispatch_one("t.read", {}, ctx=ctx))
    _run(dispatch_one("t.read", {}, ctx=ctx))
    assert calls["reader"] == 1  # second call was a hit
    # Mutate → invalidates t.read
    _run(dispatch_one("t.mutate", {}, ctx=ctx))
    # Next read must re-invoke handler
    _run(dispatch_one("t.read", {}, ctx=ctx))
    assert calls["reader"] == 2


def test_invalidation_skipped_on_errored_mutator():
    calls = {"reader": 0}

    async def read_handler(*, ctx, args):
        calls["reader"] += 1
        return ToolResult.text("ok")

    async def mutate_handler(*, ctx, args):
        return ToolResult.error("mutate failed")

    _register("t.read2", read_handler, cacheable=True)
    _register("t.mutate2", mutate_handler, exclusive=True, invalidates=["t.read2"])

    cache = ToolCache()
    ctx = _ctx(cache=cache)
    _run(dispatch_one("t.read2", {}, ctx=ctx))
    _run(dispatch_one("t.read2", {}, ctx=ctx))
    _run(dispatch_one("t.mutate2", {}, ctx=ctx))  # failed mutation
    _run(dispatch_one("t.read2", {}, ctx=ctx))  # should still hit cache
    assert calls["reader"] == 1


def test_cache_hit_still_records_into_session_recorder():
    """Observability invariant: cache hits show up in meta.call_history."""
    from poor_cli.session_recorder import SessionRecorder

    async def h(*, ctx, args):
        return ToolResult.text("ok")

    _register("t.sr", h, cacheable=True)
    cache = ToolCache()
    recorder = SessionRecorder()
    ctx = SimpleNamespace(
        cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None,
        tool_cache=cache, session_recorder=recorder,
    )
    _run(dispatch_one("t.sr", {}, ctx=ctx))
    _run(dispatch_one("t.sr", {}, ctx=ctx))
    assert len(recorder.records) == 2
    # Second record has wall_time_ms=0 since it was a cache hit
    assert recorder.records[1].rec.wall_time_ms == 0
