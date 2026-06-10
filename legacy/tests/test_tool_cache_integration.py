"""E.1b integration: real tools marked cacheable/invalidate work end-to-end
against a real git repo via the dispatcher. Proves the declarations added in
E.1b (not just the abstract plumbing from E.1a)."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli.tool_cache import ToolCache
from poor_cli.tool_dispatcher import dispatch_one
import poor_cli.tools  # noqa: F401 — register tools


@pytest.fixture
def repo(tmp_path):
    cwd = tmp_path / "r"
    cwd.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.email", "t@e"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=cwd, check=True)
    (cwd / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "a.txt"], cwd=cwd, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=cwd, check=True)
    return cwd


def _ctx(cwd, cache):
    return SimpleNamespace(
        cwd=str(cwd),
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_cache=cache,
    )


def _run(coro):
    return asyncio.run(coro)


def test_git_status_cached_across_calls(repo):
    cache = ToolCache()
    ctx = _ctx(repo, cache)
    r1, _ = _run(dispatch_one("git.status", {}, ctx=ctx))
    assert r1.metadata.get("cache_hit") is None
    r2, _ = _run(dispatch_one("git.status", {}, ctx=ctx))
    assert r2.metadata.get("cache_hit") is True


def test_git_status_cache_invalidated_after_git_stage(repo):
    cache = ToolCache()
    ctx = _ctx(repo, cache)
    # Populate
    _run(dispatch_one("git.status", {}, ctx=ctx))
    # Mutate
    (repo / "b.txt").write_text("new\n")
    r_stage, _ = _run(dispatch_one("git.stage", {"paths": ["b.txt"]}, ctx=ctx))
    assert not r_stage.is_error
    # Next git.status must be a fresh dispatch (invalidates chain fired)
    r_post, _ = _run(dispatch_one("git.status", {}, ctx=ctx))
    assert r_post.metadata.get("cache_hit") is None


def test_git_status_cache_invalidated_after_git_commit(repo):
    cache = ToolCache()
    ctx = _ctx(repo, cache)
    # Stage + commit (stage already invalidates status, so this specifically
    # verifies git.commit's invalidation chain hits git.log too).
    (repo / "b.txt").write_text("new\n")
    _run(dispatch_one("git.stage", {"paths": ["b.txt"]}, ctx=ctx))
    # Populate git.log
    _run(dispatch_one("git.log", {"limit": 5}, ctx=ctx))
    # Confirm subsequent git.log is cached
    r_cached, _ = _run(dispatch_one("git.log", {"limit": 5}, ctx=ctx))
    assert r_cached.metadata.get("cache_hit") is True
    # Now commit
    _run(dispatch_one("git.commit", {"message": "test"}, ctx=ctx))
    # git.log must miss cache because git.commit invalidates it
    r_post, _ = _run(dispatch_one("git.log", {"limit": 5}, ctx=ctx))
    assert r_post.metadata.get("cache_hit") is None


def test_different_args_bypass_cache(repo):
    cache = ToolCache()
    ctx = _ctx(repo, cache)
    _run(dispatch_one("git.log", {"limit": 5}, ctx=ctx))
    r, _ = _run(dispatch_one("git.log", {"limit": 10}, ctx=ctx))
    assert r.metadata.get("cache_hit") is None


def test_fs_browse_cached(repo):
    cache = ToolCache()
    ctx = _ctx(repo, cache)
    _run(dispatch_one("fs.browse", {"path": "."}, ctx=ctx))
    r, _ = _run(dispatch_one("fs.browse", {"path": "."}, ctx=ctx))
    assert r.metadata.get("cache_hit") is True


def test_meta_list_tools_cached():
    cache = ToolCache()
    ctx = SimpleNamespace(
        cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None,
        tool_cache=cache,
    )
    _run(dispatch_one("meta.list_tools", {"domain": "git"}, ctx=ctx))
    r, _ = _run(dispatch_one("meta.list_tools", {"domain": "git"}, ctx=ctx))
    assert r.metadata.get("cache_hit") is True
