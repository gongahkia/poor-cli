"""Lightweight config reads for latency-sensitive read-only paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml


_DEFAULT_CONFIG_PATH = Path.home() / ".poor-cli" / "config.yaml"
_TRUSTED_REPOS_PATH = Path.home() / ".poor-cli" / "trusted_repos.json"
_PROVIDER_CATALOG_PATH = Path(__file__).resolve().parent / "provider_catalog.json"
_ROUTING_MODES = {"manual", "quality", "speed", "cheap", "private"}
_MODEL_DEFAULT_CACHE: Dict[str, str] | None = None


def normalize_routing_mode_fast(raw_value: Any) -> str:
    candidate = str(raw_value or "").strip().lower()
    if candidate in _ROUTING_MODES:
        return candidate
    return "manual"


def _load_yaml_map(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _repo_is_trusted(repo_root: Path) -> bool:
    if not _TRUSTED_REPOS_PATH.exists():
        return False
    try:
        payload = json.loads(_TRUSTED_REPOS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    trusted = payload.get("trusted")
    if not isinstance(trusted, list):
        return False
    canonical = str(repo_root.resolve())
    return canonical in {str(entry).strip() for entry in trusted}


def _default_models() -> Dict[str, str]:
    global _MODEL_DEFAULT_CACHE
    if _MODEL_DEFAULT_CACHE is not None:
        return dict(_MODEL_DEFAULT_CACHE)
    try:
        payload = json.loads(_PROVIDER_CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    models: Dict[str, str] = {}
    providers = payload.get("providers")
    if isinstance(providers, dict):
        for provider_name, provider_data in providers.items():
            if not isinstance(provider_data, dict):
                continue
            model_name = str(provider_data.get("defaultModel", "")).strip()
            if model_name:
                models[str(provider_name).strip().lower()] = model_name
    if "openai" not in models:
        models["openai"] = "gpt-5.1"
    _MODEL_DEFAULT_CACHE = dict(models)
    return dict(models)


def _default_model_for_provider(provider_name: str) -> str:
    provider = str(provider_name or "").strip().lower()
    if provider == "claude":
        provider = "anthropic"
    models = _default_models()
    return str(models.get(provider) or models.get("openai") or "gpt-5.1")


def load_runtime_model_settings(config_path_hint: str | None = None) -> Dict[str, str]:
    """Return provider/model/routing from global + trusted repo config only."""
    repo_root = Path.cwd().resolve()
    config_path = Path(config_path_hint).expanduser() if config_path_hint else _DEFAULT_CONFIG_PATH
    global_cfg = _load_yaml_map(config_path)
    model_cfg = dict(global_cfg.get("model", {})) if isinstance(global_cfg.get("model"), dict) else {}

    repo_cfg_path = repo_root / ".poor-cli" / "config.yaml"
    if _repo_is_trusted(repo_root):
        repo_cfg = _load_yaml_map(repo_cfg_path)
        repo_model_cfg = repo_cfg.get("model")
        if isinstance(repo_model_cfg, dict):
            model_cfg.update(repo_model_cfg)

    provider = str(model_cfg.get("provider", "")).strip() or "openai"
    model_name = str(model_cfg.get("model_name", "")).strip()
    if not model_name:
        model_name = _default_model_for_provider(provider)
    routing_mode = normalize_routing_mode_fast(model_cfg.get("routing_mode", "manual"))
    return {
        "provider": provider,
        "model": model_name,
        "routingMode": routing_mode,
    }
