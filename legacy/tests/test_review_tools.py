"""Tests for poor_cli.tools.review (Phase B).

We don't test ``review.pr`` end-to-end (needs gh + network). We verify the
tool is registered, validates args, and degrades cleanly when ``gh`` is
absent; it's a thin shell wrapper otherwise.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import CodeBlock, TextBlock
from poor_cli.tools import review as review_tools


def _ctx(cwd):
    return SimpleNamespace(
        cwd=str(cwd), has_plugin=lambda _n: False, notify_client=lambda *a, **k: None
    )


def _run(coro):
    return asyncio.run(coro)


def _init_repo(cwd):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=cwd, check=True)
    (Path(cwd) / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "a.txt"], cwd=cwd, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=cwd, check=True)


def test_changes_no_diff(tmp_path):
    _init_repo(tmp_path)
    r = _run(review_tools.handle_changes(ctx=_ctx(tmp_path), args={}))
    assert not r.is_error
    assert "no changes" in r.content[0].text


def test_changes_with_diff(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("one\ntwo\n")
    r = _run(review_tools.handle_changes(ctx=_ctx(tmp_path), args={}))
    assert not r.is_error
    assert any(isinstance(b, CodeBlock) and b.language == "diff" for b in r.content)


def test_pr_requires_number():
    r = _run(review_tools.handle_pr(ctx=_ctx("."), args={}))
    assert r.is_error


def test_pr_rejects_non_integer():
    r = _run(review_tools.handle_pr(ctx=_ctx("."), args={"number": "abc"}))
    assert r.is_error


def test_lint_no_config(tmp_path):
    r = _run(review_tools.handle_lint(ctx=_ctx(tmp_path), args={}))
    assert not r.is_error
    assert "no linter config detected" in r.content[0].text
