"""Tests for poor_cli.tools.watch."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import TableBlock
from poor_cli.tools import watch as watch_tools


def _ctx(cwd):
    return SimpleNamespace(
        cwd=str(cwd), has_plugin=lambda _n: False, notify_client=lambda *a, **k: None
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset():
    watch_tools._reset()
    yield
    watch_tools._reset()


def _init_git(cwd):
    subprocess.run(["git", "init", "-q"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=cwd, check=True)


def test_list_finds_directives(tmp_path):
    _init_git(tmp_path)
    (tmp_path / "a.py").write_text(
        "# hello\n# @poor-cli: rewrite this in asyncio\ndef foo(): pass\n"
    )
    (tmp_path / "b.js").write_text(
        "// @poor-cli: add types\nfunction bar() {}\n"
    )
    (tmp_path / "clean.py").write_text("# nothing to see\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    r = _run(watch_tools.handle_directives_list(ctx=_ctx(tmp_path), args={}))
    assert not r.is_error
    files = {d["file"] for d in r.metadata["directives"]}
    assert files == {"a.py", "b.js"}
    insts = {d["instruction"] for d in r.metadata["directives"]}
    assert "rewrite this in asyncio" in insts
    assert "add types" in insts


def test_consume_and_filter(tmp_path):
    _init_git(tmp_path)
    (tmp_path / "a.py").write_text("# @poor-cli: X\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    # list → 1
    r = _run(watch_tools.handle_directives_list(ctx=_ctx(tmp_path), args={}))
    assert len(r.metadata["directives"]) == 1
    # consume
    _run(
        watch_tools.handle_directives_consume(
            ctx=_ctx(tmp_path), args={"file": "a.py", "line": 1}
        )
    )
    # list → 0 (without include_consumed)
    r2 = _run(watch_tools.handle_directives_list(ctx=_ctx(tmp_path), args={}))
    assert "no pending" in r2.content[0].text
    # list with include_consumed → 1 with consumed=True
    r3 = _run(
        watch_tools.handle_directives_list(
            ctx=_ctx(tmp_path), args={"include_consumed": True}
        )
    )
    assert r3.metadata["directives"][0]["consumed"] is True


def test_consume_requires_file_and_line(tmp_path):
    r = _run(watch_tools.handle_directives_consume(ctx=_ctx(tmp_path), args={}))
    assert r.is_error


def test_clear_wipes_consumed_set(tmp_path):
    _init_git(tmp_path)
    (tmp_path / "a.py").write_text("# @poor-cli: X\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    _run(
        watch_tools.handle_directives_consume(
            ctx=_ctx(tmp_path), args={"file": "a.py", "line": 1}
        )
    )
    _run(watch_tools.handle_directives_clear(ctx=_ctx(tmp_path), args={}))
    r = _run(watch_tools.handle_directives_list(ctx=_ctx(tmp_path), args={}))
    assert len(r.metadata["directives"]) == 1
    assert r.metadata["directives"][0]["consumed"] is False
