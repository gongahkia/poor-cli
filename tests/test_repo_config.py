"""
Tests for repository preference serialization.
"""

import os
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from poor_cli.config import PermissionMode
from poor_cli.exceptions import ConfigurationError
from poor_cli.repo_config import ChatSession, RepoConfig, RepoPreferences


class TestRepoPreferencesPermissionMode:
    """Test repo preference permission mode parsing and serialization."""

    def test_to_dict_serializes_permission_mode(self):
        prefs = RepoPreferences(permission_mode=PermissionMode.AUTO_SAFE)

        data = prefs.to_dict()

        assert data["permission_mode"] == "auto-safe"

    def test_from_dict_parses_permission_mode(self):
        prefs = RepoPreferences.from_dict({"permission_mode": "danger-full-access"})

        assert prefs.permission_mode == PermissionMode.DANGER_FULL_ACCESS

    def test_from_dict_rejects_invalid_permission_mode(self):
        with pytest.raises(ConfigurationError, match="Invalid preferences.permission_mode value"):
            RepoPreferences.from_dict({"permission_mode": "always-allow"})

    def test_from_dict_rejects_invalid_max_sessions(self):
        with pytest.raises(ConfigurationError, match="preferences.max_sessions must be at least 1"):
            RepoPreferences.from_dict({"max_sessions": 0})

    def test_from_dict_rejects_invalid_max_messages_per_session(self):
        with pytest.raises(ConfigurationError, match="preferences.max_messages_per_session must be at least 1"):
            RepoPreferences.from_dict({"max_messages_per_session": 0})


class TestRepoConfigHistoryPersistence:
    """Test repository history persistence behavior."""

    def test_save_history_uses_atomic_replace(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        replace_calls = []
        real_replace = os.replace

        def _tracking_replace(src, dst):
            replace_calls.append((Path(src), Path(dst)))
            return real_replace(src, dst)

        monkeypatch.setattr("poor_cli.repo_config.os.replace", _tracking_replace)

        repo_config = RepoConfig(repo_path=repo_root)
        repo_config.start_session(model="test-model")
        repo_config.add_message("user", "hello")

        assert replace_calls
        source, destination = replace_calls[-1]
        assert destination == repo_config.history_file
        assert source.parent == repo_config.config_dir
        assert repo_config.history_file.exists()

    def test_history_load_and_save_take_file_lock(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        # Bootstrap files first, then track locking calls on a fresh instance.
        RepoConfig(repo_path=repo_root)

        lock_modes = []
        original_lock = RepoConfig._history_file_lock

        @contextmanager
        def _tracking_lock(self, exclusive):
            lock_modes.append(exclusive)
            with original_lock(self, exclusive):
                yield

        monkeypatch.setattr(RepoConfig, "_history_file_lock", _tracking_lock)

        repo_config = RepoConfig(repo_path=repo_root)
        repo_config.start_session(model="test-model")
        repo_config.add_message("user", "hello")

        assert False in lock_modes
        assert True in lock_modes
        assert repo_config.history_lock_file.exists()

    def test_corrupted_history_recovers_from_latest_valid_backup(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        repo_config = RepoConfig(repo_path=repo_root)
        repo_config.start_session(model="test-model")
        repo_config.add_message("user", "hello")

        backup_files = sorted(repo_config.history_backup_dir.glob("history-*.json"))
        assert backup_files
        expected_backup_payload = json.loads(backup_files[-1].read_text(encoding="utf-8"))

        # Introduce a newer invalid backup to ensure recovery skips invalid snapshots.
        invalid_backup = repo_config.history_backup_dir / "history-999999999999999999.json"
        invalid_backup.write_text("{invalid-json", encoding="utf-8")

        # Corrupt the active history file.
        repo_config.history_file.write_text("{invalid-json", encoding="utf-8")

        RepoConfig(repo_path=repo_root)
        restored_payload = json.loads(repo_config.history_file.read_text(encoding="utf-8"))
        assert restored_payload["sessions"] == expected_backup_payload["sessions"]

    def test_legacy_history_db_migrates_once_and_writes_marker(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        legacy_dir = home / ".poor-cli"
        legacy_dir.mkdir(parents=True)
        legacy_db = legacy_dir / "history.db"

        conn = sqlite3.connect(legacy_db)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    total_tokens INTEGER DEFAULT 0,
                    model TEXT DEFAULT 'gemini-2.0-flash-exp',
                    archived INTEGER DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO sessions (session_id, started_at, ended_at, model) VALUES (?, ?, ?, ?)",
                ("legacy-1", "2026-01-01T00:00:00", None, "gemini-legacy"),
            )
            cursor.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                ("legacy-1", "user", "hello from sqlite", "2026-01-01T00:00:01"),
            )
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setenv("HOME", str(home))

        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        first = RepoConfig(repo_path=repo_root)
        migrated_ids = {session.session_id for session in first.sessions}
        assert "legacy-1" in migrated_ids
        assert first.history_migration_marker_file.exists()

        conn = sqlite3.connect(legacy_db)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (session_id, started_at, ended_at, model) VALUES (?, ?, ?, ?)",
                ("legacy-2", "2026-01-02T00:00:00", None, "gemini-legacy"),
            )
            conn.commit()
        finally:
            conn.close()

        second = RepoConfig(repo_path=repo_root)
        second_ids = {session.session_id for session in second.sessions}
        assert "legacy-2" not in second_ids

    def test_legacy_history_migration_can_be_disabled(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        legacy_dir = home / ".poor-cli"
        legacy_dir.mkdir(parents=True)
        legacy_db = legacy_dir / "history.db"

        conn = sqlite3.connect(legacy_db)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    total_tokens INTEGER DEFAULT 0,
                    model TEXT DEFAULT 'gemini-2.0-flash-exp',
                    archived INTEGER DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "INSERT INTO sessions (session_id, started_at, ended_at, model) VALUES (?, ?, ?, ?)",
                ("legacy-off", "2026-01-01T00:00:00", None, "gemini-legacy"),
            )
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setenv("HOME", str(home))

        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        repo_config = RepoConfig(
            repo_path=repo_root,
            enable_legacy_history_migration=False,
        )

        assert {session.session_id for session in repo_config.sessions} == set()
        assert not repo_config.history_migration_marker_file.exists()

    def test_retention_prunes_messages_per_session_on_add(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        repo_config = RepoConfig(repo_path=repo_root)
        repo_config.preferences.max_messages_per_session = 2
        repo_config.start_session(model="test-model")
        repo_config.add_message("user", "first")
        repo_config.add_message("assistant", "second")
        repo_config.add_message("user", "third")

        contents = [msg.content for msg in repo_config.current_session.messages]
        assert contents == ["second", "third"]

    def test_retention_prunes_sessions_on_save(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        repo_config = RepoConfig(repo_path=repo_root)
        repo_config.preferences.max_sessions = 2
        repo_config.sessions = [
            ChatSession(session_id="s1", started_at="2026-01-01T00:00:00"),
            ChatSession(session_id="s2", started_at="2026-01-02T00:00:00"),
            ChatSession(session_id="s3", started_at="2026-01-03T00:00:00"),
        ]

        repo_config._save_history()

        assert [session.session_id for session in repo_config.sessions] == ["s2", "s3"]
