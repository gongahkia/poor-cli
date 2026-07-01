from __future__ import annotations

import os
import re
import shlex
import shutil
from typing import Any

from .types import ModelSpec, ProviderSpec

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
_WEBLLM_DEFAULT_MODEL = os.environ.get("HAUS_WEBLLM_MODEL", "Llama-3.1-8B-Instruct-q4f32_1-MLC")
_WEBLLM_MODELS = (
    ModelSpec("SmolLM2-360M-Instruct-q4f32_1-MLC", "SmolLM2 360M", ("chat", "browser_runtime", "webgpu"), notes="~580MB VRAM; smallest practical chat option."),
    ModelSpec("TinyLlama-1.1B-Chat-v1.0-q4f32_1-MLC", "TinyLlama 1.1B", ("chat", "browser_runtime", "webgpu"), notes="~840MB VRAM; low-resource browser model."),
    ModelSpec("Llama-3.2-1B-Instruct-q4f16_1-MLC", "Llama 3.2 1B", ("chat", "browser_runtime", "webgpu"), notes="~879MB VRAM; low-resource instruction model."),
    ModelSpec("Qwen2.5-1.5B-Instruct-q4f16_1-MLC", "Qwen2.5 1.5B", ("chat", "browser_runtime", "webgpu"), notes="~1.6GB VRAM; low-resource instruction model."),
    ModelSpec("SmolLM2-1.7B-Instruct-q4f32_1-MLC", "SmolLM2 1.7B", ("chat", "browser_runtime", "webgpu"), notes="~2.7GB VRAM; stronger small model."),
    ModelSpec("Llama-3.2-3B-Instruct-q4f16_1-MLC", "Llama 3.2 3B", ("chat", "browser_runtime", "webgpu"), notes="~2.3GB VRAM; balanced browser model."),
    ModelSpec("Hermes-3-Llama-3.2-3B-q4f16_1-MLC", "Hermes 3 Llama 3.2 3B", ("chat", "browser_runtime", "webgpu"), notes="~2.3GB VRAM; tool-oriented prompt following."),
    ModelSpec("Phi-3.5-mini-instruct-q4f16_1-MLC", "Phi 3.5 mini", ("chat", "browser_runtime", "webgpu"), notes="~3.7GB VRAM; compact reasoning model."),
    ModelSpec("Hermes-2-Pro-Llama-3-8B-q4f32_1-MLC", "Hermes 2 Pro Llama 3 8B", ("chat", "tools", "browser_runtime", "webgpu"), notes="~6.1GB VRAM; WebLLM native tool-call model."),
    ModelSpec("Hermes-3-Llama-3.1-8B-q4f32_1-MLC", "Hermes 3 Llama 3.1 8B", ("chat", "tools", "browser_runtime", "webgpu"), notes="~5.8GB VRAM; WebLLM native tool-call model."),
    ModelSpec("Llama-3.1-8B-Instruct-q4f32_1-MLC", "Llama 3.1 8B", ("chat", "browser_runtime", "webgpu"), _WEBLLM_DEFAULT_MODEL == "Llama-3.1-8B-Instruct-q4f32_1-MLC", notes="~6.1GB VRAM; default JSON-tool fallback model."),
)
if _WEBLLM_DEFAULT_MODEL not in {model.id for model in _WEBLLM_MODELS}:
    _WEBLLM_MODELS = (
        ModelSpec(_WEBLLM_DEFAULT_MODEL, "WebLLM configured default", ("chat", "browser_runtime", "webgpu"), True),
        *_WEBLLM_MODELS,
    )


