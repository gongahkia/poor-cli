"""
AI Model Provider Abstractions

Multi-provider support for AI models including:
- Gemini (Google)
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Ollama (Local models)
"""

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, FunctionCall, UsageMetadata
from .capability import ProviderCapability
from .tool_translator import ToolTranslator, ProviderType
from .provider_factory import ProviderFactory

# Provider implementations (imported lazily by factory to avoid missing dependencies)
from .gemini_provider import GeminiProvider
from .hf_local_provider import HFLocalProvider
from .hf_tgi_provider import HFTGIProvider
from .llama_server_provider import LlamaServerProvider
from .lmstudio_provider import LMStudioProvider
from .sglang_provider import SGLangProvider
from .vllm_provider import VLLMProvider

__all__ = [
    # Base classes
    "BaseProvider",
    "ProviderCapabilities",
    "ProviderCapability",
    "ProviderResponse",
    "FunctionCall",
    "UsageMetadata",

    # Utilities
    "ToolTranslator",
    "ProviderType",
    "ProviderFactory",

    # Providers (available for direct import)
    "GeminiProvider",
    "HFLocalProvider",
    "HFTGIProvider",
    "LlamaServerProvider",
    "LMStudioProvider",
    "SGLangProvider",
    "VLLMProvider",
]
