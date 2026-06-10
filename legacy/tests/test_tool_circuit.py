"""Proposal F.1 tests: per-tool circuit breaker behavior."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import ToolResult
from poor_cli.tool_dispatcher import dispatch_one
from poor_cli.tool_health import reset as health_reset
from poor_cli.tools import _registry


def _run(coro):
    return asyncio.run(coro)


def _ctx():
    return SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
    )


def _register(name: str, handler, **kwargs):
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "additionalProperties": True},
        handler=handler,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _snapshot_registry_and_health():
    before = dict(_registry._TOOLS)
    health_reset()
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)
    health_reset()


def test_circuit_opens_after_threshold():
    calls = {"n": 0}

    async def fail(*, ctx, args):
        calls["n"] += 1
        return ToolResult.error("boom")

    _register("c.fail", fail, circuit_threshold=3, circuit_window_s=60.0, circuit_cooldown_s=30.0)
    ctx = _ctx()
    _run(dispatch_one("c.fail", {}, ctx=ctx))
    _run(dispatch_one("c.fail", {}, ctx=ctx))
    _run(dispatch_one("c.fail", {}, ctx=ctx))
    result, rec = _run(dispatch_one("c.fail", {}, ctx=ctx))
    assert calls["n"] == 3
    assert result.is_error
    assert result.metadata["circuit_open"] is True
    assert rec.wall_time_ms == 0


def test_circuit_does_not_open_for_disabled_tools():
    calls = {"n": 0}

    async def fail(*, ctx, args):
        calls["n"] += 1
        return ToolResult.error("boom")

    _register("c.disabled", fail, circuit_threshold=1, circuit_disabled=True)
    ctx = _ctx()
    for _ in range(4):
        result, _ = _run(dispatch_one("c.disabled", {}, ctx=ctx))
        assert result.metadata.get("circuit_open") is not True
    assert calls["n"] == 4


def test_circuit_half_opens_after_cooldown():
    calls = {"n": 0}

    async def fail(*, ctx, args):
        calls["n"] += 1
        return ToolResult.error("boom")

    _register("c.cool", fail, circuit_threshold=1, circuit_cooldown_s=0.05)
    ctx = _ctx()
    _run(dispatch_one("c.cool", {}, ctx=ctx))  # fail -> trip
    second, _ = _run(dispatch_one("c.cool", {}, ctx=ctx))  # open
    assert second.metadata["circuit_open"] is True
    time.sleep(0.12)
    third, _ = _run(dispatch_one("c.cool", {}, ctx=ctx))  # probe
    assert calls["n"] == 2
    assert "boom" in third.content[0].text


def test_circuit_half_open_success_closes():
    calls = {"n": 0}

    async def flaky(*, ctx, args):
        calls["n"] += 1
        if calls["n"] == 1:
            return ToolResult.error("boom")
        return ToolResult.text("ok")

    _register("c.recover", flaky, circuit_threshold=1, circuit_cooldown_s=0.05)
    ctx = _ctx()
    _run(dispatch_one("c.recover", {}, ctx=ctx))  # fail -> trip
    _run(dispatch_one("c.recover", {}, ctx=ctx))  # open
    time.sleep(0.12)
    probe, _ = _run(dispatch_one("c.recover", {}, ctx=ctx))  # half-open probe succeeds
    after, _ = _run(dispatch_one("c.recover", {}, ctx=ctx))  # closed, allowed
    assert probe.is_error is False
    assert after.metadata.get("circuit_open") is not True
    assert calls["n"] == 3


def test_circuit_half_open_failure_reopens():
    calls = {"n": 0}

    async def fail(*, ctx, args):
        calls["n"] += 1
        return ToolResult.error("boom")

    _register("c.reopen", fail, circuit_threshold=1, circuit_cooldown_s=0.05)
    ctx = _ctx()
    _run(dispatch_one("c.reopen", {}, ctx=ctx))  # fail -> trip
    _run(dispatch_one("c.reopen", {}, ctx=ctx))  # open
    time.sleep(0.12)
    _run(dispatch_one("c.reopen", {}, ctx=ctx))  # probe fails -> open
    blocked, _ = _run(dispatch_one("c.reopen", {}, ctx=ctx))  # blocked again
    assert blocked.metadata["circuit_open"] is True
    assert calls["n"] == 2
