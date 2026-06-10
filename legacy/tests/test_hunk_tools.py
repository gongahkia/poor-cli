"""Tests for poor_cli.tools.hunks."""

from __future__ import annotations

import asyncio
import subprocess
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import TableBlock, TextBlock, ToolResult
from poor_cli.tools import hunks as hunks_tools


def _sh(argv, cwd):
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    cwd = tmp_path / "r"
    cwd.mkdir()
    _sh(["git", "init", "-q", "-b", "main"], cwd)
    _sh(["git", "config", "user.email", "t@e.com"], cwd)
    _sh(["git", "config", "user.name", "T"], cwd)
    (cwd / "a.txt").write_text("one\ntwo\nthree\nfour\nfive\n")
    _sh(["git", "add", "a.txt"], cwd)
    _sh(["git", "commit", "-q", "-m", "init"], cwd)
    return cwd


def _ctx(cwd, notify_log=None, plugins=None):
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


def test_list_empty_for_clean_file(repo):
    r = _run(hunks_tools.handle_list(ctx=_ctx(repo), args={"file": "a.txt"}))
    assert not r.is_error
    text = " ".join(
        b.text for b in r.content if isinstance(b, TextBlock)
    )
    assert "no hunks" in text


def test_list_reports_hunks_for_dirty_file(repo):
    (repo / "a.txt").write_text("one\nTWO\nthree\nFOUR\nfive\n")
    r = _run(hunks_tools.handle_list(ctx=_ctx(repo), args={"file": "a.txt"}))
    assert not r.is_error
    tables = [b for b in r.content if isinstance(b, TableBlock)]
    assert tables
    assert tables[0].columns == ["#", "-", "+"]
    assert len(tables[0].rows) >= 1
    assert "hunks" in r.metadata
    assert len(r.metadata["hunks"]) >= 1


def test_stage_adds_file_and_fires_notification(repo):
    (repo / "new.txt").write_text("x\n")
    log = []
    ctx = _ctx(repo, notify_log=log, plugins={"gitsigns": True})
    r = _run(hunks_tools.handle_stage(ctx=ctx, args={"file": "new.txt"}))
    assert not r.is_error
    methods = [m for m, _ in log]
    assert "integration.gitsigns.stage" in methods
    st = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "A  new.txt" in st


def test_reset_restores_file(repo):
    (repo / "a.txt").write_text("destroyed\n")
    ctx = _ctx(repo)
    r = _run(hunks_tools.handle_reset(ctx=ctx, args={"file": "a.txt"}))
    assert not r.is_error
    assert (repo / "a.txt").read_text() == "one\ntwo\nthree\nfour\nfive\n"


def test_ai_mark_fires_notification(tmp_path):
    log = []
    ctx = _ctx(tmp_path, notify_log=log, plugins={"gitsigns": True})
    r = _run(hunks_tools.handle_ai_mark(ctx=ctx, args={"file": "x.py", "line": 3}))
    assert not r.is_error
    assert log == [("integration.gitsigns.aiMark", {"file": "x.py", "line": 3})]


def test_parse_hunks_multi():
    # Two-hunk diff body
    diff = """\
--- a/x.py
+++ b/x.py
@@ -1,2 +1,3 @@
 a
+b
 c
@@ -10,1 +11,2 @@
 z
+zz
"""
    hunks = hunks_tools._parse_hunks(diff)
    assert len(hunks) == 2
    assert hunks[0]["old_start"] == 1 and hunks[0]["new_start"] == 1
    assert hunks[1]["old_start"] == 10 and hunks[1]["new_start"] == 11
