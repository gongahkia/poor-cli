"""Proposal F.2 tests: idempotency key replay for exclusive tools."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import ToolResult
from poor_cli.tool_dispatcher import dispatch_one
from poor_cli.tool_errors import ToolError, TransientError
from poor_cli.tools import _registry


def _run(coro):
    return asyncio.run(coro)


def _ctx():
    return SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
    )


def _register(name: str, handler):
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "additionalProperties": True},
        handler=handler,
        exclusive=True,
    )


@pytest.fixture(autouse=True)
def _snapshot_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


def test_idempotency_replays_cached_result():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("idem.ok", handler)
    ctx = _ctx()
    _run(dispatch_one("idem.ok", {"idempotency_key": "abcdefgh"}, ctx=ctx))
    second, _ = _run(dispatch_one("idem.ok", {"idempotency_key": "abcdefgh"}, ctx=ctx))
    assert calls["n"] == 1
    assert second.metadata["idempotent_replay"] is True


def test_different_keys_run_independently():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("idem.keys", handler)
    ctx = _ctx()
    _run(dispatch_one("idem.keys", {"idempotency_key": "abcdefgh"}, ctx=ctx))
    _run(dispatch_one("idem.keys", {"idempotency_key": "ijklmnop"}, ctx=ctx))
    assert calls["n"] == 2


def test_idempotency_caches_error_result_too():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        raise ToolError("bad input", field="x")

    _register("idem.err", handler)
    ctx = _ctx()
    first, _ = _run(dispatch_one("idem.err", {"idempotency_key": "abcdefgh"}, ctx=ctx))
    second, _ = _run(dispatch_one("idem.err", {"idempotency_key": "abcdefgh"}, ctx=ctx))
    assert first.is_error
    assert second.is_error
    assert second.metadata["idempotent_replay"] is True
    assert calls["n"] == 1


def test_transient_error_not_cached():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientError("flaky")
        return ToolResult.text("ok")

    _register("idem.transient", handler)
    ctx = _ctx()
    first, _ = _run(dispatch_one("idem.transient", {"idempotency_key": "abcdefgh"}, ctx=ctx))
    second, _ = _run(dispatch_one("idem.transient", {"idempotency_key": "abcdefgh"}, ctx=ctx))
    assert first.is_error
    assert first.metadata["retry_exhausted"] is True
    assert second.is_error is False
    assert calls["n"] == 2


def test_no_key_means_no_dedup():
    calls = {"n": 0}

    async def handler(*, ctx, args):
        calls["n"] += 1
        return ToolResult.text("ok")

    _register("idem.none", handler)
    ctx = _ctx()
    _run(dispatch_one("idem.none", {}, ctx=ctx))
    _run(dispatch_one("idem.none", {}, ctx=ctx))
    assert calls["n"] == 2
