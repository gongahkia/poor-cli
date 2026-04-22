"""Tests for poor_cli.tools.diagnostics."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from poor_cli.tools import diagnostics as diag_tools


def _ctx(notify_log=None):
    notify_log = notify_log if notify_log is not None else []

    async def notify(method, params):
        notify_log.append((method, params))

    return SimpleNamespace(cwd="/tmp", has_plugin=lambda _name: False, notify_client=notify)


def _run(coro):
    return asyncio.run(coro)


def test_emit_rejects_non_list():
    ctx = _ctx()
    r = _run(diag_tools.handle_emit(ctx=ctx, args={"items": "oops"}))
    assert r.is_error


def test_emit_filters_invalid_items_and_fires_notification():
    log = []
    ctx = _ctx(notify_log=log)
    r = _run(
        diag_tools.handle_emit(
            ctx=ctx,
            args={
                "items": [
                    {"file": "a.py", "line": 3, "message": "suspicious import"},
                    {"line": 9},  # missing file → dropped
                    {"file": "", "message": ""},  # empty → dropped
                    {"file": "b.py", "message": "TODO", "severity": "warn"},
                ]
            },
        )
    )
    assert not r.is_error
    assert len(log) == 1
    method, params = log[0]
    assert method == "integration.diagnostics.emit"
    files = [i["file"] for i in params["items"]]
    assert files == ["a.py", "b.py"]


def test_clear_fires_notification():
    log = []
    ctx = _ctx(notify_log=log)
    r = _run(diag_tools.handle_clear(ctx=ctx, args={}))
    assert not r.is_error
    assert log == [("integration.diagnostics.clear", {})]


def test_list_not_yet_implemented():
    ctx = _ctx()
    r = _run(diag_tools.handle_list(ctx=ctx, args={}))
    assert r.metadata.get("not_implemented") is True
