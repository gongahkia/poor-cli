from __future__ import annotations

import os
import re
import shlex
import shutil
from typing import Any

from .types import ModelSpec, ProviderSpec

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")


_PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        id="anthropic",
        label="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        default_model="claude-sonnet-4-20250514",
        optional_extra="anthropic",
        install_hint='uv pip install -e ".[anthropic]"',
        capabilities=("tools", "vision", "streaming", "structured_output"),
        models=(
            ModelSpec("claude-sonnet-4-20250514", "Claude Sonnet 4", ("tools", "vision", "streaming"), True),
            ModelSpec("claude-opus-4-1-20250805", "Claude Opus 4.1", ("tools", "vision", "streaming")),
            ModelSpec("claude-3-5-haiku-20241022", "Claude Haiku 3.5", ("tools", "vision", "streaming")),
        ),
    ),
    "openai": ProviderSpec(
        id="openai",
        label="OpenAI",
        env_var="OPENAI_API_KEY",
        default_model="gpt-5.5",
        optional_extra="openai",
        install_hint='uv pip install -e ".[openai]"',
        capabilities=("tools", "vision", "streaming", "structured_output", "responses_api"),
        models=(
            ModelSpec("gpt-5.5", "GPT-5.5", ("tools", "vision", "streaming", "structured_output"), True),
            ModelSpec("gpt-5.5-mini", "GPT-5.5 mini", ("tools", "vision", "streaming", "structured_output")),
            ModelSpec("gpt-4o", "GPT-4o", ("tools", "vision", "streaming")),
            ModelSpec("gpt-4o-mini", "GPT-4o mini", ("tools", "vision", "streaming")),
        ),
    ),
    "gemini": ProviderSpec(
        id="gemini",
        label="Gemini",
        env_var="GEMINI_API_KEY",
        default_model="gemini-2.5-flash",
        optional_extra="gemini",
        install_hint='uv pip install -e ".[gemini]"',
        capabilities=("tools", "vision", "streaming", "structured_output"),
        models=(
            ModelSpec("gemini-2.5-flash", "Gemini 2.5 Flash", ("tools", "vision", "streaming"), True),
            ModelSpec("gemini-2.5-pro", "Gemini 2.5 Pro", ("tools", "vision", "streaming")),
            ModelSpec("gemini-2.0-flash", "Gemini 2.0 Flash", ("tools", "vision", "streaming")),
        ),
    ),
    "ollama": ProviderSpec(
        id="ollama",
        label="Ollama",
        env_var="",
        default_model=os.environ.get("OLLAMA_MODEL", "llama3.1"),
        optional_extra="ollama",
        install_hint="brew install ollama",
        capabilities=("tools", "streaming", "local"),
        models=(
            ModelSpec(os.environ.get("OLLAMA_MODEL", "llama3.1"), "Ollama default", ("tools", "streaming", "local"), True),
        ),
        requires_api_key=False,
        base_url_env="OLLAMA_BASE_URL",
        allow_custom_models=True,
        command_name="ollama",
    ),
    "codex": ProviderSpec(
        id="codex",
        label="Codex runtime",
        env_var="",
        default_model=os.environ.get("HAUS_CODEX_MODEL", "default"),
        optional_extra="",
        install_hint="codex login, or HAUS_CODEX_OSS=1 HAUS_CODEX_LOCAL_PROVIDER=ollama",
        capabilities=("chat", "local_runtime", "text_only"),
        models=(ModelSpec(os.environ.get("HAUS_CODEX_MODEL", "default"), "Codex configured default", ("chat", "local_runtime", "text_only"), True),),
        requires_api_key=False,
        allow_custom_models=True,
        command_name="codex",
        command_env="HAUS_CODEX_CMD",
    ),
    "claude-code": ProviderSpec(
        id="claude-code",
        label="Claude Code runtime",
        env_var="",
        default_model=os.environ.get("HAUS_CLAUDE_CODE_MODEL", "default"),
        optional_extra="",
        install_hint="claude auth login",
        capabilities=("chat", "local_runtime", "text_only"),
        models=(
            ModelSpec(os.environ.get("HAUS_CLAUDE_CODE_MODEL", "default"), "Claude Code configured default", ("chat", "local_runtime", "text_only"), True),
        ),
        requires_api_key=False,
        allow_custom_models=True,
        command_name="claude",
        command_env="HAUS_CLAUDE_CODE_CMD",
    ),
    "opencode": ProviderSpec(
        id="opencode",
        label="opencode runtime",
        env_var="",
        default_model=os.environ.get("HAUS_OPENCODE_MODEL", "default"),
        optional_extra="",
        install_hint="opencode providers auth, or configure a local model in opencode",
        capabilities=("chat", "local_runtime", "text_only"),
        models=(ModelSpec(os.environ.get("HAUS_OPENCODE_MODEL", "default"), "opencode configured default", ("chat", "local_runtime", "text_only"), True),),
        requires_api_key=False,
        allow_custom_models=True,
        command_name="opencode",
        command_env="HAUS_OPENCODE_CMD",
    ),
}

