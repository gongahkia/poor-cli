"""Tests for poor_cli.tool_health (T9)."""

from __future__ import annotations

import time

import pytest

from poor_cli.tool_dispatcher import CallRecord
from poor_cli.tool_health import ToolHealth


@pytest.fixture
def health():
    return ToolHealth()


def test_records_success_and_failure(health):
    health.record(CallRecord(tool="git.status", wall_time_ms=10, returncode=0))
    health.record(CallRecord(tool="git.status", wall_time_ms=20, returncode=1, is_error=True))
    snap = health.snapshot("git.status")
    assert snap["successes"] == 1
    assert snap["failures"] == 1
    assert snap["success_rate"] == 0.5


def test_percentiles(health):
    for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        health.record(CallRecord(tool="x", wall_time_ms=ms, returncode=0))
    snap = health.snapshot("x")
    assert snap["p50_ms"] in (50, 60)  # inclusive bounds
    assert snap["p95_ms"] in (90, 100)


def test_recent_errors_capped_at_5(health):
    for i in range(10):
        health.record(
            CallRecord(tool="y", wall_time_ms=1, returncode=1, is_error=True),
            error_excerpt=f"err-{i}",
        )
    snap = health.snapshot("y")
    assert len(snap["recent_errors"]) == 5
    # The last-in excerpts
    assert snap["recent_errors"][-1]["excerpt"] == "err-9"


def test_window_success_rate_ignores_old_events(health):
    # Old success
    health.record(CallRecord(tool="z", wall_time_ms=1, returncode=0))
    # Simulate old event by mutating timestamps to far past
    stats = health._tools["z"]
    stats.events[0] = time.time() - 4000
    # Fresh failure
    health.record(CallRecord(tool="z", wall_time_ms=1, returncode=1, is_error=True))
    stats.recent_errors[-1]["at"] = time.time()
    snap = health.snapshot("z", window_s=1800.0)
    assert snap["window_total"] == 1
    assert snap["window_success_rate"] == 0.0


def test_snapshots_returns_one_per_tool(health):
    health.record(CallRecord(tool="a", wall_time_ms=1, returncode=0))
    health.record(CallRecord(tool="b", wall_time_ms=1, returncode=0))
    snaps = health.snapshots()
    names = {s["name"] for s in snaps}
    assert names == {"a", "b"}


def test_unknown_tool_returns_none(health):
    assert health.snapshot("never.called") is None


def test_reset_clears(health):
    health.record(CallRecord(tool="a", wall_time_ms=1, returncode=0))
    health.reset()
    assert health.tool_names() == []


def test_recent_consecutive_failures_counts_tail_only(health):
    health.record(CallRecord(tool="c", wall_time_ms=1, returncode=1, is_error=True))
    health.record(CallRecord(tool="c", wall_time_ms=1, returncode=1, is_error=True))
    health.record(CallRecord(tool="c", wall_time_ms=1, returncode=0, is_error=False))
    health.record(CallRecord(tool="c", wall_time_ms=1, returncode=1, is_error=True))
    assert health.recent_consecutive_failures("c", window_s=60.0) == 1
