"""Provider readiness probing and routing-mode selection."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from .config import Config, ConfigManager
from .provider_catalog import common_models_for_provider
from .providers.provider_factory import ProviderFactory

ROUTING_MODES = ("manual", "quality", "speed", "cheap", "private")


@dataclass(frozen=True)
class ProviderProbeResult:
    name: str
    available: bool
    ready: bool
    configured: bool
    source: str
    status_label: str
    default_model: str
    models: List[str]
    capabilities: Dict[str, Any]
    env_var: str
    base_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "ready": self.ready,
            "configured": self.configured,
            "source": self.source,
            "statusLabel": self.status_label,
            "defaultModel": self.default_model,
            "models": list(self.models),
            "capabilities": dict(self.capabilities),
            "envVar": self.env_var,
            "baseUrl": self.base_url,
        }


def normalize_routing_mode(raw_value: Any) -> str:
    candidate = str(raw_value or "").strip().lower()
    if candidate in ROUTING_MODES:
        return candidate
    return "manual"


def select_default_routing_mode(provider_status: Dict[str, Dict[str, Any]]) -> str:
    ready = [
        name
        for name, payload in provider_status.items()
        if bool(payload.get("ready"))
    ]
    if ready == ["ollama"]:
        return "private"
    if len(ready) > 1:
        return "quality"
    return "manual"


def resolve_routing_mode(
    configured_mode: Any,
    provider_status: Dict[str, Dict[str, Any]],
) -> str:
    normalized = normalize_routing_mode(configured_mode)
    if normalized != "manual":
        return normalized
    return select_default_routing_mode(provider_status)


def probe_providers(
    config_manager: ConfigManager,
    config: Config,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    ollama_models = _discover_ollama_models(config)
    ollama_ready = bool(ollama_models.get("ready"))
    ollama_known_models = list(ollama_models.get("models", []))

    for provider_name in sorted(config.model.providers.keys()):
        provider_cfg = config.model.providers[provider_name]
        provider_info = ProviderFactory.get_provider_info(provider_name) or {}
        dependency_available = bool(provider_info.get("available", True))
        env_var = provider_cfg.api_key_env_var
        capabilities = dict(provider_info.get("capabilities") or {})

        if provider_name == "ollama":
            ready = dependency_available and ollama_ready
            configured = True
            source = "local"
            status_label = (
                "service up"
                if ready
                else f"service unavailable at {provider_cfg.base_url or 'http://localhost:11434'}"
            )
            models = (
                ollama_known_models
                if ollama_known_models
                else common_models_for_provider(provider_name)
            )
        else:
            api_key = config_manager.get_api_key(provider_name)
            configured = bool(api_key)
            ready = dependency_available and configured
            source = "environment" if api_key else "none"
            status_label = "API key configured" if ready else f"missing {env_var}"
            models = common_models_for_provider(provider_name)

        if not dependency_available:
            ready = False
            status_label = "provider dependency unavailable"

        results[provider_name] = ProviderProbeResult(
            name=provider_name,
            available=dependency_available,
            ready=ready,
            configured=configured,
            source=source,
            status_label=status_label,
            default_model=provider_cfg.default_model,
            models=models,
            capabilities=capabilities,
            env_var=env_var,
            base_url=provider_cfg.base_url,
        ).to_dict()

    return results


def _discover_ollama_models(config: Config) -> Dict[str, Any]:
    provider_cfg = config.model.providers.get("ollama")
    base_url = provider_cfg.base_url if provider_cfg else "http://localhost:11434"
    parsed = urlparse(base_url or "http://localhost:11434")
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434
    tags_url = f"{(base_url or 'http://localhost:11434').rstrip('/')}/api/tags"
    if not _is_tcp_reachable(host, port):
        return {"ready": False, "models": [], "baseUrl": base_url}

    try:
        with urlopen(tags_url, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("models") or []
        names = [
            str(model.get("name", "")).strip()
            for model in models
            if isinstance(model, dict) and str(model.get("name", "")).strip()
        ]
        return {"ready": True, "models": names, "baseUrl": base_url}
    except (OSError, URLError, ValueError):
        return {"ready": False, "models": [], "baseUrl": base_url}


def _is_tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=1.5):
            return True
    except OSError:
        return False


def summarize_ready_providers(provider_status: Dict[str, Dict[str, Any]]) -> List[str]:
    return [
        name
        for name, payload in provider_status.items()
        if bool(payload.get("ready"))
    ]


def suggested_privacy_posture(provider_status: Dict[str, Dict[str, Any]]) -> str:
    ready = summarize_ready_providers(provider_status)
    if ready == ["ollama"]:
        return "local-only"
    if "ollama" in ready:
        return "mixed"
    if any(ready):
        return "cloud"
    return "unconfigured"
