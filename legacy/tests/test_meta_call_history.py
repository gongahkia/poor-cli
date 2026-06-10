"""Tests for meta.call_history (Proposal D.4)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.session_recorder import SessionRecorder
from poor_cli.tool_blocks import TableBlock, TextBlock, ToolResult
from poor_cli.tool_dispatcher import CallRecord
import poor_cli.tools  # trigger registrations  # noqa: F401
from poor_cli.tools.meta import handle_call_history


def _fake(tool, *, is_error=False, timeout=False, degraded=None, wall_time_ms=5,
          retry_attempts=1):
    return CallRecord(
        tool=tool, wall_time_ms=wall_time_ms, returncode=1 if is_error else 0,
        retry_attempts=retry_attempts, degraded=degraded, timeout=timeout,
        is_error=is_error,
    )


def _ctx(recorder=None):
    return SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        session_recorder=recorder,
    )


def _run(coro):
    return asyncio.run(coro)


def test_history_with_no_recorder_returns_text():
    result = _run(handle_call_history(ctx=_ctx(None), args={}))
    # Not registered as error — informational text explaining absence.
    assert not result.is_error
    assert "no session_recorder" in result.content[0].text


def test_empty_session_returns_text():
    recorder = SessionRecorder()
    result = _run(handle_call_history(ctx=_ctx(recorder), args={}))
    assert "no tool calls this session" in result.content[0].text


def test_returns_table_with_recent_calls():
    recorder = SessionRecorder()
    recorder.record(_fake("git.status"))
    recorder.record(_fake("fs.browse"))
    recorder.record(_fake("git.commit", wall_time_ms=42, retry_attempts=2))
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"n": 10}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert tables
    assert tables[0].columns == ["tool", "outcome", "wall_ms", "retries", "ago"]
    names = [row[0] for row in tables[0].rows]
    assert names == ["git.status", "fs.browse", "git.commit"]
    # Wall-time and retries round-trip
    commit_row = tables[0].rows[2]
    assert commit_row[2] == "42"
    assert commit_row[3] == "2"


def test_tool_filter_exact_match():
    recorder = SessionRecorder()
    recorder.record(_fake("git.status"))
    recorder.record(_fake("git.status"))
    recorder.record(_fake("fs.browse"))
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"tool": "git.status"}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert [row[0] for row in tables[0].rows] == ["git.status", "git.status"]


def test_tool_filter_with_no_matches():
    recorder = SessionRecorder()
    recorder.record(_fake("git.status"))
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"tool": "never.called"}))
    assert "no calls to tool 'never.called'" in result.content[0].text


def test_n_limit_respected():
    recorder = SessionRecorder()
    for i in range(15):
        recorder.record(_fake(f"t.{i}"))
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"n": 3}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert len(tables[0].rows) == 3
    assert [row[0] for row in tables[0].rows] == ["t.12", "t.13", "t.14"]


def test_outcomes_differentiated():
    recorder = SessionRecorder()
    recorder.record(_fake("ok"))
    recorder.record(_fake("err", is_error=True))
    recorder.record(_fake("timeout", is_error=True, timeout=True))
    recorder.record(_fake("degraded", degraded="cli"))
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"n": 10}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    outcomes = [row[1] for row in tables[0].rows]
    assert outcomes == ["ok", "err", "timeout", "degraded"]


def test_metadata_reports_counts():
    recorder = SessionRecorder()
    for i in range(7):
        recorder.record(_fake(f"t.{i}"))
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"n": 3}))
    assert result.metadata["returned"] == 3
    assert result.metadata["session_total"] == 7


def test_invalid_n_type_errors():
    recorder = SessionRecorder()
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"n": "many"}))
    assert result.is_error


def test_invalid_tool_type_errors():
    recorder = SessionRecorder()
    result = _run(handle_call_history(ctx=_ctx(recorder), args={"tool": 42}))
    assert result.is_error