_PROVIDERS: dict[str, ProviderSpec] = {
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
        capabilities=("chat", "tools", "local_runtime"),
        models=(ModelSpec(os.environ.get("HAUS_CODEX_MODEL", "default"), "Codex configured default", ("chat", "tools", "local_runtime"), True),),
        requires_api_key=False,
        allow_custom_models=True,
        command_name="codex",
        command_env="HAUS_CODEX_CMD",
    ),
    "gemini-cli": ProviderSpec(
        id="gemini-cli",
        label="Gemini CLI runtime",
        env_var="",
        default_model=os.environ.get("HAUS_GEMINI_CLI_MODEL", "default"),
        optional_extra="",
        install_hint="gemini auth login",
        capabilities=("chat", "tools", "local_runtime"),
        models=(ModelSpec(os.environ.get("HAUS_GEMINI_CLI_MODEL", "default"), "Gemini CLI configured default", ("chat", "tools", "local_runtime"), True),),
        requires_api_key=False,
        allow_custom_models=True,
        command_name="gemini",
        command_env="HAUS_GEMINI_CLI_CMD",
    ),
    "claude-code": ProviderSpec(
        id="claude-code",
        label="Claude Code runtime",
        env_var="",
        default_model=os.environ.get("HAUS_CLAUDE_CODE_MODEL", "default"),
        optional_extra="",
        install_hint="claude auth login",
        capabilities=("chat", "tools", "local_runtime"),
        models=(
            ModelSpec(os.environ.get("HAUS_CLAUDE_CODE_MODEL", "default"), "Claude Code configured default", ("chat", "tools", "local_runtime"), True),
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
        capabilities=("chat", "tools", "local_runtime"),
        models=(ModelSpec(os.environ.get("HAUS_OPENCODE_MODEL", "default"), "opencode configured default", ("chat", "tools", "local_runtime"), True),),
        requires_api_key=False,
        allow_custom_models=True,
        command_name="opencode",
        command_env="HAUS_OPENCODE_CMD",
    ),
    "aider": ProviderSpec(
        id="aider",
        label="Aider runtime",
        env_var="",
        default_model=os.environ.get("HAUS_AIDER_MODEL", "default"),
        optional_extra="",
        install_hint="pipx install aider-chat, then configure aider auth/model",
        capabilities=("chat", "tools", "local_runtime"),
        models=(ModelSpec(os.environ.get("HAUS_AIDER_MODEL", "default"), "Aider configured default", ("chat", "tools", "local_runtime"), True),),
        requires_api_key=False,
        allow_custom_models=True,
        command_name="aider",
        command_env="HAUS_AIDER_CMD",
    ),
    "openai-compatible-local": ProviderSpec(
        id="openai-compatible-local",
        label="OpenAI-compatible local",
        env_var="",
        default_model=os.environ.get("HAUS_OPENAI_COMPAT_MODEL", "local-model"),
        optional_extra="",
        install_hint="Start LM Studio, llama.cpp server, vLLM, or LocalAI with an OpenAI-compatible /v1 endpoint.",
        capabilities=("tools", "local", "openai_compatible"),
        models=(ModelSpec(os.environ.get("HAUS_OPENAI_COMPAT_MODEL", "local-model"), "Configured local model", ("tools", "local", "openai_compatible"), True),),
        requires_api_key=False,
        base_url_env="HAUS_OPENAI_COMPAT_BASE_URL",
        allow_custom_models=True,
    ),
    "webllm": ProviderSpec(
        id="webllm",
        label="WebLLM",
        env_var="",
        default_model=_WEBLLM_DEFAULT_MODEL,
        optional_extra="",
        install_hint="Use a WebGPU-capable browser; the model downloads into browser cache on first use.",
        capabilities=("chat", "tools", "browser_runtime", "webgpu"),
        models=_WEBLLM_MODELS,
        requires_api_key=False,
        allow_custom_models=True,
    ),
}

_AGENT_RUNTIME_PROVIDER_IDS = ("codex", "gemini-cli", "claude-code", "opencode", "aider")


def _agent_runtimes_enabled() -> bool:
    return os.environ.get("HAUS_ENABLE_AGENT_RUNTIMES", "").strip().lower() in {"1", "true", "yes", "on"}


if not _agent_runtimes_enabled():
    for provider_id in _AGENT_RUNTIME_PROVIDER_IDS:
        _PROVIDERS.pop(provider_id, None)

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
        default_base_url = "http://localhost:1234/v1" if spec.id == "openai-compatible-local" else "http://localhost:11434"
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
                "base_url": os.environ.get(spec.base_url_env, default_base_url) if spec.base_url_env else "",
                "command_name": spec.command_name,
                "command_env": spec.command_env,
                "command_available": _command_available(spec),
                "allow_custom_models": spec.allow_custom_models,
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
