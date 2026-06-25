"""LLM provider registry and adapters for Haus chat."""

from .registry import (
    DEFAULT_MODELS,
    ENV_KEYS,
    provider_specs,
    provider_status,
    providers_with_env_keys,
    resolve_model,
    supported_provider_ids,
    validate_model_id,
)
from .types import ChatChunk, ChatResult, ModelSpec, ProviderSpec

__all__ = [
    "ChatChunk",
    "ChatResult",
    "DEFAULT_MODELS",
    "ENV_KEYS",
    "ModelSpec",
    "ProviderSpec",
    "provider_specs",
    "provider_status",
    "providers_with_env_keys",
    "resolve_model",
    "supported_provider_ids",
    "validate_model_id",
]
