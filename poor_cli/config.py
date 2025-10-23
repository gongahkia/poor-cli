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
class ProviderConfig:
    """Configuration for a specific provider"""
    name: str  # Provider name
    api_key_env_var: str  # Environment variable for API key
    default_model: str  # Default model to use
    enabled: bool = True  # Whether provider is available
    base_url: Optional[str] = None  # For providers like Ollama


@dataclass
class ModelConfig:
    """Configuration for AI model settings"""
    provider: str = "gemini"  # Active provider: gemini, openai, anthropic, ollama
    model_name: str = "gemini-2.0-flash-exp"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 0.95
    top_k: int = 40

    # Provider registry
    providers: Dict[str, ProviderConfig] = field(default_factory=lambda: {
        "gemini": ProviderConfig(
            name="gemini",
            api_key_env_var="GEMINI_API_KEY",
            default_model="gemini-2.0-flash-exp"
        ),
        "openai": ProviderConfig(
            name="openai",
            api_key_env_var="OPENAI_API_KEY",
            default_model="gpt-4-turbo"
        ),
        "anthropic": ProviderConfig(
            name="anthropic",
            api_key_env_var="ANTHROPIC_API_KEY",
            default_model="claude-3-5-sonnet-20241022"
        ),
        "ollama": ProviderConfig(
            name="ollama",
            api_key_env_var="OLLAMA_API_KEY",  # Usually not needed
            default_model="llama3",
            base_url="http://localhost:11434"
        ),
    })


@dataclass
class HistoryConfig:
    """Configuration for conversation history"""
    max_turns: int = 50
    auto_save: bool = True
    save_directory: str = "~/.poor-cli/history"
    max_token_limit: int = 100000  # Context window limit

    # History restoration settings
    restore_on_startup: bool = True  # Load previous session on startup
    max_messages_to_restore: int = 20  # How many messages to restore from previous session
    continue_last_session: bool = True  # Continue last session or start new one


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
class PlanModeConfig:
    """Configuration for plan mode"""
    enabled: bool = True  # Enable plan mode by default
    auto_plan_threshold: int = 2  # Auto-enable plan for operations affecting N+ files
    require_approval_for_high_risk: bool = True
    show_diff_in_plan: bool = True
    allow_step_modification: bool = True
    default_context_lines: int = 3  # Lines of context in diffs


@dataclass
class CheckpointConfig:
    """Configuration for checkpoint system"""
    enabled: bool = True  # Enable automatic checkpoints
    auto_checkpoint_before_write: bool = True
    auto_checkpoint_before_edit: bool = True
    auto_checkpoint_before_delete: bool = True
    max_checkpoints: int = 50  # Maximum checkpoints to keep
    checkpoint_on_session_start: bool = False  # Create checkpoint at start
    checkpoint_on_session_end: bool = False  # Create checkpoint at end


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
    plan_mode: PlanModeConfig = field(default_factory=PlanModeConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)

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
            "plan_mode": asdict(self.plan_mode),
            "checkpoint": asdict(self.checkpoint),
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
            plan_mode=PlanModeConfig(**data.get("plan_mode", {})),
            checkpoint=CheckpointConfig(**data.get("checkpoint", {})),
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
            provider: Provider name (gemini, openai, anthropic, claude, ollama)

        Returns:
            API key or None
        """
        provider = provider.lower()

        # Handle claude as alias for anthropic
        if provider == "claude":
            provider = "anthropic"

        # Get provider config
        provider_config = self.config.model.providers.get(provider)
        if not provider_config:
            logger.warning(f"Unknown provider: {provider}")
            return None

        # Check environment variable first
        env_var = provider_config.api_key_env_var
        api_key = os.getenv(env_var)
        if api_key:
            return api_key

        # Check config api_keys dict (backward compatibility)
        if hasattr(self.config, 'api_keys'):
            return self.config.api_keys.get(provider)

        return None

    def get_provider_config(self, provider: str) -> Optional['ProviderConfig']:
        """Get configuration for a specific provider

        Args:
            provider: Provider name

        Returns:
            ProviderConfig or None
        """
        provider = provider.lower()
        if provider == "claude":
            provider = "anthropic"

        return self.config.model.providers.get(provider)

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
