"""
Tests for configuration serialization and validation.
"""

import pytest

from poor_cli.config import Config, ConfigurationError, PermissionMode, SecurityConfig


class TestPermissionModeConfig:
    """Test permission mode enum serialization and parsing."""

    def test_config_to_dict_serializes_permission_mode_value(self):
        config = Config()
        config.security.permission_mode = PermissionMode.AUTO_SAFE

        data = config.to_dict()

        assert data["security"]["permission_mode"] == "auto-safe"

    def test_config_from_dict_parses_permission_mode_value(self):
        config = Config.from_dict(
            {
                "security": {
                    "permission_mode": "danger-full-access",
                }
            }
        )

        assert config.security.permission_mode == PermissionMode.DANGER_FULL_ACCESS

    def test_security_config_rejects_invalid_permission_mode(self):
        with pytest.raises(ConfigurationError, match="Invalid security.permission_mode value"):
            SecurityConfig.from_dict({"permission_mode": "never-ask"})
