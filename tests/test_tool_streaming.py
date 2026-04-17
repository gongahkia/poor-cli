"""Tests for T3 streaming tool output."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import CodeBlock, TextBlock, ToolResult
from poor_cli.tool_dispatcher import dispatch_one
from poor_cli.tools import _registry


def _register(name: str, handler, *, timeout_s=2.0):
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=handler,
        timeout_s=timeout_s,
    )


def _ctx(notify_log=None):
    notify_log = notify_log if notify_log is not None else []

    async def notify(method, params):
        notify_log.append((method, params))

    return SimpleNamespace(
        cwd=".", has_plugin=lambda _n: False, notify_client=notify
    ), notify_log


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clean_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


def test_streaming_handler_yields_multiple_chunks():
    async def streaming(*, ctx, args):
        for i in range(3):
            yield TextBlock(text=f"chunk-{i}")

    _register("s.triple", streaming)
    ctx, log = _ctx()
    result, rec = _run(dispatch_one("s.triple", {}, ctx=ctx))
    assert not result.is_error
    assert len(result.content) == 3
    assert [b.text for b in result.content] == ["chunk-0", "chunk-1", "chunk-2"]
    # Each chunk was streamed via notification
    methods = [m for m, _ in log]
    assert methods.count("poor-cli/toolStream") == 3
    # Chunk indices are 0, 1, 2
    assert [p["chunkIndex"] for _, p in log] == [0, 1, 2]


def test_streaming_handler_can_mark_final_mid_stream():
    async def streaming(*, ctx, args):
        yield {"block": TextBlock(text="a")}
        yield {"block": CodeBlock(language="py", code="print(1)"), "final": True}

    _register("s.final", streaming)
    ctx, log = _ctx()
    result, _ = _run(dispatch_one("s.final", {}, ctx=ctx))
    assert not result.is_error
    # second chunk's "final" flag is reflected in the last notification
    assert log[-1][1]["final"] is True


def test_streaming_handler_timeout_preserves_partial():
    async def slow_stream(*, ctx, args):
        yield TextBlock(text="one")
        await asyncio.sleep(5)
        yield TextBlock(text="never")

    _register("s.slow", slow_stream, timeout_s=0.2)
    ctx, _log = _ctx()
    result, rec = _run(dispatch_one("s.slow", {}, ctx=ctx))
    assert result.is_error
    assert result.metadata.get("timeout") is True
    # Partial chunk preserved
    texts = [b.text for b in result.content if isinstance(b, TextBlock)]
    assert any(t == "one" for t in texts)
    assert any("timed out" in t for t in texts)


def test_streaming_handler_with_metadata():
    async def streaming(*, ctx, args):
        yield {"block": TextBlock(text="done"), "metadata": {"token_cost": {"in": 42, "out": 10}}}

    _register("s.meta", streaming)
    ctx, _ = _ctx()
    _result, rec = _run(dispatch_one("s.meta", {}, ctx=ctx))
    assert rec.tokens_in == 42
    assert rec.tokens_out == 10


def test_non_streaming_handler_unchanged():
    async def normal(*, ctx, args):
        return ToolResult.text("ok")

    _register("s.normal", normal)
    ctx, log = _ctx()
    result, _ = _run(dispatch_one("s.normal", {}, ctx=ctx))
    assert not result.is_error
    # No toolStream notifications for non-streaming handlers
    stream_methods = [m for m, _ in log if m == "poor-cli/toolStream"]
    assert stream_methods == []


def test_streaming_handler_empty_produces_placeholder():
    async def empty(*, ctx, args):
        if False:  # type: ignore
            yield TextBlock(text="never")  # make it a generator
        return

    _register("s.empty", empty)
    ctx, _ = _ctx()
    result, _ = _run(dispatch_one("s.empty", {}, ctx=ctx))
    assert not result.is_error
    assert len(result.content) == 1
    assert "no output" in result.content[0].text
