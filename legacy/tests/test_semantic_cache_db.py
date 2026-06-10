from __future__ import annotations

import sqlite3
from pathlib import Path

from poor_cli.semantic_cache import SemanticCache


def test_semantic_cache_falls_back_to_tmp_db_path(monkeypatch, tmp_path):
    expected_fallback = tmp_path / "poor-cli" / "cache" / "semantic_cache.db"
    monkeypatch.setattr("poor_cli.semantic_cache.tempfile.gettempdir", lambda: str(tmp_path))

    real_connect = sqlite3.connect
    calls = {"count": 0}

    def _fake_connect(path, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("primary path denied")
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr("poor_cli.semantic_cache.sqlite3.connect", _fake_connect)

    cache = SemanticCache(db_path=tmp_path / "restricted" / "semantic_cache.db")
    assert cache._db is not None
    assert Path(cache.db_path) == expected_fallback
    cache.close()


def test_semantic_cache_applies_sqlite_pragmas(tmp_path):
    cache = SemanticCache(db_path=tmp_path / "semantic_cache.db")
    assert cache._db is not None

    conn = cache._db
    journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    sync_mode = int(conn.execute("PRAGMA synchronous").fetchone()[0])
    busy_timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])

    assert journal_mode == "wal"
    assert sync_mode in (1, 2)
    assert busy_timeout >= 5000
    cache.close()
