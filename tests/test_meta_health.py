"""Tests for meta.health (Proposal D.5)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tool_dispatcher import CallRecord
from poor_cli.tool_health import record, reset as health_reset, ToolHealth
import poor_cli.tools  # trigger registrations  # noqa: F401
from poor_cli.tools.meta import handle_health


def _ctx():
    return SimpleNamespace(cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None)


def _run(coro):
    return asyncio.run(coro)


def _fake(tool, *, is_error=False, wall_time_ms=10):
    return CallRecord(
        tool=tool, wall_time_ms=wall_time_ms, returncode=1 if is_error else 0,
        is_error=is_error,
    )


@pytest.fixture(autouse=True)
def _reset_health():
    health_reset()
    yield
    health_reset()


def test_health_empty_returns_text():
    result = _run(handle_health(ctx=_ctx(), args={}))
    assert not result.is_error
    assert "no tool-health data" in result.content[0].text


def test_single_tool_snapshot():
    for _ in range(5):
        record(_fake("git.status"))
    record(_fake("git.status", is_error=True))
    result = _run(handle_health(ctx=_ctx(), args={"tool": "git.status"}))
    assert not result.is_error
    blocks = [b for b in result.content if isinstance(b, CodeBlock)]
    assert blocks
    text = blocks[0].code
    assert "git.status" in text
    assert "total: 6" in text
    assert "successes=5" in text
    assert "failures=1" in text


def test_single_tool_unknown_returns_text():
    result = _run(handle_health(ctx=_ctx(), args={"tool": "never.dispatched"}))
    assert not result.is_error
    assert "no health data" in result.content[0].text


def test_summary_table_lists_every_recorded_tool():
    record(_fake("git.status"))
    record(_fake("fs.browse"))
    record(_fake("git.commit"))
    result = _run(handle_health(ctx=_ctx(), args={}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert tables
    names = [row[0] for row in tables[0].rows]
    assert set(names) == {"git.status", "fs.browse", "git.commit"}
    assert names == sorted(names)  # alpha order (deterministic)


def test_summary_reports_success_and_p50():
    for ms in [10, 20, 30, 40, 50]:
        record(_fake("fs.glob", wall_time_ms=ms))
    result = _run(handle_health(ctx=_ctx(), args={}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    row = next(r for r in tables[0].rows if r[0] == "fs.glob")
    # success=100% because no errors
    assert row[2] == "100%"
    # p50 is either 30 or 20 depending on rounding; check it's present
    assert row[4] in ("20ms", "30ms", "40ms")


def test_window_s_clamp():
    record(_fake("git.status"))
    result = _run(handle_health(ctx=_ctx(), args={"window_s": 999999}))
    assert result.metadata["window_s"] == 86400


def test_window_s_invalid_type_errors():
    result = _run(handle_health(ctx=_ctx(), args={"window_s": "forever"}))
    assert result.is_error


def test_tool_name_invalid_type_errors():
    result = _run(handle_health(ctx=_ctx(), args={"tool": 42}))
    assert result.is_error


def test_metadata_exposes_raw_snapshot_for_single_tool():
    for _ in range(3):
        record(_fake("git.log"))
    result = _run(handle_health(ctx=_ctx(), args={"tool": "git.log"}))
    # meta.health returns the full raw snapshot in metadata so the agent
    # can reason over fields without re-parsing the CodeBlock text.
    assert result.metadata["name"] == "git.log"
    assert result.metadata["successes"] == 3
