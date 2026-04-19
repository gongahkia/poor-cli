"""AI provider abstractions with lazy provider-class exports."""

from __future__ import annotations

from importlib import import_module

from .base import BaseProvider, FunctionCall, ProviderCapabilities, ProviderResponse, UsageMetadata
from .capability import ProviderCapability
from .provider_factory import ProviderFactory
from .tool_translator import ProviderType, ToolTranslator

_PROVIDER_EXPORTS = {
    "GeminiProvider": ".gemini_provider",
    "HFLocalProvider": ".hf_local_provider",
    "HFTGIProvider": ".hf_tgi_provider",
    "LlamaServerProvider": ".llama_server_provider",
    "LMStudioProvider": ".lmstudio_provider",
    "SGLangProvider": ".sglang_provider",
    "VLLMProvider": ".vllm_provider",
}

__all__ = [
    "BaseProvider",
    "ProviderCapabilities",
    "ProviderCapability",
    "ProviderResponse",
    "FunctionCall",
    "UsageMetadata",
    "ToolTranslator",
    "ProviderType",
    "ProviderFactory",
    *sorted(_PROVIDER_EXPORTS.keys()),
]


def __getattr__(name: str):
    module_name = _PROVIDER_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    module = import_module(module_name, package=__name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
