"""Shared provider/model catalog used across Python surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ProviderCatalogEntry:
    name: str
    display_name: str
    env_var: str
    default_model: str
    common_models: tuple[str, ...]
    setup_help: str
    capability_summary: str
    capabilities: tuple[str, ...]
    base_url: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelTier:
    model_name: str
    tier: str  # "quality" | "balanced" | "cheap" | "private"
    cost_1k_in: float
    cost_1k_out: float
    speed_rank: int  # 1=fastest, 3=slowest
    context_window: int = 0  # max context tokens (0 = unknown)


_CATALOG_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "gemini": ("streaming", "tool_calling", "system_instructions", "json_mode", "vision"),
    "openai": ("streaming", "tool_calling", "system_instructions", "json_mode", "vision"),
    "anthropic": (
        "streaming",
        "tool_calling",
        "system_instructions",
        "vision",
        "prompt_caching_prefix",
        "prompt_caching_block",
        "extended_thinking",
    ),
    "openrouter": ("streaming", "tool_calling", "system_instructions", "json_mode", "vision"),
    "ollama": ("streaming", "tool_calling", "system_instructions", "json_mode"),
}


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
            capabilities=_CATALOG_CAPABILITIES.get(name, ()),
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


def get_model_tier(provider: str, model: str) -> Optional[ModelTier]:
    """Lookup model tier info from catalog JSON."""
    canonical = canonical_provider_name(provider)
    payload = _catalog_payload().get("providers", {}).get(canonical, {})
    tiers = payload.get("modelTiers", {})
    tier_data = tiers.get(model)
    if not tier_data:
        return None
    return ModelTier(
        model_name=model,
        tier=str(tier_data.get("tier", "balanced")),
        cost_1k_in=float(tier_data.get("cost_1k_in", 0)),
        cost_1k_out=float(tier_data.get("cost_1k_out", 0)),
        speed_rank=int(tier_data.get("speed_rank", 2)),
        context_window=int(tier_data.get("context_window", 0)),
    )


def get_model_context_window(provider: str, model: str) -> int:
    """Return context window size for a model, or 0 if unknown."""
    tier = get_model_tier(provider, model)
    return tier.context_window if tier else 0


def get_cheapest_model(provider: str) -> Optional[ModelTier]:
    """Return the cheapest model tier for a given provider, or None."""
    canonical = canonical_provider_name(provider)
    payload = _catalog_payload().get("providers", {}).get(canonical, {})
    tiers = payload.get("modelTiers", {})
    if not tiers:
        return None
    best: Optional[ModelTier] = None
    for model_name, tier_data in tiers.items():
        mt = ModelTier(
            model_name=model_name,
            tier=str(tier_data.get("tier", "balanced")),
            cost_1k_in=float(tier_data.get("cost_1k_in", 0)),
            cost_1k_out=float(tier_data.get("cost_1k_out", 0)),
            speed_rank=int(tier_data.get("speed_rank", 2)),
        )
        if best is None or mt.cost_1k_in < best.cost_1k_in:
            best = mt
    return best


def get_downshift_model(provider: str) -> Optional[Tuple[str, ModelTier]]:
    """Return (model_name, ModelTier) for the cheapest model of the same provider.

    Returns None if the provider has no model tiers or only one model.
    """
    canonical = canonical_provider_name(provider)
    payload = _catalog_payload().get("providers", {}).get(canonical, {})
    tiers = payload.get("modelTiers", {})
    if len(tiers) < 2:
        return None
    best_name: Optional[str] = None
    best_tier: Optional[ModelTier] = None
    for model_name, tier_data in tiers.items():
        mt = ModelTier(
            model_name=model_name,
            tier=str(tier_data.get("tier", "balanced")),
            cost_1k_in=float(tier_data.get("cost_1k_in", 0)),
            cost_1k_out=float(tier_data.get("cost_1k_out", 0)),
            speed_rank=int(tier_data.get("speed_rank", 2)),
        )
        if best_tier is None or mt.cost_1k_in < best_tier.cost_1k_in:
            best_name = model_name
            best_tier = mt
    if best_name and best_tier:
        return best_name, best_tier
    return None


def select_provider_and_model(
    routing_mode: str, ready_providers: List[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Pick best (provider, model) for the given routing mode.

    Returns (None, None) for 'manual' or if no match found.
    """
    if routing_mode == "manual" or not ready_providers:
        return None, None

    payload = _catalog_payload().get("providers", {})
    candidates: List[Tuple[str, ModelTier]] = []
    for prov in ready_providers:
        canonical = canonical_provider_name(prov)
        prov_data = payload.get(canonical, {})
        for model_name, tier_data in prov_data.get("modelTiers", {}).items():
            mt = ModelTier(
                model_name=model_name,
                tier=str(tier_data.get("tier", "balanced")),
                cost_1k_in=float(tier_data.get("cost_1k_in", 0)),
                cost_1k_out=float(tier_data.get("cost_1k_out", 0)),
                speed_rank=int(tier_data.get("speed_rank", 2)),
            )
            candidates.append((canonical, mt))

    if not candidates:
        return None, None

    if routing_mode == "quality":
        quality = [(p, m) for p, m in candidates if m.tier == "quality"]
        if quality:
            best = min(quality, key=lambda x: x[1].cost_1k_in)
            return best[0], best[1].model_name
    elif routing_mode == "speed":
        fastest = min(candidates, key=lambda x: (x[1].speed_rank, x[1].cost_1k_in))
        return fastest[0], fastest[1].model_name
    elif routing_mode == "cheap":
        cheapest = min(candidates, key=lambda x: x[1].cost_1k_in)
        return cheapest[0], cheapest[1].model_name
    elif routing_mode == "private":
        private = [(p, m) for p, m in candidates if m.tier == "private"]
        if private:
            return private[0][0], private[0][1].model_name

    return None, None


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
