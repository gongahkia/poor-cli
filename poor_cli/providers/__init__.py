"""
AI Model Provider Abstractions

Multi-provider support for AI models including:
- Gemini (Google)
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Ollama (Local models)
"""

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, FunctionCall
from .tool_translator import ToolTranslator, ProviderType
from .provider_factory import ProviderFactory

# Provider implementations (imported lazily by factory to avoid missing dependencies)
from .gemini_provider import GeminiProvider

__all__ = [
    # Base classes
    "BaseProvider",
    "ProviderCapabilities",
    "ProviderResponse",
    "FunctionCall",

    # Utilities
    "ToolTranslator",
    "ProviderType",
    "ProviderFactory",

    # Providers (available for direct import)
    "GeminiProvider",
]
