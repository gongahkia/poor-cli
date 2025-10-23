"""
Provider factory for creating AI provider instances

Supports dynamic provider creation and registration of custom providers.
"""

from typing import Optional, Dict, Any, Type
from .base import BaseProvider
from ..exceptions import ConfigurationError, setup_logger

logger = setup_logger(__name__)


class ProviderFactory:
    """Factory for creating AI provider instances"""

    # Registry of available providers
    # Will be populated lazily to avoid import errors if dependencies are missing
    _providers: Dict[str, Type[BaseProvider]] = {}
    _initialized = False

    @classmethod
    def _initialize_providers(cls):
        """
        Initialize provider registry

        This is done lazily to avoid import errors for optional dependencies
        """
        if cls._initialized:
            return

        # Try to import each provider, but don't fail if dependencies are missing
        try:
            from .gemini_provider import GeminiProvider
            cls._providers["gemini"] = GeminiProvider
            logger.debug("Registered Gemini provider")
        except ImportError as e:
            logger.warning(f"Gemini provider not available: {e}")

        try:
            from .openai_provider import OpenAIProvider
            cls._providers["openai"] = OpenAIProvider
            logger.debug("Registered OpenAI provider")
        except ImportError as e:
            logger.warning(f"OpenAI provider not available: {e}")

        try:
            from .anthropic_provider import AnthropicProvider
            cls._providers["anthropic"] = AnthropicProvider
            cls._providers["claude"] = AnthropicProvider  # Alias
            logger.debug("Registered Anthropic provider")
        except ImportError as e:
            logger.warning(f"Anthropic provider not available: {e}")

        try:
            from .ollama_provider import OllamaProvider
            cls._providers["ollama"] = OllamaProvider
            logger.debug("Registered Ollama provider")
        except ImportError as e:
            logger.warning(f"Ollama provider not available: {e}")

        cls._initialized = True

    @classmethod
    def create(
        cls,
        provider_name: str,
        api_key: str,
        model_name: str,
        **kwargs
    ) -> BaseProvider:
        """
        Create a provider instance

        Args:
            provider_name: Provider type (gemini, openai, anthropic, ollama)
            api_key: API key for the provider
            model_name: Model to use
            **kwargs: Additional provider-specific configuration
                - max_retries: Maximum number of retries (default: 3)
                - retry_delay: Initial retry delay in seconds (default: 1.0)
                - timeout: Request timeout in seconds (default: 60.0)

        Returns:
            Initialized provider instance

        Raises:
            ConfigurationError: If provider is unknown or initialization fails
        """
        # Initialize provider registry if needed
        cls._initialize_providers()

        provider_name = provider_name.lower()

        if provider_name not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ConfigurationError(
                f"Unknown provider: {provider_name}. "
                f"Available providers: {available}"
            )

        provider_class = cls._providers[provider_name]

        try:
            logger.info(f"Creating {provider_name} provider with model {model_name}")

            # Extract common parameters
            max_retries = kwargs.pop("max_retries", 3)
            retry_delay = kwargs.pop("retry_delay", 1.0)
            timeout = kwargs.pop("timeout", 60.0)

            # Create provider instance
            provider = provider_class(
                api_key=api_key,
                model_name=model_name,
                max_retries=max_retries,
                retry_delay=retry_delay,
                timeout=timeout,
                **kwargs
            )

            logger.info(f"Successfully created {provider_name} provider")
            return provider

        except Exception as e:
            logger.error(f"Failed to create {provider_name} provider: {e}")
            raise ConfigurationError(
                f"Failed to initialize {provider_name} provider: {str(e)}"
            )

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BaseProvider]):
        """
        Register a custom provider (for plugins/extensions)

        This allows users to add their own provider implementations.

        Args:
            name: Provider name (e.g., "custom", "local")
            provider_class: Provider class (must inherit from BaseProvider)

        Raises:
            ValueError: If provider_class doesn't inherit from BaseProvider
        """
        if not issubclass(provider_class, BaseProvider):
            raise ValueError(
                f"{provider_class.__name__} must inherit from BaseProvider"
            )

        cls._providers[name.lower()] = provider_class
        logger.info(f"Registered custom provider: {name}")

    @classmethod
    def list_providers(cls) -> Dict[str, Type[BaseProvider]]:
        """
        Get all registered providers

        Returns:
            Dictionary mapping provider names to provider classes
        """
        cls._initialize_providers()
        return cls._providers.copy()

    @classmethod
    def is_provider_available(cls, provider_name: str) -> bool:
        """
        Check if a provider is available

        Args:
            provider_name: Name of the provider to check

        Returns:
            True if provider is available, False otherwise
        """
        cls._initialize_providers()
        return provider_name.lower() in cls._providers

    @classmethod
    def get_provider_info(cls, provider_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a provider

        Args:
            provider_name: Name of the provider

        Returns:
            Dictionary with provider information or None if not found
        """
        cls._initialize_providers()

        provider_name = provider_name.lower()
        if provider_name not in cls._providers:
            return None

        provider_class = cls._providers[provider_name]

        return {
            "name": provider_name,
            "class": provider_class.__name__,
            "module": provider_class.__module__,
            "available": True
        }
