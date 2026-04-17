"""Tests for poor_cli.session_recorder (Proposal D.1)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from poor_cli.session_recorder import RecordedCall, SessionRecorder
from poor_cli.tool_blocks import ToolResult
from poor_cli.tool_dispatcher import CallRecord, dispatch_one
from poor_cli.tools import _registry


def _fake_record(tool: str, *, is_error=False, timeout=False, degraded=None,
                 wall_time_ms=5, retry_attempts=1):
    return CallRecord(
        tool=tool, wall_time_ms=wall_time_ms, returncode=1 if is_error else 0,
        retry_attempts=retry_attempts, degraded=degraded, timeout=timeout,
        is_error=is_error,
    )


# ──────────────── SessionRecorder unit tests ────────────────


def test_record_appends_to_ring_buffer():
    r = SessionRecorder()
    r.record(_fake_record("git.status"))
    r.record(_fake_record("fs.browse"))
    assert len(r.records) == 2
    assert [c.tool for c in r.records] == ["git.status", "fs.browse"]


def test_record_respects_max_records_ring_buffer():
    r = SessionRecorder(max_records=3)
    for i in range(10):
        r.record(_fake_record(f"t.{i}"))
    assert len(r.records) == 3
    # ring preserves newest
    assert [c.tool for c in r.records] == ["t.7", "t.8", "t.9"]


def test_outcome_categorisation():
    r = SessionRecorder()
    r.record(_fake_record("ok"))
    r.record(_fake_record("err", is_error=True))
    r.record(_fake_record("timeout", is_error=True, timeout=True))
    r.record(_fake_record("degraded", degraded="cli"))
    outcomes = [c.outcome for c in r.records]
    assert outcomes == ["ok", "err", "timeout", "degraded"]


def test_recent_returns_last_n():
    r = SessionRecorder()
    for i in range(5):
        r.record(_fake_record(f"t.{i}"))
    last2 = r.recent(n=2)
    assert [c.tool for c in last2] == ["t.3", "t.4"]


def test_recent_filters_by_tool_name():
    r = SessionRecorder()
    r.record(_fake_record("git.status"))
    r.record(_fake_record("fs.browse"))
    r.record(_fake_record("git.status"))
    only_git = r.recent(n=10, tool_filter="git.status")
    assert len(only_git) == 2
    assert all(c.tool == "git.status" for c in only_git)


def test_file_writes_empty_for_non_mutating_tools():
    r = SessionRecorder()
    r.record(_fake_record("git.status"), {})
    r.record(_fake_record("fs.browse"), {"path": "."})
    assert r.file_writes() == []


def test_file_writes_tracks_mutating_tool_paths():
    r = SessionRecorder()
    r.record(_fake_record("git.stage"), {"paths": ["a.py", "b.py"]})
    r.record(_fake_record("hunks.stage"), {"file": "c.py"})
    rows = r.file_writes()
    paths = {row["path"] for row in rows}
    assert paths == {"a.py", "b.py", "c.py"}
    # first_touched_by records the tool that mentioned the path first
    a_row = next(row for row in rows if row["path"] == "a.py")
    assert a_row["first_touched_by"] == "git.stage"
    assert a_row["touches"] == 1


def test_file_writes_increments_touches_on_repeat():
    r = SessionRecorder()
    r.record(_fake_record("git.stage"), {"paths": ["a.py"]})
    r.record(_fake_record("git.stage"), {"paths": ["a.py"]})
    r.record(_fake_record("git.unstage"), {"paths": ["a.py"]})
    rows = {row["path"]: row for row in r.file_writes()}
    assert rows["a.py"]["touches"] == 3
    assert rows["a.py"]["first_touched_by"] == "git.stage"  # first, not latest


def test_file_writes_skipped_when_tool_errored():
    r = SessionRecorder()
    r.record(_fake_record("git.stage", is_error=True), {"paths": ["a.py"]})
    assert r.file_writes() == []


def test_reset_clears_state():
    r = SessionRecorder()
    r.record(_fake_record("git.stage"), {"paths": ["a.py"]})
    r.reset()
    assert len(r.records) == 0
    assert r.file_writes() == []


def test_recorders_are_independent():
    a = SessionRecorder()
    b = SessionRecorder()
    a.record(_fake_record("t"))
    assert len(a.records) == 1
    assert len(b.records) == 0


# ──────────────── dispatcher integration ────────────────


def _register_throwaway(name: str, handler):
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=handler,
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


def test_dispatcher_pushes_into_recorder_when_present():
    recorder = SessionRecorder()
    ctx = SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        session_recorder=recorder,
    )

    async def handler(*, ctx, args):
        return ToolResult.text("done")

    _register_throwaway("rec.t", handler)
    asyncio.run(dispatch_one("rec.t", {"x": 1}, ctx=ctx))
    assert len(recorder.records) == 1
    assert recorder.records[0].tool == "rec.t"
    assert recorder.records[0].args == {"x": 1}


def test_dispatcher_noop_when_ctx_has_no_recorder():
    ctx = SimpleNamespace(
        cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None,
    )

    async def handler(*, ctx, args):
        return ToolResult.text("done")

    _register_throwaway("rec.t2", handler)
    # Dispatch must not raise when recorder is absent.
    result, rec = asyncio.run(dispatch_one("rec.t2", {}, ctx=ctx))
    assert not result.is_error


def test_dispatcher_records_errors_too():
    recorder = SessionRecorder()
    ctx = SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        session_recorder=recorder,
    )

    async def handler(*, ctx, args):
        return ToolResult.error("nope")

    _register_throwaway("rec.err", handler)
    asyncio.run(dispatch_one("rec.err", {}, ctx=ctx))
    assert len(recorder.records) == 1
    assert recorder.records[0].outcome == "err"
