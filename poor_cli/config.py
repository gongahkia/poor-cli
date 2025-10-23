"""
Configuration management for poor-cli

Handles loading, saving, and validating user configuration from YAML files.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from poor_cli.exceptions import ConfigurationError, setup_logger

logger = setup_logger(__name__)


@dataclass
class ModelConfig:
    """Configuration for AI model settings"""
    provider: str = "gemini"  # gemini, openai, claude, ollama
    model_name: str = "gemini-2.0-flash-exp"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 0.95
    top_k: int = 40


@dataclass
class HistoryConfig:
    """Configuration for conversation history"""
    max_turns: int = 50
    auto_save: bool = True
    save_directory: str = "~/.poor-cli/history"
    max_token_limit: int = 100000  # Context window limit


@dataclass
class UIConfig:
    """Configuration for user interface"""
    theme: str = "default"  # default, dark, light, minimal
    show_token_count: bool = True
    enable_streaming: bool = True
    markdown_rendering: bool = True
    show_tool_calls: bool = True
    verbose_logging: bool = False  # Show INFO/DEBUG logs in console


@dataclass
class SecurityConfig:
    """Configuration for security settings"""
    safe_commands: list = field(default_factory=lambda: [
        "pwd", "ls", "echo", "cat", "head", "tail",
        "grep", "find", "which", "whoami", "date"
    ])
    require_permission_for_write: bool = True
    require_permission_for_bash: bool = True
    enable_bash_execution: bool = True
    max_file_size_mb: int = 100
    allowed_file_extensions: list = field(default_factory=lambda: [])  # Empty = all allowed


@dataclass
class ToolConfig:
    """Configuration for tool behavior"""
    enable_git_tools: bool = True
    enable_file_tools: bool = True
    enable_network_tools: bool = True
    backup_before_edit: bool = True
    git_auto_detect: bool = True


@dataclass
class Config:
    """Main configuration class"""
    model: ModelConfig = field(default_factory=ModelConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)

    # API keys stored separately (not in config file)
    api_keys: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary, excluding API keys"""
        config_dict = {
            "model": asdict(self.model),
            "history": asdict(self.history),
            "ui": asdict(self.ui),
            "security": asdict(self.security),
            "tools": asdict(self.tools),
        }
        return config_dict

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create config from dictionary"""
        return cls(
            model=ModelConfig(**data.get("model", {})),
            history=HistoryConfig(**data.get("history", {})),
            ui=UIConfig(**data.get("ui", {})),
            security=SecurityConfig(**data.get("security", {})),
            tools=ToolConfig(**data.get("tools", {})),
        )


class ConfigManager:
    """Manages configuration loading, saving, and validation"""

    DEFAULT_CONFIG_DIR = Path.home() / ".poor-cli"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize config manager

        Args:
            config_path: Path to config file (defaults to ~/.poor-cli/config.yaml)
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_FILE
        self.config: Config = Config()

    def load(self) -> Config:
        """Load configuration from file

        Returns:
            Config object

        Raises:
            ConfigurationError: If config file is invalid
        """
        try:
            if not self.config_path.exists():
                logger.info(f"Config file not found at {self.config_path}, using defaults")
                self._create_default_config()
                return self.config

            logger.info(f"Loading configuration from {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data is None:
                logger.warning("Config file is empty, using defaults")
                return self.config

            self.config = Config.from_dict(data)

            # Expand paths
            self.config.history.save_directory = str(
                Path(self.config.history.save_directory).expanduser()
            )

            logger.info("Configuration loaded successfully")
            return self.config

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load config: {e}")

    def save(self, config: Optional[Config] = None) -> None:
        """Save configuration to file

        Args:
            config: Config object to save (uses current if None)

        Raises:
            ConfigurationError: If saving fails
        """
        try:
            if config:
                self.config = config

            # Create config directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict and save
            config_dict = self.config.to_dict()

            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Configuration saved to {self.config_path}")

        except Exception as e:
            raise ConfigurationError(f"Failed to save config: {e}")

    def _create_default_config(self) -> None:
        """Create default configuration file"""
        try:
            logger.info("Creating default configuration file")
            self.save()
            logger.info(f"Default config created at {self.config_path}")
        except Exception as e:
            logger.warning(f"Failed to create default config: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation path

        Args:
            key_path: Dot-separated path (e.g., "model.temperature")
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        try:
            keys = key_path.split('.')
            value = self.config

            for key in keys:
                if hasattr(value, key):
                    value = getattr(value, key)
                else:
                    return default

            return value

        except Exception:
            return default

    def set(self, key_path: str, value: Any) -> None:
        """Set configuration value by dot-notation path

        Args:
            key_path: Dot-separated path (e.g., "model.temperature")
            value: Value to set

        Raises:
            ConfigurationError: If path is invalid
        """
        try:
            keys = key_path.split('.')
            obj = self.config

            # Navigate to parent object
            for key in keys[:-1]:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    raise ConfigurationError(f"Invalid config path: {key_path}")

            # Set the final value
            final_key = keys[-1]
            if hasattr(obj, final_key):
                setattr(obj, final_key, value)
            else:
                raise ConfigurationError(f"Invalid config key: {final_key}")

        except Exception as e:
            raise ConfigurationError(f"Failed to set config value: {e}")

    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults"""
        self.config = Config()
        logger.info("Configuration reset to defaults")

    def validate(self) -> bool:
        """Validate current configuration

        Returns:
            True if valid

        Raises:
            ConfigurationError: If validation fails
        """
        # Validate model config
        if self.config.model.temperature < 0 or self.config.model.temperature > 2:
            raise ConfigurationError("Temperature must be between 0 and 2")

        if self.config.model.top_p < 0 or self.config.model.top_p > 1:
            raise ConfigurationError("top_p must be between 0 and 1")

        # Validate history config
        if self.config.history.max_turns < 1:
            raise ConfigurationError("max_turns must be at least 1")

        # Validate security config
        if self.config.security.max_file_size_mb < 1:
            raise ConfigurationError("max_file_size_mb must be at least 1")

        logger.info("Configuration validated successfully")
        return True

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for provider from environment or config

        Args:
            provider: Provider name (gemini, openai, claude, ollama)

        Returns:
            API key or None
        """
        # Check environment variables first
        env_key_map = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "ollama": "OLLAMA_API_KEY",
        }

        env_var = env_key_map.get(provider.lower())
        if env_var and os.getenv(env_var):
            return os.getenv(env_var)

        # Check config
        return self.config.api_keys.get(provider.lower())

    def display_config(self) -> str:
        """Get formatted configuration display

        Returns:
            Formatted config string
        """
        config_dict = self.config.to_dict()
        return yaml.dump(config_dict, default_flow_style=False, sort_keys=False)


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


def get_config() -> Config:
    """Get current configuration"""
    return get_config_manager().config
