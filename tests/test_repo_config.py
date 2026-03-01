"""
Tests for repository preference serialization.
"""

import pytest

from poor_cli.config import PermissionMode
from poor_cli.exceptions import ConfigurationError
from poor_cli.repo_config import RepoPreferences


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
