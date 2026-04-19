"""
Provider factory for creating AI provider instances

Supports dynamic provider creation and registration of custom providers.
"""

import importlib
from importlib.util import find_spec
from typing import Optional, Dict, Any, Type
from .base import BaseProvider
from .capability import ProviderCapability, capability_names, capabilities_for_provider
from ..exceptions import ConfigurationError, setup_logger

logger = setup_logger(__name__)


class ProviderFactory:
    """Factory for creating AI provider instances"""

    # Loaded provider classes (built-ins + custom registrations).
    _providers: Dict[str, Type[BaseProvider]] = {}
    _initialized = False  # compatibility flag: "built-in registry preloaded"
    _load_errors: Dict[str, str] = {}

    _provider_specs: Dict[str, tuple[str, str]] = {
        "gemini": (".gemini_provider", "GeminiProvider"),
        "openai": (".openai_provider", "OpenAIProvider"),
        "anthropic": (".anthropic_provider", "AnthropicProvider"),
        "ollama": (".ollama_provider", "OllamaProvider"),
        "hf_local": (".hf_local_provider", "HFLocalProvider"),
        "vllm": (".vllm_provider", "VLLMProvider"),
        "llama_server": (".llama_server_provider", "LlamaServerProvider"),
        "sglang": (".sglang_provider", "SGLangProvider"),
        "hf_tgi": (".hf_tgi_provider", "HFTGIProvider"),
        "lmstudio": (".lmstudio_provider", "LMStudioProvider"),
        "openrouter": (".openrouter_provider", "OpenRouterProvider"),
        "litellm": (".litellm_provider", "LiteLLMProvider"),
    }
    _provider_aliases: Dict[str, str] = {
        "claude": "anthropic",
    }
    _provider_deps: Dict[str, tuple[str, ...]] = {
        "gemini": ("google", "google.genai"),
        "openai": ("openai",),
        "anthropic": ("anthropic",),
        "ollama": ("aiohttp",),
        "hf_local": ("torch", "transformers"),
        "vllm": ("openai",),
        "llama_server": ("openai",),
        "sglang": ("openai",),
        "hf_tgi": ("openai",),
        "lmstudio": ("openai",),
        "openrouter": ("openai",),
        "litellm": ("litellm",),
    }

    @classmethod
    def _normalize_name(cls, provider_name: str) -> str:
        lowered = str(provider_name or "").strip().lower()
        return cls._provider_aliases.get(lowered, lowered)

    @classmethod
    def _dependency_available(cls, provider_name: str) -> bool:
        canonical = cls._normalize_name(provider_name)
        deps = cls._provider_deps.get(canonical)
        if not deps:
            return True
        for module_name in deps:
            try:
                if find_spec(module_name) is None:
                    return False
            except Exception:
                return False
        return True

    @classmethod
    def _load_provider_class(cls, provider_name: str) -> Optional[Type[BaseProvider]]:
        requested = str(provider_name or "").strip().lower()
        if requested in cls._providers:
            return cls._providers[requested]

        canonical = cls._normalize_name(requested)
        if canonical in cls._providers:
            provider_class = cls._providers[canonical]
            cls._providers[requested] = provider_class
            return provider_class

        spec = cls._provider_specs.get(canonical)
        if spec is None:
            return None
        module_name, class_name = spec
        try:
            module = importlib.import_module(module_name, package=__package__)
            provider_class = getattr(module, class_name)
        except ImportError as error:
            cls._load_errors[canonical] = str(error)
            logger.warning(f"{canonical} provider not available: {error}")
            return None
        except Exception as error:
            cls._load_errors[canonical] = str(error)
            logger.warning(f"{canonical} provider not available: {error}")
            return None
        if not isinstance(provider_class, type) or not issubclass(provider_class, BaseProvider):
            cls._load_errors[canonical] = f"{class_name} is not a BaseProvider subtype"
            logger.warning(f"{canonical} provider not available: invalid provider class")
            return None

        cls._providers[canonical] = provider_class
        for alias, target in cls._provider_aliases.items():
            if target == canonical:
                cls._providers[alias] = provider_class
        if requested not in cls._providers:
            cls._providers[requested] = provider_class
        return provider_class

    @classmethod
    def _initialize_providers(cls):
        if cls._initialized:
            return
        for provider_name in cls._provider_specs:
            cls._load_provider_class(provider_name)
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
        requested = str(provider_name or "").strip().lower()
        provider_class = cls._providers.get(requested)
        if provider_class is None:
            provider_class = cls._load_provider_class(requested)
        if provider_class is None:
            available = sorted(
                set(cls._providers.keys()) | set(cls._provider_specs.keys()) | set(cls._provider_aliases.keys())
            )
            raise ConfigurationError(
                f"Unknown provider: {requested}. "
                f"Available providers: {', '.join(available)}"
            )
        resolved_name = cls._normalize_name(requested)

        try:
            logger.info(f"Creating {resolved_name} provider with model {model_name}")

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

            logger.info(f"Successfully created {resolved_name} provider")
            return provider

        except Exception as e:
            logger.error(f"Failed to create {resolved_name} provider: {e}")
            raise ConfigurationError(
                f"Failed to initialize {resolved_name} provider: {str(e)}"
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
        if not getattr(provider_class, "capabilities", frozenset()):
            raise ValueError(
                f"{provider_class.__name__} must declare provider capabilities"
            )

        cls._providers[name.lower()] = provider_class
        logger.info(f"Registered custom provider: {name}")

    @classmethod
    def list_provider_names(cls, *, include_aliases: bool = True) -> list[str]:
        names = set(cls._provider_specs.keys())
        if include_aliases:
            names.update(cls._provider_aliases.keys())
        names.update(cls._providers.keys())
        return sorted(str(name) for name in names if str(name).strip())

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
        requested = str(provider_name or "").strip().lower()
        provider_class = cls._providers.get(requested)
        if provider_class is not None:
            return bool(getattr(provider_class, "available", True))
        canonical = cls._normalize_name(requested)
        provider_class = cls._providers.get(canonical)
        if provider_class is not None:
            return bool(getattr(provider_class, "available", True))
        if canonical in cls._provider_specs:
            return cls._dependency_available(canonical)
        return False

    @classmethod
    def get_provider_info(cls, provider_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a provider

        Args:
            provider_name: Name of the provider

        Returns:
            Dictionary with provider information or None if not found
        """
        requested = str(provider_name or "").strip().lower()
        canonical = cls._normalize_name(requested)

        provider_class = cls._providers.get(requested)
        if provider_class is None:
            provider_class = cls._providers.get(canonical)
        if provider_class is not None:
            declared = getattr(provider_class, "capabilities", frozenset({ProviderCapability.NONE}))
            return {
                "name": requested,
                "class": provider_class.__name__,
                "module": provider_class.__module__,
                "available": bool(getattr(provider_class, "available", True)),
                "capabilities": capability_names(declared),
            }

        spec = cls._provider_specs.get(canonical)
        if spec is None:
            return None
        module_name, class_name = spec
        declared = capabilities_for_provider(canonical) or frozenset({ProviderCapability.NONE})
        return {
            "name": requested,
            "class": class_name,
            "module": f"{__package__}{module_name}",
            "available": cls._dependency_available(canonical),
            "capabilities": capability_names(declared),
        }
