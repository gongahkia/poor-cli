"""
Tests for configuration serialization and validation.
"""

from pathlib import Path

import pytest

from poor_cli.config import (
    Config,
    ConfigManager,
    ConfigurationError,
    PermissionMode,
    SecurityConfig,
)


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


class TestAdditionalConfigFeatures:
    def test_config_roundtrip_includes_mcp_servers(self):
        config = Config()
        config.mcp_servers = {
            "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]},
        }

        data = config.to_dict()
        loaded = Config.from_dict(data)

        assert "mcp_servers" in data
        assert loaded.mcp_servers["filesystem"]["command"] == "npx"

    def test_repo_overrides_are_applied_when_present(self, tmp_path, monkeypatch):
        config_file = tmp_path / "global-config.yaml"
        config_file.write_text(
            "ui:\n"
            "  show_token_count: true\n"
            "model:\n"
            "  provider: gemini\n",
            encoding="utf-8",
        )

        repo_cfg_dir = tmp_path / ".poor-cli"
        repo_cfg_dir.mkdir(parents=True)
        (repo_cfg_dir / "config.yaml").write_text(
            "ui:\n"
            "  show_token_count: false\n"
            "mcp_servers:\n"
            "  demo:\n"
            "    command: demo-mcp\n",
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)
        manager = ConfigManager(config_path=Path(config_file))
        loaded = manager.load()

        assert loaded.ui.show_token_count is False
        assert loaded.mcp_servers["demo"]["command"] == "demo-mcp"

    def test_get_api_key_falls_back_to_secure_store(self, monkeypatch, tmp_path):
        manager = ConfigManager(config_path=tmp_path / "config.yaml")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        manager.config.api_keys.clear()
        monkeypatch.setattr("poor_cli.config.Path.home", lambda: tmp_path)
        secure_store_file = tmp_path / ".poor-cli" / "keys" / "encrypted_keys.json"
        secure_store_file.parent.mkdir(parents=True, exist_ok=True)
        secure_store_file.write_text("{}", encoding="utf-8")

        class _FakeKeyStore:
            @staticmethod
            def get_key(provider: str):
                return "secure-gemini-key" if provider == "gemini" else None

        monkeypatch.setattr(
            "poor_cli.api_key_manager.get_api_key_manager",
            lambda: _FakeKeyStore(),
        )

        assert manager.get_api_key("gemini") == "secure-gemini-key"
