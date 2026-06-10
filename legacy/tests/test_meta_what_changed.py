"""Tests for meta.what_changed (Proposal D.6)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.session_recorder import SessionRecorder
from poor_cli.tool_blocks import TableBlock, TextBlock
from poor_cli.tool_dispatcher import CallRecord
import poor_cli.tools  # trigger registrations  # noqa: F401
from poor_cli.tools.meta import handle_what_changed


def _fake(tool, *, is_error=False):
    return CallRecord(
        tool=tool, wall_time_ms=5, returncode=1 if is_error else 0, is_error=is_error,
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


def test_no_recorder_returns_text():
    result = _run(handle_what_changed(ctx=_ctx(None), args={}))
    assert not result.is_error
    assert "no session_recorder" in result.content[0].text


def test_empty_session_returns_text():
    recorder = SessionRecorder()
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    assert not result.is_error
    assert "no files touched" in result.content[0].text


def test_non_mutating_tools_contribute_nothing():
    recorder = SessionRecorder()
    recorder.record(_fake("git.status"), {})
    recorder.record(_fake("fs.browse"), {"path": "."})
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    assert "no files touched" in result.content[0].text


def test_mutating_tools_populate_table():
    recorder = SessionRecorder()
    recorder.record(_fake("git.stage"), {"paths": ["a.py", "b.py"]})
    recorder.record(_fake("hunks.stage"), {"file": "c.py"})
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert tables
    paths = {row[0] for row in tables[0].rows}
    assert paths == {"a.py", "b.py", "c.py"}


def test_first_touched_by_records_first_tool():
    recorder = SessionRecorder()
    recorder.record(_fake("git.stage"), {"paths": ["x.py"]})
    recorder.record(_fake("hunks.stage"), {"file": "x.py"})
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    row = next(r for r in tables[0].rows if r[0] == "x.py")
    assert row[1] == "git.stage"  # first, not latest


def test_touches_count_reflects_repeats():
    recorder = SessionRecorder()
    recorder.record(_fake("git.stage"), {"paths": ["a.py"]})
    recorder.record(_fake("git.stage"), {"paths": ["a.py"]})
    recorder.record(_fake("git.unstage"), {"paths": ["a.py"]})
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    row = tables[0].rows[0]
    assert row[2] == "3"


def test_rows_stable_sorted_by_path():
    recorder = SessionRecorder()
    recorder.record(_fake("git.stage"), {"paths": ["zzz.py", "aaa.py", "mmm.py"]})
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    paths = [row[0] for row in tables[0].rows]
    assert paths == sorted(paths)


def test_errored_mutations_excluded():
    recorder = SessionRecorder()
    recorder.record(_fake("git.stage", is_error=True), {"paths": ["oops.py"]})
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    assert "no files touched" in result.content[0].text


def test_metadata_reports_counts():
    recorder = SessionRecorder()
    recorder.record(_fake("git.stage"), {"paths": ["a.py", "b.py"]})
    recorder.record(_fake("git.status"), {})  # non-mutating
    result = _run(handle_what_changed(ctx=_ctx(recorder), args={}))
    assert result.metadata["files_touched"] == 2
    assert result.metadata["session_total_calls"] == 2
