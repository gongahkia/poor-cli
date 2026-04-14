"""Provider-declared feature capabilities."""

from __future__ import annotations

from enum import Flag, auto
from typing import Any, Iterable


class ProviderCapability(Flag):
    NONE = 0
    STREAMING = auto()
    TOOL_CALLING = auto()
    SYSTEM_INSTRUCTIONS = auto()
    JSON_MODE = auto()
    VISION = auto()
    PROMPT_CACHING_PREFIX = auto()
    PROMPT_CACHING_BLOCK = auto()
    EXTENDED_THINKING = auto()
    GROUNDING = auto()
    LATENT_COMMUNICATION = auto()


_ORDERED_CAPABILITIES = tuple(
    cap for cap in ProviderCapability if cap is not ProviderCapability.NONE
)

PROVIDER_CAPABILITIES: dict[str, frozenset[ProviderCapability]] = {
    "gemini": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
            ProviderCapability.JSON_MODE,
            ProviderCapability.VISION,
        }
    ),
    "openai": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
            ProviderCapability.JSON_MODE,
            ProviderCapability.VISION,
        }
    ),
    "anthropic": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
            ProviderCapability.VISION,
            ProviderCapability.PROMPT_CACHING_PREFIX,
            ProviderCapability.PROMPT_CACHING_BLOCK,
            ProviderCapability.EXTENDED_THINKING,
        }
    ),
    "openrouter": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
            ProviderCapability.JSON_MODE,
            ProviderCapability.VISION,
        }
    ),
    "ollama": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
            ProviderCapability.JSON_MODE,
        }
    ),
    "hf_local": frozenset(
        {
            ProviderCapability.SYSTEM_INSTRUCTIONS,
            ProviderCapability.LATENT_COMMUNICATION,
        }
    ),
    "vllm": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
        }
    ),
    "llama_server": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
        }
    ),
    "sglang": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
        }
    ),
    "hf_tgi": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
        }
    ),
    "lmstudio": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
        }
    ),
    # litellm routes to 100+ backends; conservative declaration, streaming +
    # tool calling are supported by major targets (openai, anthropic, vertex,
    # cohere, mistral). Model-specific gaps surface at call time via fallback.
    "litellm": frozenset(
        {
            ProviderCapability.STREAMING,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
            ProviderCapability.JSON_MODE,
            ProviderCapability.VISION,
        }
    ),
}


def capabilities_for_provider(provider_name: str) -> frozenset[ProviderCapability]:
    return PROVIDER_CAPABILITIES.get(str(provider_name).strip().lower(), frozenset())


def capability_names(capabilities: Iterable[ProviderCapability]) -> list[str]:
    declared = frozenset(capabilities)
    return [cap.name.lower() for cap in _ORDERED_CAPABILITIES if cap in declared]


def provider_has_capability(provider: Any, capability: ProviderCapability) -> bool:
    declared = getattr(provider, "capabilities", None)
    if declared is not None:
        return capability in declared
    get_capabilities = getattr(provider, "get_capabilities", None)
    if not callable(get_capabilities):
        return False
    runtime = get_capabilities()
    if capability is ProviderCapability.STREAMING:
        return bool(getattr(runtime, "supports_streaming", False))
    if capability is ProviderCapability.TOOL_CALLING:
        return bool(getattr(runtime, "supports_function_calling", False))
    if capability is ProviderCapability.SYSTEM_INSTRUCTIONS:
        return bool(getattr(runtime, "supports_system_instructions", False))
    if capability is ProviderCapability.JSON_MODE:
        return bool(getattr(runtime, "supports_json_mode", False))
    if capability is ProviderCapability.VISION:
        return bool(getattr(runtime, "supports_vision", False))
    if capability is ProviderCapability.EXTENDED_THINKING:
        return bool(getattr(runtime, "supports_thinking", False))
    if capability is ProviderCapability.LATENT_COMMUNICATION:
        return bool(getattr(runtime, "supports_latent_communication", False))
    return False
