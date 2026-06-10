"""Tests for poor_cli.tools.debug."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import ToolResult
from poor_cli.tools import debug as debug_tools


def _ctx(plugins=None, notify_log=None, request=None):
    plugins = plugins or {}
    notify_log = notify_log if notify_log is not None else []

    async def notify(method, params):
        notify_log.append((method, params))

    return SimpleNamespace(
        cwd="/tmp",
        has_plugin=lambda name: plugins.get(name, False),
        notify_client=notify,
        request_client=request,
    )


def _run(coro):
    return asyncio.run(coro)


def test_set_breakpoint_without_debug_bridge_returns_error():
    ctx = _ctx(plugins={})
    r = _run(debug_tools.handle_set_breakpoint(ctx=ctx, args={"file": "x.py", "line": 1}))
    assert r.is_error
    assert r.metadata.get("degraded") == "unavailable"


def test_set_breakpoint_with_debug_bridge_fires_notification():
    log = []
    ctx = _ctx(plugins={"debug": True}, notify_log=log)
    r = _run(
        debug_tools.handle_set_breakpoint(
            ctx=ctx, args={"file": "x.py", "line": 5, "condition": "x > 0"}
        )
    )
    assert not r.is_error
    methods = [m for m, _ in log]
    assert methods == ["integration.debug.setBreakpoint"]
    _, params = log[0]
    assert params == {"file": "x.py", "line": 5, "condition": "x > 0"}


def test_step_invalid_direction():
    ctx = _ctx(plugins={"debug": True})
    r = _run(debug_tools.handle_step(ctx=ctx, args={"direction": "sideways"}))
    assert r.is_error


def test_step_and_continue_fire_notifications():
    log = []
    ctx = _ctx(plugins={"debug": True}, notify_log=log)
    _run(debug_tools.handle_step(ctx=ctx, args={"direction": "over"}))
    _run(debug_tools.handle_continue(ctx=ctx, args={}))
    methods = [m for m, _ in log]
    assert methods == ["integration.debug.step", "integration.debug.continue"]


def test_eval_and_stack_use_debug_request_bridge():
    async def request(method, params):
        return {"text": f"{method}:{params}"}

    ctx = _ctx(plugins={"debug": True}, request=request)
    r1 = _run(debug_tools.handle_stack(ctx=ctx, args={}))
    r2 = _run(debug_tools.handle_eval(ctx=ctx, args={"expression": "x"}))
    assert not r1.is_error
    assert not r2.is_error
    assert "integration.debug.stack" in r1.content[0].text
    assert "integration.debug.eval" in r2.content[0].text


def test_eval_without_request_bridge_returns_error():
    ctx = _ctx(plugins={"debug": True})
    r = _run(debug_tools.handle_eval(ctx=ctx, args={"expression": "x"}))
    assert r.is_error
