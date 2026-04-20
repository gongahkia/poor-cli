from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from seuss.defaults import DEFAULT_CONFIG_YAML
from seuss.provenance import validate_provenance

DEFAULT_CONFIG_PATH = Path("seuss.yaml")


class ConfigError(RuntimeError):
    pass


def write_default_config(path: Path, force: bool = False) -> None:
    if path.exists() and not force:
        raise ConfigError(f"Config already exists at {path}. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(
            f"Config not found at {path}. Run 'seuss init' or pass --config <path>."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping.")
    validate_config(raw)
    return raw


def validate_config(config: dict[str, Any]) -> None:
    required_roots = [
        "project",
        "sources",
        "privacy",
        "segmentation",
        "splits",
        "adaptation",
        "generation",
        "evaluation",
    ]
    for key in required_roots:
        if key not in config:
            raise ConfigError(f"Missing required config section: {key}")

    sources = config.get("sources", [])
    if not isinstance(sources, list):
        raise ConfigError("sources must be a list")

    for source in sources:
        if not isinstance(source, dict):
            raise ConfigError("Each source must be a mapping")
        name = source.get("name")
        src_type = source.get("type")
        path = source.get("path")
        provenance = source.get("provenance", "human_original")
        if not name or not src_type or not path:
            raise ConfigError("Each source needs name, type, and path")
        validate_provenance(provenance)


def resolve_workspace(config: dict[str, Any], config_path: Path) -> Path:
    workspace_value = config.get("project", {}).get("workspace", "./.seuss")
    workspace = Path(workspace_value)
    if not workspace.is_absolute():
        workspace = (config_path.parent / workspace).resolve()
    return workspace


def resolve_path(value: str, config_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()
