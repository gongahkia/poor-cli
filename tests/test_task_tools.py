"""Tests for poor_cli.tools.task."""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import CodeBlock, TableBlock
from poor_cli.tools import task as task_tools


def _ctx(cwd=".", notify_log=None, plugins=None):
    notify_log = notify_log if notify_log is not None else []
    plugins = plugins or {}

    async def notify(method, params):
        notify_log.append((method, params))

    return SimpleNamespace(
        cwd=str(cwd),
        has_plugin=lambda name: plugins.get(name, False),
        notify_client=notify,
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset():
    task_tools._reset()
    yield
    task_tools._reset()


def test_run_requires_name_or_cmd():
    r = _run(task_tools.handle_run(ctx=_ctx(), args={}))
    assert r.is_error


def test_run_cli_path_spawns_process(tmp_path):
    r = _run(
        task_tools.handle_run(
            ctx=_ctx(cwd=tmp_path),
            args={"cmd": [sys.executable, "-c", "print('hi')"]},
        )
    )
    assert not r.is_error
    assert "task_id" in r.metadata
    task_id = r.metadata["task_id"]
    # poll until completed
    for _ in range(50):
        r2 = _run(task_tools.handle_status(ctx=_ctx(cwd=tmp_path), args={"task_id": task_id}))
        if "completed" in r2.content[0].text:
            break
        import time; time.sleep(0.1)
    logs = _run(task_tools.handle_logs(ctx=_ctx(cwd=tmp_path), args={"task_id": task_id}))
    assert not logs.is_error
    code = logs.content[0]
    assert isinstance(code, CodeBlock)
    assert "hi" in code.code


def test_run_name_uses_make_target(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\t@printf built\n", encoding="utf-8")
    ctx = _ctx(cwd=tmp_path)
    r = _run(task_tools.handle_run(ctx=ctx, args={"name": "build"}))
    assert not r.is_error
    task_id = r.metadata["task_id"]
    for _ in range(50):
        r2 = _run(task_tools.handle_status(ctx=ctx, args={"task_id": task_id}))
        if "completed" in r2.content[0].text:
            break
        import time; time.sleep(0.1)
    logs = _run(task_tools.handle_logs(ctx=ctx, args={"task_id": task_id}))
    assert "built" in logs.content[0].code


def test_cancel_unknown_id():
    r = _run(task_tools.handle_cancel(ctx=_ctx(), args={"task_id": "nope"}))
    assert r.is_error
