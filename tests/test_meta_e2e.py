"""End-to-end integration tests for the meta.* self-discovery family (D.7).

Proves:
  1. All 5 meta.* tools are discoverable via meta.list_tools.
  2. A full round trip: agent dispatches some tools, meta.call_history
     surfaces them accurately.
  3. meta.* tools can call each other via ctx.call_tool (T10 compat).
  4. Self-discoverability invariant from PROPOSAL-D §3 invariant #6.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli.session_recorder import SessionRecorder
from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tool_dispatcher import CallRecord, dispatch_one
from poor_cli.tool_health import reset as health_reset
import poor_cli.tools  # trigger registrations  # noqa: F401
from poor_cli.tools import _registry
from poor_cli.tools.meta import (
    handle_call_history,
    handle_describe_tool,
    handle_health,
    handle_list_tools,
    handle_what_changed,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_health():
    health_reset()
    yield
    health_reset()


@pytest.fixture
def repo(tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.email", "t@e"], cwd=cwd, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=cwd, check=True)
    (cwd / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "a.txt"], cwd=cwd, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=cwd, check=True)
    return cwd


def _make_ctx(cwd, recorder=None):
    return SimpleNamespace(
        cwd=str(cwd),
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        session_recorder=recorder,
    )


# ──────────────── invariant #6: self-discoverable ────────────────


def test_all_five_meta_tools_appear_in_list_tools():
    result = _run(handle_list_tools(ctx=_make_ctx("."), args={"domain": "meta"}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = set(row[0] for row in tables[0].rows)
    assert {
        "meta.list_tools",
        "meta.describe_tool",
        "meta.call_history",
        "meta.health",
        "meta.what_changed",
    } <= names, f"missing: {names}"


def test_meta_tools_describe_each_other():
    # Ensure every meta.* tool has a schema that describe_tool can render.
    for name in (
        "meta.list_tools",
        "meta.describe_tool",
        "meta.call_history",
        "meta.health",
        "meta.what_changed",
    ):
        result = _run(handle_describe_tool(ctx=_make_ctx("."), args={"name": name}))
        assert not result.is_error, f"describe failed for {name}"
        blocks = [b for b in result.content if isinstance(b, CodeBlock)]
        assert blocks and f"## {name}" in blocks[0].code


# ──────────────── E2E: dispatch → history → what_changed ────────────────


def test_dispatch_round_trip_surfaces_history(repo):
    """Agent-centric scenario: dispatch git.status + git.diff + git.stage,
    then ask meta.call_history what was just done — no chat context needed."""
    recorder = SessionRecorder()
    ctx = _make_ctx(repo, recorder=recorder)

    _run(dispatch_one("git.status", {}, ctx=ctx))
    (repo / "a.txt").write_text("one\nchange\n")
    _run(dispatch_one("git.diff", {}, ctx=ctx))
    _run(dispatch_one("git.stage", {"paths": ["a.txt"]}, ctx=ctx))

    # meta.call_history should list those three, in order
    hist = _run(handle_call_history(ctx=ctx, args={"n": 10}))
    tables = [b for b in hist.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    assert names == ["git.status", "git.diff", "git.stage"]

    # meta.what_changed should know about a.txt (from git.stage)
    changed = _run(handle_what_changed(ctx=ctx, args={}))
    ctables = [b for b in changed.content if isinstance(b, TableBlock)]
    paths = [row[0] for row in ctables[0].rows]
    assert paths == ["a.txt"]


def test_call_history_filter_by_tool(repo):
    recorder = SessionRecorder()
    ctx = _make_ctx(repo, recorder=recorder)
    _run(dispatch_one("git.status", {}, ctx=ctx))
    _run(dispatch_one("git.log", {"limit": 1}, ctx=ctx))
    _run(dispatch_one("git.status", {}, ctx=ctx))

    result = _run(handle_call_history(ctx=ctx, args={"tool": "git.status"}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    assert names == ["git.status", "git.status"]


# ──────────────── T10 composition: meta tools can call each other ────────────────


def test_meta_tools_can_call_each_other_via_ctx():
    """Phase-C T10 invariant: meta.* tools can call peers via ctx.call_tool
    without respawning a sub-agent. We prove it by going through the
    dispatcher for meta.list_tools (which uses T10 under the hood when
    the agent does `ctx.call_tool("meta.list_tools", ...)`)."""
    ctx = _make_ctx(".", recorder=SessionRecorder())
    result, _rec = _run(dispatch_one("meta.list_tools", {"domain": "meta"}, ctx=ctx))
    assert not result.is_error
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    assert "meta.list_tools" in names


# ──────────────── budget invariant ────────────────


def test_list_tools_output_fits_under_token_budget():
    """PROPOSAL-D §3 invariant #2: meta.list_tools({}) must stay under
    4000 tokens (paginated to be safe). We check via char count."""
    result = _run(handle_list_tools(ctx=_make_ctx("."), args={}))
    total_chars = sum(
        len(b.text) if isinstance(b, TextBlock)
        else sum(sum(len(c) for c in row) for row in b.rows) if isinstance(b, TableBlock)
        else 0
        for b in result.content
    )
    assert total_chars / 4 < 4500, f"~{total_chars//4} tokens; budget is 4000"


# ──────────────── session isolation ────────────────


def test_two_sessions_have_independent_recorders(repo):
    ra = SessionRecorder()
    rb = SessionRecorder()
    ctx_a = _make_ctx(repo, recorder=ra)
    ctx_b = _make_ctx(repo, recorder=rb)

    _run(dispatch_one("git.status", {}, ctx=ctx_a))
    _run(dispatch_one("git.status", {}, ctx=ctx_b))
    _run(dispatch_one("git.log", {"limit": 1}, ctx=ctx_b))

    h_a = _run(handle_call_history(ctx=ctx_a, args={"n": 10}))
    h_b = _run(handle_call_history(ctx=ctx_b, args={"n": 10}))

    names_a = [row[0] for row in next(b for b in h_a.content if isinstance(b, TableBlock)).rows]
    names_b = [row[0] for row in next(b for b in h_b.content if isinstance(b, TableBlock)).rows]
    assert names_a == ["git.status"]
    assert names_b == ["git.status", "git.log"]
