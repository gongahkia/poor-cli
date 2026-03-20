"""Shared provider/model catalog used across Python surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Dict, Iterable


@dataclass(frozen=True)
class ProviderCatalogEntry:
    name: str
    display_name: str
    env_var: str
    default_model: str
    common_models: tuple[str, ...]
    setup_help: str
    capability_summary: str
    base_url: str | None = None
    aliases: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def _catalog_payload() -> Dict[str, Any]:
    raw = files("poor_cli").joinpath("provider_catalog.json").read_text(encoding="utf-8")
    return json.loads(raw)


@lru_cache(maxsize=1)
def provider_catalog() -> Dict[str, ProviderCatalogEntry]:
    catalog: Dict[str, ProviderCatalogEntry] = {}
    for name, payload in _catalog_payload().get("providers", {}).items():
        if not isinstance(payload, dict):
            continue
        catalog[name] = ProviderCatalogEntry(
            name=name,
            display_name=str(payload.get("displayName", name.title())),
            env_var=str(payload.get("envVar", "")),
            default_model=str(payload.get("defaultModel", "")),
            common_models=tuple(
                str(model)
                for model in payload.get("commonModels", [])
                if str(model).strip()
            ),
            setup_help=str(payload.get("setupHelp", "")),
            capability_summary=str(payload.get("capabilitySummary", "")),
            base_url=str(payload["baseUrl"]) if payload.get("baseUrl") else None,
            aliases=tuple(
                str(alias) for alias in payload.get("aliases", []) if str(alias).strip()
            ),
        )
    return catalog


@lru_cache(maxsize=1)
def provider_name_aliases() -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for name, entry in provider_catalog().items():
        aliases[name] = name
        aliases[entry.display_name.lower()] = name
        for alias in entry.aliases:
            aliases[alias.lower()] = name
    return aliases


def canonical_provider_name(name: str) -> str:
    candidate = str(name or "").strip().lower()
    return provider_name_aliases().get(candidate, candidate)


def get_provider_entry(name: str) -> ProviderCatalogEntry:
    canonical = canonical_provider_name(name)
    return provider_catalog()[canonical]


def default_model_for_provider(name: str) -> str:
    return get_provider_entry(name).default_model


def common_models_for_provider(name: str) -> list[str]:
    return list(get_provider_entry(name).common_models)


def all_provider_entries() -> Iterable[ProviderCatalogEntry]:
    return provider_catalog().values()


README_MODEL_SUPPORT_HEADER = (
    "| Provider | Key | Default Model | Common Models | Capabilities in `poor-cli` |"
)
README_MODEL_SUPPORT_SEPARATOR = "|---|---|---|---|---|"


def _readme_provider_label(entry: ProviderCatalogEntry) -> str:
    if entry.name == "anthropic" and any(alias.lower() == "claude" for alias in entry.aliases):
        return "Anthropic / Claude"
    return entry.display_name


def _readme_key_label(entry: ProviderCatalogEntry) -> str:
    if entry.name == "anthropic" and any(alias.lower() == "claude" for alias in entry.aliases):
        return f"`{entry.name}` (alias: `claude`)"
    return f"`{entry.name}`"


def _readme_common_models(entry: ProviderCatalogEntry) -> str:
    rendered_models = ", ".join(f"`{model}`" for model in entry.common_models)
    if entry.name == "ollama":
        return (
            "Auto-discovered from local `ollama` (`/api/tags`), with fallbacks "
            f"{rendered_models}"
        )
    return rendered_models


def _readme_capability_summary(entry: ProviderCatalogEntry) -> str:
    summary = entry.capability_summary
    if entry.name == "ollama" and entry.base_url:
        return f"{summary}, local-only execution via `{entry.base_url}`"
    return summary


def render_readme_model_support_table() -> str:
    lines = [README_MODEL_SUPPORT_HEADER, README_MODEL_SUPPORT_SEPARATOR]
    for entry in all_provider_entries():
        lines.append(
            "| {provider} | {key} | `{default_model}` | {common_models} | {capabilities} |".format(
                provider=_readme_provider_label(entry),
                key=_readme_key_label(entry),
                default_model=entry.default_model,
                common_models=_readme_common_models(entry),
                capabilities=_readme_capability_summary(entry),
            )
        )
    return "\n".join(lines)
