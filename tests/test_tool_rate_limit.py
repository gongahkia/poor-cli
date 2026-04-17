"""Proposal F.4 tests: per-tool rate limiting."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import poor_cli.tool_dispatcher as tool_dispatcher
import poor_cli.tool_rate_limit as tool_rate_limit
from poor_cli.tool_blocks import ToolResult
from poor_cli.tool_dispatcher import dispatch_one
from poor_cli.tools import _registry


def _run(coro):
    return asyncio.run(coro)


def _ctx(*, config=None):
    payload = {
        "cwd": ".",
        "has_plugin": lambda _n: False,
        "notify_client": lambda *a, **k: None,
    }
    if config is not None:
        payload["config"] = config
    return SimpleNamespace(**payload)


def _register(name: str, handler, *, max_per_minute: int):
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "additionalProperties": True},
        handler=handler,
        max_per_minute=max_per_minute,
        circuit_disabled=True,
    )


@pytest.fixture(autouse=True)
def _snapshot_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


def test_under_cap_allows_all_calls():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("rl.ok", handler, max_per_minute=3)
    ctx = _ctx()
    for _ in range(3):
        result, _ = _run(dispatch_one("rl.ok", {}, ctx=ctx))
        assert result.is_error is False
    assert calls["n"] == 3


def test_over_cap_rejects_immediately():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("rl.cap", handler, max_per_minute=3)
    ctx = _ctx()
    _run(dispatch_one("rl.cap", {}, ctx=ctx))
    _run(dispatch_one("rl.cap", {}, ctx=ctx))
    _run(dispatch_one("rl.cap", {}, ctx=ctx))
    blocked, _ = _run(dispatch_one("rl.cap", {}, ctx=ctx))
    assert blocked.is_error
    assert blocked.metadata["rate_limited"] is True
    assert blocked.metadata["retry_after_s"] > 0
    assert calls["n"] == 3


def test_window_slides_after_60s(monkeypatch):
    now = {"t": 1000.0}

    monkeypatch.setattr(tool_rate_limit.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(tool_dispatcher.time, "monotonic", lambda: now["t"])

    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("rl.slide", handler, max_per_minute=2)
    ctx = _ctx()
    _run(dispatch_one("rl.slide", {}, ctx=ctx))
    _run(dispatch_one("rl.slide", {}, ctx=ctx))
    blocked, _ = _run(dispatch_one("rl.slide", {}, ctx=ctx))
    assert blocked.metadata["rate_limited"] is True

    now["t"] += 61.0
    after, _ = _run(dispatch_one("rl.slide", {}, ctx=ctx))
    assert after.is_error is False
    assert calls["n"] == 3


def test_rate_limit_disabled_via_config():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("rl.off", handler, max_per_minute=1)
    cfg = SimpleNamespace(tools=SimpleNamespace(rate_limits=False))
    ctx = _ctx(config=cfg)
    _run(dispatch_one("rl.off", {}, ctx=ctx))
    _run(dispatch_one("rl.off", {}, ctx=ctx))
    _run(dispatch_one("rl.off", {}, ctx=ctx))
    assert calls["n"] == 3