DEFAULT_MODELS = {provider: spec.default_model for provider, spec in _PROVIDERS.items()}
ENV_KEYS = {provider: spec.env_var for provider, spec in _PROVIDERS.items()}


def provider_specs() -> dict[str, ProviderSpec]:
    return dict(_PROVIDERS)


def supported_provider_ids() -> list[str]:
    return list(_PROVIDERS.keys())


def providers_with_env_keys() -> list[str]:
    out: list[str] = []
    for provider, spec in _PROVIDERS.items():
        if spec.requires_api_key and spec.env_var and os.environ.get(spec.env_var):
            out.append(provider)
    return out


def _command_available(spec: ProviderSpec) -> bool | None:
    command = os.environ.get(spec.command_env, "").strip() if spec.command_env else ""
    if command:
        parts = shlex.split(command)
        return bool(parts and shutil.which(parts[0]))
    if spec.command_name:
        return shutil.which(spec.command_name) is not None
    return None


def validate_model_id(model: str) -> bool:
    return bool(_MODEL_ID_RE.fullmatch(model.strip()))


def resolve_model(provider: str, requested: str = "") -> tuple[str, bool]:
    spec = _PROVIDERS[provider]
    model = requested.strip() or spec.default_model
    if not validate_model_id(model):
        raise ValueError("Model id contains unsupported characters.")
    known = {item.id for item in spec.models}
    if model not in known and not spec.allow_custom_models:
        raise ValueError(f"Model '{model}' is not listed for {provider}.")
    return model, model not in known


def provider_status() -> dict[str, Any]:
    env_ready = set(providers_with_env_keys())
    providers: list[dict[str, Any]] = []
    for spec in _PROVIDERS.values():
        providers.append(
            {
                "id": spec.id,
                "label": spec.label,
                "env_var": spec.env_var,
                "default_model": spec.default_model,
                "optional_extra": spec.optional_extra,
                "install_hint": spec.install_hint,
                "requires_api_key": spec.requires_api_key,
                "has_env_key": spec.id in env_ready,
                "base_url_env": spec.base_url_env,
                "base_url": os.environ.get(spec.base_url_env, "http://localhost:11434") if spec.base_url_env else "",
                "command_name": spec.command_name,
                "command_env": spec.command_env,
                "command_available": _command_available(spec),
                "capabilities": list(spec.capabilities),
                "models": [
                    {
                        "id": model.id,
                        "label": model.label,
                        "default": model.default,
                        "capabilities": list(model.capabilities),
                        "notes": model.notes,
                    }
                    for model in spec.models
                ],
            }
        )
    return {
        "providers": providers,
        "supported_providers": supported_provider_ids(),
        "providers_with_env_keys": sorted(env_ready),
        "default_models": DEFAULT_MODELS,
    }
