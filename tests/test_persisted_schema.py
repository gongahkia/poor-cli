"""Tests for the persisted-state envelope and SQLite meta helpers (PRD 003)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from poor_cli.persisted import (
    CURRENT_VERSIONS,
    UnknownSchemaVersion,
    load_json,
    read_sqlite_version,
    run_sqlite_migrations,
    save_json,
    seed_sqlite_meta,
)


def test_envelope_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    payload = {"theme": "dark", "active_provider": "openai"}

    save_json(path, "preferences", payload)

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == CURRENT_VERSIONS["preferences"]
    assert on_disk["artifact"] == "preferences"
    assert on_disk["data"] == payload

    loaded = load_json(path, "preferences")
    assert loaded == payload


def test_save_json_rejects_unknown_artifact(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_json(tmp_path / "x.json", "not-a-real-artifact", {})


def test_unknown_version_refuses_to_load(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 9999,
                "artifact": "preferences",
                "data": {"theme": "dark"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(UnknownSchemaVersion):
        load_json(path, "preferences")


def test_load_json_missing_returns_default(tmp_path: Path) -> None:
    sentinel = {"seeded": True}
    assert load_json(tmp_path / "nope.json", "preferences", default=sentinel) is sentinel
    assert load_json(tmp_path / "nope.json", "preferences") is None


def test_sqlite_meta_table_seeded(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    conn = sqlite3.connect(db_path)
    try:
        seed_sqlite_meta(conn, "audit")
        conn.commit()

        cur = conn.execute("SELECT key, value FROM meta ORDER BY key")
        rows = dict(cur.fetchall())
        assert rows["schema_version"] == str(CURRENT_VERSIONS["audit"])
        assert rows["artifact"] == "audit"
        assert read_sqlite_version(conn) == CURRENT_VERSIONS["audit"]
    finally:
        conn.close()


def test_seed_sqlite_meta_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    conn = sqlite3.connect(db_path)
    try:
        seed_sqlite_meta(conn, "audit")
        seed_sqlite_meta(conn, "audit")
        conn.commit()
        rows = conn.execute("SELECT COUNT(*) FROM meta").fetchone()
        assert rows[0] == 2  # schema_version + artifact, not duplicated
    finally:
        conn.close()


def test_run_sqlite_migrations_seeds_fresh_db(tmp_path: Path) -> None:
    db_path = tmp_path / "runs.db"
    conn = sqlite3.connect(db_path)
    try:
        run_sqlite_migrations(conn, "runs")
        assert read_sqlite_version(conn) == CURRENT_VERSIONS["runs"]
    finally:
        conn.close()


def test_sqlite_newer_version_rejected(tmp_path: Path) -> None:
    from poor_cli.persisted.schema import set_sqlite_version

    db_path = tmp_path / "audit.db"
    conn = sqlite3.connect(db_path)
    try:
        seed_sqlite_meta(conn, "audit")
        set_sqlite_version(conn, CURRENT_VERSIONS["audit"] + 99)
        conn.commit()
        with pytest.raises(UnknownSchemaVersion):
            run_sqlite_migrations(conn, "audit")
    finally:
        conn.close()
