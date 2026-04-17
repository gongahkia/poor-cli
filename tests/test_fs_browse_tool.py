"""Tests for poor_cli.tools.fs."""

from __future__ import annotations

import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import TableBlock
from poor_cli.tools import fs as fs_tools


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


def test_browse_returns_entries(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_text("x")
    (tmp_path / "b.txt").write_text("b")
    r = _run(fs_tools.handle_browse(ctx=_ctx(tmp_path), args={"path": "."}))
    assert not r.is_error
    assert "root" in r.metadata
    paths = {e["path"] for e in r.metadata["entries"]}
    assert "a" in paths and "b.txt" in paths


def test_browse_oil_notification_fires_when_available(tmp_path):
    log = []
    ctx = _ctx(tmp_path, notify_log=log, plugins={"oil": True})
    _run(fs_tools.handle_browse(ctx=ctx, args={"path": "."}))
    methods = [m for m, _ in log]
    assert methods == ["integration.oil.openPath"]


def test_browse_rejects_non_dir(tmp_path):
    (tmp_path / "f.txt").write_text("f")
    r = _run(fs_tools.handle_browse(ctx=_ctx(tmp_path), args={"path": "f.txt"}))
    assert r.is_error
    assert r.metadata.get("not_a_dir") is True


def test_glob_stdlib_path_matches(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "foo.py").write_text("")
    (tmp_path / "pkg" / "bar.py").write_text("")
    (tmp_path / "README.md").write_text("")
    r = _run(fs_tools.handle_glob(ctx=_ctx(tmp_path), args={"pattern": "pkg/*.py"}))
    assert not r.is_error
    assert set(r.metadata["matches"]) == {"pkg/foo.py", "pkg/bar.py"}


def test_glob_empty():
    r = _run(fs_tools.handle_glob(ctx=_ctx("."), args={"pattern": ""}))
    assert r.is_error


def test_glob_respects_gitignore(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("ignored/\n")
    (tmp_path / "kept.py").write_text("")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "secret.py").write_text("")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    r = _run(fs_tools.handle_glob(ctx=_ctx(tmp_path), args={"pattern": "*.py"}))
    assert not r.is_error
    matches = r.metadata["matches"]
    assert "kept.py" in matches
    assert all("ignored/" not in m for m in matches)
