"""Unit tests for poor_cli.tools.git (Phase B / Proposal B).

These tests execute real ``git`` subprocesses inside a disposable tmp_path
repo. They do not reach the network (no ``git push`` test with a remote).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tools import _registry
from poor_cli.tools import git as git_tools


def _run(argv, cwd):
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    _run(["git", "init", "-q", "-b", "main"], cwd)
    _run(["git", "config", "user.email", "t@example.com"], cwd)
    _run(["git", "config", "user.name", "Test"], cwd)
    (cwd / "a.txt").write_text("alpha\n")
    _run(["git", "add", "a.txt"], cwd)
    _run(["git", "commit", "-q", "-m", "init"], cwd)
    return cwd


def _ctx(cwd, plugins=None, notify_log=None):
    plugins = plugins or {}
    notify_log = notify_log if notify_log is not None else []

    async def notify(method, params):
        notify_log.append((method, params))

    return SimpleNamespace(
        cwd=str(cwd),
        has_plugin=lambda name: plugins.get(name, False),
        notify_client=notify,
    )


def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_status_clean(repo):
    ctx = _ctx(repo)
    result = _run_async(git_tools.handle_status(ctx=ctx, args={}))
    assert isinstance(result, ToolResult)
    assert not result.is_error
    texts = [b.text for b in result.content if isinstance(b, TextBlock)]
    assert any("branch:" in t or "clean" in t for t in texts)


def test_status_dirty(repo):
    (repo / "b.txt").write_text("beta\n")
    (repo / "a.txt").write_text("alpha modified\n")
    ctx = _ctx(repo)
    result = _run_async(git_tools.handle_status(ctx=ctx, args={}))
    assert not result.is_error
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert tables, "expected a status TableBlock"
    paths = {row[2] for row in tables[0].rows}
    assert "a.txt" in paths
    assert "b.txt" in paths


def test_diff_returns_code_block(repo):
    (repo / "a.txt").write_text("alpha\nextra\n")
    ctx = _ctx(repo)
    result = _run_async(git_tools.handle_diff(ctx=ctx, args={}))
    assert not result.is_error
    blocks = [b for b in result.content if isinstance(b, CodeBlock)]
    assert blocks and blocks[0].language == "diff"
    assert "+extra" in blocks[0].code


def test_stage_and_unstage(repo):
    (repo / "new.txt").write_text("new\n")
    ctx = _ctx(repo)
    staged = _run_async(git_tools.handle_stage(ctx=ctx, args={"paths": ["new.txt"]}))
    assert not staged.is_error
    # git should now see new.txt as staged
    st = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "A  new.txt" in st
    unstaged = _run_async(git_tools.handle_unstage(ctx=ctx, args={"paths": ["new.txt"]}))
    assert not unstaged.is_error
    st2 = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "?? new.txt" in st2


def test_commit_cli_path_commits(repo):
    (repo / "a.txt").write_text("alpha commit change\n")
    ctx = _ctx(repo, plugins={})  # no commit UI available
    _run_async(git_tools.handle_stage(ctx=ctx, args={"paths": ["a.txt"]}))
    result = _run_async(
        git_tools.handle_commit(
            ctx=ctx, args={"message": "chore: test commit from poor-cli tool"}
        )
    )
    assert not result.is_error
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert log == "chore: test commit from poor-cli tool"


def test_commit_ui_path_fires_notification_and_commits(repo):
    (repo / "a.txt").write_text("alpha another change\n")
    notify_log: list = []
    ctx = _ctx(repo, plugins={"commit_ui": True}, notify_log=notify_log)
    _run_async(git_tools.handle_stage(ctx=ctx, args={"paths": ["a.txt"]}))
    result = _run_async(
        git_tools.handle_commit(
            ctx=ctx, args={"message": "feat: with commit ui"}
        )
    )
    assert not result.is_error
    methods = [m for m, _ in notify_log]
    assert "integration.git.openCommit" in methods
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    assert log == "feat: with commit ui"


def test_log_returns_table(repo):
    ctx = _ctx(repo)
    result = _run_async(git_tools.handle_log(ctx=ctx, args={"limit": 10}))
    assert not result.is_error
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert tables
    assert tables[0].columns == ["hash", "author", "when", "subject"]
    assert len(tables[0].rows) >= 1


def test_branch_list_and_create_and_checkout(repo):
    ctx = _ctx(repo)
    r1 = _run_async(git_tools.handle_branch_list(ctx=ctx, args={}))
    assert not r1.is_error
    r2 = _run_async(
        git_tools.handle_branch_create(ctx=ctx, args={"name": "feature-x"})
    )
    assert not r2.is_error
    r3 = _run_async(
        git_tools.handle_branch_checkout(ctx=ctx, args={"name": "feature-x"})
    )
    assert not r3.is_error
    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert current == "feature-x"


def test_not_a_repo(tmp_path):
    ctx = _ctx(tmp_path)
    result = _run_async(git_tools.handle_status(ctx=ctx, args={}))
    assert result.is_error
    assert result.metadata.get("not_a_repo") is True


def test_registry_exposes_all_git_tools():
    names = set(_registry.tool_names())
    assert {
        "git.status",
        "git.diff",
        "git.stage",
        "git.unstage",
        "git.commit",
        "git.log",
        "git.branch.list",
        "git.branch.create",
        "git.branch.checkout",
        "git.push",
    } <= names
    assert _registry.get("git.commit").exclusive is True
    assert _registry.get("git.status").exclusive is False
