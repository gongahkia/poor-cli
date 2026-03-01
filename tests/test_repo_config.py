"""
Tests for repository preference serialization.
"""

import os
from pathlib import Path

import pytest

from poor_cli.config import PermissionMode
from poor_cli.exceptions import ConfigurationError
from poor_cli.repo_config import RepoConfig, RepoPreferences


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
