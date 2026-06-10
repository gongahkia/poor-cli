"""Tests for the Phase-C tool dispatcher (T1, T2, T4, T5, T10)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import TextBlock, ToolResult
from poor_cli.tool_dispatcher import (
    DEFAULT_RETRY_POLICY,
    TRANSIENT_RETRY_POLICY,
    RetryPolicy,
    dispatch_many,
    dispatch_one,
)
from poor_cli.tool_errors import (
    PermissionDenied,
    ToolError,
    TransientError,
)
from poor_cli.tools import _registry


@pytest.fixture
def ctx():
    return SimpleNamespace(
        cwd="/tmp", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None
    )


def _register(name: str, handler, *, exclusive=False, timeout_s=10.0, schema=None):
    _registry.register_tool(
        name=name,
        description="t",
        schema=schema or {"type": "object", "properties": {}, "additionalProperties": False},
        handler=handler,
        exclusive=exclusive,
        timeout_s=timeout_s,
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_after():
    # Snapshot the live registry so we can restore it after inserting
    # per-test fakes. We don't want a test fake to clobber git.commit etc.
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


# ──────────────── T1: schema validation ────────────────


def test_validation_rejects_missing_required(ctx):
    async def handler(*, ctx, args):
        return ToolResult.text("should not run")

    _register(
        "t.requires_message",
        handler,
        schema={
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
    )
    result, rec = _run(dispatch_one("t.requires_message", {}, ctx=ctx))
    assert result.is_error
    assert result.metadata["validation_error"] is True
    assert "message" in result.content[0].text


def test_validation_rejects_wrong_type(ctx):
    async def handler(*, ctx, args):
        return ToolResult.text("ok")

    _register(
        "t.wants_int",
        handler,
        schema={
            "type": "object",
            "properties": {"n": {"type": "integer"}},
            "additionalProperties": False,
        },
    )
    result, _ = _run(dispatch_one("t.wants_int", {"n": "seven"}, ctx=ctx))
    assert result.is_error
    assert result.metadata["validation_error"] is True


def test_validation_accepts_valid_args(ctx):
    async def handler(*, ctx, args):
        return ToolResult.text(f"got {args['n']}")

    _register(
        "t.ok",
        handler,
        schema={
            "type": "object",
            "required": ["n"],
            "properties": {"n": {"type": "integer"}},
        },
    )
    result, rec = _run(dispatch_one("t.ok", {"n": 42}, ctx=ctx))
    assert not result.is_error
    assert rec.returncode == 0
    assert "got 42" in result.content[0].text


# ──────────────── T4: timeout ────────────────


def test_timeout_preserves_partial_none(ctx):
    async def handler(*, ctx, args):
        await asyncio.sleep(5)
        return ToolResult.text("never")

    _register("t.hang", handler, timeout_s=0.1)
    result, rec = _run(dispatch_one("t.hang", {}, ctx=ctx))
    assert result.is_error
    assert result.metadata["timeout"] is True
    assert rec.timeout is True


def test_no_timeout_when_handler_returns_fast(ctx):
    async def handler(*, ctx, args):
        return ToolResult.text("done")

    _register("t.fast", handler, timeout_s=1.0)
    result, rec = _run(dispatch_one("t.fast", {}, ctx=ctx))
    assert not result.is_error
    assert result.metadata.get("timeout") is None


# ──────────────── T5: retry ────────────────


def test_retry_transient_succeeds_eventually(ctx):
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("flaky")
        return ToolResult.text("finally!")

    _register("t.flaky", handler)
    policy = RetryPolicy(max_attempts=3, base_delay_s=0.01, jitter=0)
    result, rec = _run(dispatch_one("t.flaky", {}, ctx=ctx, policy=policy))
    assert not result.is_error
    assert rec.retry_attempts == 3
    assert result.metadata["retry_attempts"] == 3


def test_retry_exhausted(ctx):
    async def handler(*, ctx, args):
        raise TransientError("always fail")

    _register("t.broken", handler)
    policy = RetryPolicy(max_attempts=2, base_delay_s=0.01, jitter=0)
    result, rec = _run(dispatch_one("t.broken", {}, ctx=ctx, policy=policy))
    assert result.is_error
    assert result.metadata["retry_exhausted"] is True
    assert rec.retry_attempts == 2


def test_no_retry_on_validation_error(ctx):
    async def handler(*, ctx, args):
        raise TransientError("shouldn't be called")

    _register(
        "t.needs_x",
        handler,
        schema={"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}},
    )
    policy = RetryPolicy(max_attempts=5, base_delay_s=0.0, jitter=0)
    result, rec = _run(dispatch_one("t.needs_x", {}, ctx=ctx, policy=policy))
    assert result.is_error
    assert result.metadata["validation_error"] is True
    # One attempt only — validation short-circuits the retry loop.
    assert rec.retry_attempts == 1


def test_no_retry_on_generic_exception(ctx):
    async def handler(*, ctx, args):
        raise ValueError("boom")

    _register("t.boom", handler)
    policy = RetryPolicy(max_attempts=5, base_delay_s=0.0, jitter=0)
    result, rec = _run(dispatch_one("t.boom", {}, ctx=ctx, policy=policy))
    assert result.is_error
    assert result.metadata["handler_exception"] is True
    assert rec.retry_attempts == 1


# ──────────────── T2: parallel dispatch ────────────────


def test_dispatch_many_runs_non_exclusive_in_parallel(ctx):
    async def slow_a(*, ctx, args):
        await asyncio.sleep(0.2)
        return ToolResult.text("a")

    async def slow_b(*, ctx, args):
        await asyncio.sleep(0.2)
        return ToolResult.text("b")

    _register("par.a", slow_a)
    _register("par.b", slow_b)
    t0 = time.monotonic()
    results = _run(
        dispatch_many(
            [("par.a", {}), ("par.b", {})],
            ctx=ctx,
        )
    )
    elapsed = time.monotonic() - t0
    assert len(results) == 2
    # both ran in parallel — wall time should be ~0.2s, not ~0.4s
    assert elapsed < 0.35, f"expected parallel, got {elapsed:.3f}s"
    texts = [r.content[0].text for r, _ in results]
    assert texts == ["a", "b"]


def test_dispatch_many_exclusive_runs_serial(ctx):
    running = {"count": 0, "max_concurrent": 0}
    lock = asyncio.Lock()

    async def excl(*, ctx, args):
        async with lock:
            running["count"] += 1
            running["max_concurrent"] = max(running["max_concurrent"], running["count"])
        await asyncio.sleep(0.1)
        async with lock:
            running["count"] -= 1
        return ToolResult.text("done")

    _register("excl.a", excl, exclusive=True)
    _register("excl.b", excl, exclusive=True)
    _run(dispatch_many([("excl.a", {}), ("excl.b", {})], ctx=ctx))
    assert running["max_concurrent"] == 1


def test_dispatch_many_preserves_order(ctx):
    async def handler(tag):
        async def inner(*, ctx, args):
            return ToolResult.text(tag)

        return inner

    _register("ord.x", asyncio.run(handler("x")))
    _register("ord.y", asyncio.run(handler("y")))
    _register("ord.z", asyncio.run(handler("z")))
    results = _run(
        dispatch_many(
            [("ord.z", {}), ("ord.x", {}), ("ord.y", {})],
            ctx=ctx,
        )
    )
    texts = [r.content[0].text for r, _ in results]
    assert texts == ["z", "x", "y"]


# ──────────────── T10: tool composition via ctx.call_tool ────────────────


def test_ctx_call_tool_chains_handlers(ctx):
    async def child(*, ctx, args):
        return ToolResult.text(f"child({args.get('v')})")

    async def parent(*, ctx, args):
        inner = await ctx.call_tool("comp.child", {"v": 42})
        return ToolResult.text(f"parent wrapping {inner.content[0].text}")

    _register(
        "comp.child",
        child,
        schema={"type": "object", "properties": {"v": {"type": "integer"}}},
    )
    _register("comp.parent", parent)
    result, _ = _run(dispatch_one("comp.parent", {}, ctx=ctx))
    assert not result.is_error
    assert "child(42)" in result.content[0].text


def test_composition_depth_limit(ctx):
    async def recursive(*, ctx, args):
        return await ctx.call_tool("comp.recur", {})

    _register("comp.recur", recursive)
    # Initial call is depth 0; recursive calls should hit the cap at depth 3.
    result, _ = _run(dispatch_one("comp.recur", {}, ctx=ctx))
    assert result.is_error
    assert result.metadata["depth_exhausted"] is True


# ──────────────── misc: permission denied, unknown tool ────────────────


def test_permission_denied(ctx):
    async def handler(*, ctx, args):
        raise PermissionDenied("not allowed", rule="deny:write")

    _register("t.denied", handler)
    result, _ = _run(dispatch_one("t.denied", {}, ctx=ctx))
    assert result.is_error
    assert result.metadata["permission_denied"] is True


def test_tool_error_sets_metadata(ctx):
    async def handler(*, ctx, args):
        raise ToolError("bad input", field="x")

    _register("t.toolerror", handler)
    result, _ = _run(dispatch_one("t.toolerror", {}, ctx=ctx))
    assert result.is_error
    assert result.metadata.get("field") == "x"


def test_unknown_tool_is_error():
    result, _ = _run(dispatch_one("never.registered", {}, ctx=None))
    assert result.is_error
    assert result.metadata["unknown_tool"] is True


# ──────────────── T8: cost attribution ────────────────


def test_cost_attribution_captures_wall_time(ctx):
    async def handler(*, ctx, args):
        await asyncio.sleep(0.05)
        return ToolResult.text("ok")

    _register("t.timed", handler)
    result, rec = _run(dispatch_one("t.timed", {}, ctx=ctx))
    assert rec.wall_time_ms >= 40
    assert result.metadata["wall_time_ms"] >= 40


def test_cost_attribution_captures_tokens(ctx):
    async def handler(*, ctx, args):
        return ToolResult(
            content=[TextBlock(text="ok")],
            metadata={"token_cost": {"in": 100, "out": 50}},
        )

    _register("t.tokens", handler)
    _result, rec = _run(dispatch_one("t.tokens", {}, ctx=ctx))
    assert rec.tokens_in == 100
    assert rec.tokens_out == 50
