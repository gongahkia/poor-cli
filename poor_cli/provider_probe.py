"""Provider readiness probing and routing-mode selection."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from .config import Config, ConfigManager
from .provider_catalog import KEYLESS_LOCAL_PROVIDER_NAMES, common_models_for_provider
from .providers.provider_factory import ProviderFactory

ROUTING_MODES = ("manual", "quality", "speed", "cheap", "private")
KEYLESS_LOCAL_PROVIDERS = KEYLESS_LOCAL_PROVIDER_NAMES
LOCAL_OPENAI_COMPATIBLE_PROVIDERS = (
    "vllm",
    "llama_server",
    "sglang",
    "hf_tgi",
    "lmstudio",
)
_PROBE_CACHE_FRESH_TTL_SECONDS = 10.0
_PROBE_CACHE_STALE_TTL_SECONDS = 120.0


def _float_env(name: str, default: float) -> float:
    raw = str(os.environ.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on", "all"}


_TCP_CONNECT_TIMEOUT_SECONDS = max(0.05, _float_env("POORCLI_PROVIDER_PROBE_TCP_TIMEOUT_S", 0.35))
_HTTP_PROBE_TIMEOUT_SECONDS = max(0.10, _float_env("POORCLI_PROVIDER_PROBE_HTTP_TIMEOUT_S", 1.20))
_probe_cache_at = 0.0
_probe_cache_signature = ""
_probe_cache_result: Optional[Dict[str, Dict[str, Any]]] = None
_probe_cache_refreshing = False
_probe_cache_lock = threading.Lock()


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
    if ready and set(ready).issubset(KEYLESS_LOCAL_PROVIDERS):
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
    *,
    allow_stale: bool = True,
    background_refresh: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Dict[str, Any]]:
    signature = json.dumps({
        name: {
            "default_model": provider_cfg.default_model,
            "base_url": provider_cfg.base_url,
            "env_var": provider_cfg.api_key_env_var,
        }
        for name, provider_cfg in sorted(config.model.providers.items())
    }, sort_keys=True)
    now = time.monotonic()
    if not force_refresh:
        cached = _copy_probe_cache(signature)
        if cached is not None:
            age = now - _probe_cache_at
            if age <= _PROBE_CACHE_FRESH_TTL_SECONDS:
                return cached
            if allow_stale and age <= _PROBE_CACHE_STALE_TTL_SECONDS:
                if background_refresh:
                    _refresh_probe_cache_async(config_manager, config, signature)
                return cached

    results = _compute_probe_results(config_manager, config)
    _store_probe_cache(signature, results, now=now)
    return {name: dict(payload) for name, payload in results.items()}


def _compute_probe_results(
    config_manager: ConfigManager,
    config: Config,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    ollama_models, local_openai_models = _probe_local_providers(config)
    ollama_ready = bool(ollama_models.get("ready"))
    ollama_known_models = list(ollama_models.get("models", []))

    for provider_name in sorted(config.model.providers.keys()):
        provider_cfg = config.model.providers[provider_name]
        provider_info = ProviderFactory.get_provider_info(provider_name) or {}
        dependency_available = bool(provider_info.get("available", True))
        env_var = provider_cfg.api_key_env_var
        raw_capabilities = provider_info.get("capabilities") or {}
        if isinstance(raw_capabilities, dict):
            capabilities = dict(raw_capabilities)
        else:
            capabilities = {str(capability): True for capability in raw_capabilities}

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
        elif provider_name == "hf_local":
            configured = True
            ready = dependency_available
            source = "local"
            status_label = "local dependencies available" if ready else "provider dependency unavailable"
            models = common_models_for_provider(provider_name)
        elif provider_name in local_openai_models:
            probe = local_openai_models[provider_name]
            ready = dependency_available and bool(probe.get("ready"))
            configured = True
            source = "local"
            status_label = (
                "service up"
                if ready
                else f"service unavailable at {provider_cfg.base_url or ''}".strip()
            )
            known_models = list(probe.get("models", []))
            models = known_models if known_models else common_models_for_provider(provider_name)
        else:
            key_info = config_manager.get_api_key_info(provider_name)
            api_key = key_info.get("key")
            configured = bool(api_key)
            ready = dependency_available and configured
            source = str(key_info.get("source") or "none")
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


def _copy_probe_cache(signature: str) -> Optional[Dict[str, Dict[str, Any]]]:
    with _probe_cache_lock:
        if _probe_cache_result is None or _probe_cache_signature != signature:
            return None
        return {
            name: dict(payload)
            for name, payload in _probe_cache_result.items()
        }


def _store_probe_cache(
    signature: str,
    results: Dict[str, Dict[str, Any]],
    *,
    now: Optional[float] = None,
) -> None:
    global _probe_cache_at, _probe_cache_signature, _probe_cache_result
    with _probe_cache_lock:
        _probe_cache_at = float(now if now is not None else time.monotonic())
        _probe_cache_signature = signature
        _probe_cache_result = {
            name: dict(payload)
            for name, payload in results.items()
        }


def _refresh_probe_cache_async(
    config_manager: ConfigManager,
    config: Config,
    signature: str,
) -> None:
    global _probe_cache_refreshing
    with _probe_cache_lock:
        if _probe_cache_refreshing:
            return
        _probe_cache_refreshing = True

    def _worker() -> None:
        global _probe_cache_refreshing
        try:
            refreshed = _compute_probe_results(config_manager, config)
            with _probe_cache_lock:
                if _probe_cache_signature not in ("", signature):
                    return
            _store_probe_cache(signature, refreshed)
        except Exception:
            pass
        finally:
            with _probe_cache_lock:
                _probe_cache_refreshing = False

    thread = threading.Thread(
        target=_worker,
        name="provider-probe-refresh",
        daemon=True,
    )
    thread.start()


def _probe_local_providers(config: Config) -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    configured = set(config.model.providers.keys())
    local_openai_all_names = [
        name for name in LOCAL_OPENAI_COMPATIBLE_PROVIDERS
        if name in configured
    ]
    active_provider = str(getattr(getattr(config, "model", None), "provider", "") or "")
    routing_mode = normalize_routing_mode(
        getattr(getattr(config, "model", None), "routing_mode", "manual")
    )
    probe_all_local = _bool_env("POORCLI_PROVIDER_PROBE_ALL_LOCAL", False)
    local_openai_names = list(local_openai_all_names) if probe_all_local else []
    if not probe_all_local and active_provider in local_openai_all_names:
        local_openai_names = [active_provider]
    ollama_enabled = "ollama" in configured and (
        probe_all_local or active_provider == "ollama" or routing_mode == "private"
    )
    total_jobs = len(local_openai_names) + (1 if ollama_enabled else 0)
    if total_jobs <= 0:
        return {"ready": False, "models": []}, {}

    ollama_models: Dict[str, Any] = {"ready": False, "models": []}
    local_openai_models: Dict[str, Dict[str, Any]] = {}

    def _fallback_openai_payload(provider_name: str) -> Dict[str, Any]:
        provider_cfg = config.model.providers.get(provider_name)
        return {
            "ready": False,
            "models": [],
            "baseUrl": provider_cfg.base_url if provider_cfg else "",
        }

    max_workers = max(1, min(total_jobs, 6))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="provider-probe") as executor:
        futures: Dict[Any, tuple[str, Optional[str]]] = {}
        if ollama_enabled:
            futures[executor.submit(_discover_ollama_models, config)] = ("ollama", None)
        for name in local_openai_names:
            futures[executor.submit(_discover_openai_compatible_models, config, name)] = ("openai", name)

        for future, (probe_type, provider_name) in futures.items():
            try:
                payload = future.result()
            except Exception:
                if probe_type == "ollama":
                    payload = {"ready": False, "models": []}
                else:
                    payload = _fallback_openai_payload(str(provider_name or ""))
            if probe_type == "ollama":
                ollama_models = dict(payload or {"ready": False, "models": []})
            elif provider_name:
                local_openai_models[str(provider_name)] = dict(payload or _fallback_openai_payload(str(provider_name)))

    for name in local_openai_all_names:
        local_openai_models.setdefault(name, _fallback_openai_payload(name))
    return ollama_models, local_openai_models


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
        with urlopen(tags_url, timeout=_HTTP_PROBE_TIMEOUT_SECONDS) as response:
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


def _discover_openai_compatible_models(config: Config, provider_name: str) -> Dict[str, Any]:
    provider_cfg = config.model.providers.get(provider_name)
    base_url = provider_cfg.base_url if provider_cfg else ""
    if not base_url:
        return {"ready": False, "models": [], "baseUrl": base_url}
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    models_url = f"{base_url.rstrip('/')}/models"
    if not _is_tcp_reachable(host, port):
        return {"ready": False, "models": [], "baseUrl": base_url}

    request = models_url
    env_var = provider_cfg.api_key_env_var if provider_cfg else ""
    api_key = str(os.environ.get(env_var, "") or getattr(config, "api_keys", {}).get(provider_name, "") or "").strip()
    if api_key:
        from urllib.request import Request
        request = Request(models_url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(request, timeout=_HTTP_PROBE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("data") or []
        names = [
            str(model.get("id", "")).strip()
            for model in models
            if isinstance(model, dict) and str(model.get("id", "")).strip()
        ]
        return {"ready": True, "models": names, "baseUrl": base_url}
    except (OSError, URLError, ValueError):
        return {"ready": False, "models": [], "baseUrl": base_url}


def _is_tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=_TCP_CONNECT_TIMEOUT_SECONDS):
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
    if ready and set(ready).issubset(KEYLESS_LOCAL_PROVIDERS):
        return "local-only"
    if any(provider in KEYLESS_LOCAL_PROVIDERS for provider in ready):
        return "mixed"
    if any(ready):
        return "cloud"
    return "unconfigured"
