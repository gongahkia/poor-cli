"""
Tests for configuration management
"""

import pytest
import tempfile
from pathlib import Path
from poor_cli.config import Config, ConfigManager, ModelConfig, HistoryConfig


class TestConfig:
    """Test configuration dataclasses"""

    def test_default_config(self):
        """Test default configuration values"""
        config = Config()

        assert config.model.provider == "gemini"
        assert config.model.temperature == 0.7
        assert config.history.max_turns == 50
        assert config.ui.enable_streaming == True
        assert config.security.require_permission_for_write == True

    def test_config_to_dict(self):
        """Test config serialization to dict"""
        config = Config()
        config_dict = config.to_dict()

        assert "model" in config_dict
        assert "history" in config_dict
        assert "ui" in config_dict
        assert "security" in config_dict
        assert "tools" in config_dict
        assert "api_keys" not in config_dict  # Should not be serialized

    def test_config_from_dict(self):
        """Test config deserialization from dict"""
        config_dict = {
            "model": {"provider": "openai", "model_name": "gpt-4", "temperature": 0.5},
            "history": {"max_turns": 100},
            "ui": {"enable_streaming": False},
            "security": {"require_permission_for_write": False},
            "tools": {"enable_git_tools": True}
        }

        config = Config.from_dict(config_dict)

        assert config.model.provider == "openai"
        assert config.model.model_name == "gpt-4"
        assert config.model.temperature == 0.5
        assert config.history.max_turns == 100
        assert config.ui.enable_streaming == False


class TestConfigManager:
    """Test configuration manager"""

    def test_create_default_config(self):
        """Test creating default configuration"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            manager = ConfigManager(config_path)

            # Should create default config
            manager.save()
            assert config_path.exists()

    def test_load_config(self):
        """Test loading configuration from file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            manager = ConfigManager(config_path)

            # Create and save config
            manager.config.model.temperature = 0.9
            manager.save()

            # Load in new manager
            manager2 = ConfigManager(config_path)
            manager2.load()

            assert manager2.config.model.temperature == 0.9

    def test_get_config_value(self):
        """Test getting config values by path"""
        manager = ConfigManager()
        manager.config.model.temperature = 0.8

        assert manager.get("model.temperature") == 0.8
        assert manager.get("invalid.path", "default") == "default"

    def test_set_config_value(self):
        """Test setting config values by path"""
        manager = ConfigManager()

        manager.set("model.temperature", 0.6)
        assert manager.config.model.temperature == 0.6

        with pytest.raises(Exception):
            manager.set("invalid.path", "value")

    def test_validate_config(self):
        """Test configuration validation"""
        manager = ConfigManager()

        # Valid config
        assert manager.validate() == True

        # Invalid temperature
        manager.config.model.temperature = 3.0
        with pytest.raises(Exception):
            manager.validate()

        # Reset
        manager.config.model.temperature = 0.7

        # Invalid max_turns
        manager.config.history.max_turns = 0
        with pytest.raises(Exception):
            manager.validate()

    def test_get_api_key(self):
        """Test API key retrieval"""
        import os

        # Test env variable
        os.environ["GEMINI_API_KEY"] = "test_key_123"
        manager = ConfigManager()

        assert manager.get_api_key("gemini") == "test_key_123"

        # Clean up
        del os.environ["GEMINI_API_KEY"]

    def test_display_config(self):
        """Test config display formatting"""
        manager = ConfigManager()
        display = manager.display_config()

        assert "model:" in display
        assert "history:" in display
        assert "ui:" in display
        assert isinstance(display, str)
