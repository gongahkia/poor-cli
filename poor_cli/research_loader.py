"""Feature-gated loader for research modules."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from .config import ConfigManager
from .persisted import load_json

RESEARCH_MODULES = frozenset({
    "latent_communication",
    "neural_code_encoder",
})


def load_research_module(name: str, config: Any = None) -> ModuleType | None:
    if name not in RESEARCH_MODULES:
        raise ValueError(f"Unknown research module: {name}")
    if not is_research_module_enabled(name, config=config):
        return None
    return importlib.import_module(f"poor_cli.research.{name}")


def is_research_module_enabled(name: str, config: Any = None) -> bool:
    if name not in RESEARCH_MODULES:
        return False
    if config is not None:
        return _flag_from_obj(getattr(config, "research", None), name)
    return (
        _flag_from_user_config(name)
        or _flag_from_repo_preferences(name)
    )


def _flag_from_obj(research: Any, name: str) -> bool:
    if research is None:
        return False
    if isinstance(research, dict):
        value = research.get(name)
    else:
        value = getattr(research, name, None)
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return bool(value.get("enabled", False))
    return bool(getattr(value, "enabled", False))


def _flag_from_user_config(name: str) -> bool:
    path = ConfigManager.DEFAULT_CONFIG_FILE
    if not path.exists():
        return False
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    return _flag_from_obj(data.get("research"), name)


def _flag_from_repo_preferences(name: str) -> bool:
    path = Path.cwd() / ".poor-cli" / "preferences.json"
    if not path.exists():
        return False
    try:
        data = load_json(path, artifact="preferences", default={}) or {}
    except Exception:
        return False
    return _flag_from_obj(data.get("research"), name)
