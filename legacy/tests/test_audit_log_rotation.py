from __future__ import annotations

import gzip
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from poor_cli.audit_log import AuditLogger, AUDIT_COLUMNS


def _insert_events(logger: AuditLogger, timestamps: list[str]) -> None:
    with sqlite3.connect(logger.db_path) as conn:
        for idx, timestamp in enumerate(timestamps):
            conn.execute(
                """
                INSERT INTO audit_events
                (event_id, event_type, severity, timestamp, user, operation, target, details, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt-{idx:03d}",
                    "tool_execution",
                    "info",
                    timestamp,
                    "tester",
                    f"op-{idx}",
                    f"target-{idx}",
                    json.dumps({"idx": idx}),
                    1,
                    None,
                ),
            )


def _live_ids(logger: AuditLogger) -> list[str]:
    with sqlite3.connect(logger.db_path) as conn:
        return [row[0] for row in conn.execute("SELECT event_id FROM audit_events ORDER BY timestamp")]


def _archive_rows(logger: AuditLogger, month: str) -> list[dict]:
    path = logger.archive_dir / f"{month}.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_rotate_respects_max_rows_live(tmp_path: Path) -> None:
    logger = AuditLogger(
        audit_dir=tmp_path / ".poor-cli",
        max_rows_live=3,
        max_age_days_live=0,
        max_size_mb=0,
        archive_chunk_size=10,
    )
    _insert_events(logger, [f"2026-01-0{day}T00:00:00" for day in range(1, 6)])

    result = logger.rotate_if_needed(now=datetime(2026, 4, 12))

    assert result["archived"] == 2
    assert _live_ids(logger) == ["evt-002", "evt-003", "evt-004"]
    assert [row["event_id"] for row in _archive_rows(logger, "2026-01")] == ["evt-000", "evt-001"]


def test_rotate_respects_max_age_days_live(tmp_path: Path) -> None:
    logger = AuditLogger(
        audit_dir=tmp_path / ".poor-cli",
        max_rows_live=100,
        max_age_days_live=90,
        max_size_mb=0,
        archive_chunk_size=10,
    )
    _insert_events(logger, ["2026-01-01T00:00:00", "2026-04-01T00:00:00"])

    result = logger.rotate_if_needed(now=datetime(2026, 4, 12))

    assert result["archived"] == 1
    assert _live_ids(logger) == ["evt-001"]
    assert _archive_rows(logger, "2026-01")[0]["event_id"] == "evt-000"


def test_export_range_roundtrips_live_and_archive(tmp_path: Path) -> None:
    logger = AuditLogger(
        audit_dir=tmp_path / ".poor-cli",
        max_rows_live=1,
        max_age_days_live=0,
        max_size_mb=0,
        archive_chunk_size=10,
    )
    _insert_events(logger, ["2026-01-01T00:00:00", "2026-02-01T00:00:00", "2026-03-01T00:00:00"])
    logger.rotate_if_needed(now=datetime(2026, 4, 12))

    out = tmp_path / "audit.jsonl"
    count = logger.export_range(start_time="2026-01-01", end_time="2026-03-31", output_path=out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    assert count == 3
    assert [row["event_id"] for row in rows] == ["evt-000", "evt-001", "evt-002"]
    assert set(AUDIT_COLUMNS).issubset(rows[0].keys())


def test_archive_replay_exports_archived_rows(tmp_path: Path) -> None:
    logger = AuditLogger(
        audit_dir=tmp_path / ".poor-cli",
        max_rows_live=100,
        max_age_days_live=90,
        max_size_mb=0,
        archive_chunk_size=10,
    )
    _insert_events(logger, ["2026-01-01T00:00:00", "2026-04-11T00:00:00"])
    logger.rotate_if_needed(now=datetime(2026, 4, 12))

    rows = list(logger.iter_export_rows(start_time="2026-01-01", end_time="2026-04-12"))

    assert [row["event_id"] for row in rows] == ["evt-000", "evt-001"]
    assert _live_ids(logger) == ["evt-001"]


def test_rotation_is_atomic_on_archive_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger = AuditLogger(
        audit_dir=tmp_path / ".poor-cli",
        max_rows_live=1,
        max_age_days_live=0,
        max_size_mb=0,
        archive_chunk_size=10,
    )
    _insert_events(logger, ["2026-01-01T00:00:00", "2026-01-02T00:00:00"])

    def fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError("boom")

    monkeypatch.setattr("poor_cli.audit_log.os.replace", fail_replace)

    with pytest.raises(OSError):
        logger.rotate_if_needed(now=datetime(2026, 4, 12))

    assert _live_ids(logger) == ["evt-000", "evt-001"]
    assert not (logger.archive_dir / "2026-01.jsonl.gz").exists()
