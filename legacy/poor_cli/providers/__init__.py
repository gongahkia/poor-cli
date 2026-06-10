"""AI provider abstractions with fully lazy exports."""

from __future__ import annotations

from importlib import import_module

_EXPORT_MAP = {
    "BaseProvider": ".base",
    "FunctionCall": ".base",
    "ProviderCapabilities": ".base",
    "ProviderResponse": ".base",
    "UsageMetadata": ".base",
    "ProviderCapability": ".capability",
    "ProviderFactory": ".provider_factory",
    "ProviderType": ".tool_translator",
    "ToolTranslator": ".tool_translator",
    "GeminiProvider": ".gemini_provider",
    "HFLocalProvider": ".hf_local_provider",
    "HFTGIProvider": ".hf_tgi_provider",
    "LlamaServerProvider": ".llama_server_provider",
    "LMStudioProvider": ".lmstudio_provider",
    "SGLangProvider": ".sglang_provider",
    "VLLMProvider": ".vllm_provider",
}

__all__ = sorted(_EXPORT_MAP.keys())


def __getattr__(name: str):
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    module = import_module(module_name, package=__name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
