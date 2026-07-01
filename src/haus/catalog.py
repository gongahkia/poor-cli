from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

_CATALOG_VERSION = 1
_DEFAULT_REGION = "sg"

_SOURCE_CONFIGS: dict[str, dict[str, Any]] = {
    "ikea": {
        "label": "IKEA",
        "domains": {"sg": "ikea.com/sg/en", "us": "ikea.com/us/en", "default": "ikea.com"},
        "currency": {"sg": "SGD", "us": "USD", "default": "SGD"},
    },
    "wayfair": {"label": "Wayfair", "domains": {"default": "wayfair.com"}, "currency": {"default": "USD"}},
    "westelm": {"label": "West Elm", "domains": {"default": "westelm.com"}, "currency": {"default": "USD"}},
    "cb2": {"label": "CB2", "domains": {"default": "cb2.com"}, "currency": {"default": "USD"}},
    "article": {"label": "Article", "domains": {"default": "article.com"}, "currency": {"default": "USD"}},
    "castlery": {"label": "Castlery", "domains": {"default": "castlery.com"}, "currency": {"sg": "SGD", "default": "USD"}},
    "hipvan": {"label": "HipVan", "domains": {"default": "hipvan.com"}, "currency": {"default": "SGD"}},
    "fortytwo": {"label": "FortyTwo", "domains": {"default": "fortytwo.sg"}, "currency": {"default": "SGD"}},
}
_DEFAULT_SOURCES = tuple(_SOURCE_CONFIGS)

_CATEGORY_DEFAULTS = {
    "bed": {"w": 1.5, "h": 0.55, "d": 2.0, "color": 0x77AADD},
    "sofa": {"w": 2.2, "h": 0.8, "d": 0.9, "color": 0x4A4A4A},
    "table": {"w": 1.2, "h": 0.75, "d": 0.8, "color": 0x8B6914},
    "chair": {"w": 0.5, "h": 0.45, "d": 0.5, "color": 0x333333},
    "desk": {"w": 1.2, "h": 0.75, "d": 0.6, "color": 0xD2B48C},
    "wardrobe": {"w": 1.2, "h": 2.0, "d": 0.6, "color": 0x5A4738},
    "storage": {"w": 0.8, "h": 1.2, "d": 0.4, "color": 0x6B4226},
    "lighting": {"w": 0.3, "h": 1.4, "d": 0.3, "color": 0xEAB308},
    "rug": {"w": 1.6, "h": 0.04, "d": 2.3, "color": 0x9CA3AF},
    "shower_chair": {"w": 0.5, "h": 0.48, "d": 0.5, "color": 0x60A5FA},
    "grab_bar": {"w": 0.6, "h": 0.08, "d": 0.08, "color": 0x93C5FD},
    "walker_parking": {"w": 0.7, "h": 0.9, "d": 0.35, "color": 0x22C55E},
    "wheelchair_turning_space": {"w": 1.5, "h": 0.02, "d": 1.5, "color": 0x86EFAC},
    "bedside_commode": {"w": 0.55, "h": 0.8, "d": 0.55, "color": 0x38BDF8},
    "built_in_storage": {"w": 1.6, "h": 2.4, "d": 0.45, "color": 0xA16207},
    "island": {"w": 1.8, "h": 0.9, "d": 0.9, "color": 0x78716C},
    "peninsula": {"w": 1.6, "h": 0.9, "d": 0.75, "color": 0x78716C},
    "partition": {"w": 1.5, "h": 2.4, "d": 0.10, "color": 0x94A3B8},
    "sliding_door": {"w": 0.9, "h": 2.1, "d": 0.08, "color": 0x7DD3FC},
    "glass_divider": {"w": 1.2, "h": 2.2, "d": 0.08, "color": 0xBAE6FD},
    "furniture": {"w": 1.0, "h": 0.75, "d": 0.6, "color": 0x888888},
}

_CATEGORY_ALIASES = {
    "bookcase": "storage",
    "shelving": "storage",
    "shelf": "storage",
    "cabinet": "storage",
    "accessibility shower chair": "shower_chair",
    "bath chair": "shower_chair",
    "grab rail": "grab_bar",
    "grab bar": "grab_bar",
    "walker": "walker_parking",
    "wheelchair turning": "wheelchair_turning_space",
    "commode": "bedside_commode",
    "built in": "built_in_storage",
    "built-in": "built_in_storage",
    "kitchen island": "island",
    "peninsula": "peninsula",
    "partition": "partition",
    "sliding door": "sliding_door",
    "glass divider": "glass_divider",
}

_CATEGORY_RULES = {
    "bed": {"front_clearance_m": 0.75, "side_clearance_m": 0.6},
    "sofa": {"front_clearance_m": 0.75, "side_clearance_m": 0.45},
    "table": {"chair_pullout_m": 0.9, "walkway_m": 0.75},
    "desk": {"chair_pullout_m": 0.75, "daylight_preference": True},
    "wardrobe": {"pullout_m": 0.8, "front_clearance_m": 0.75},
    "storage": {"front_clearance_m": 0.45},
    "shower_chair": {"transfer_clearance_m": 0.75},
    "grab_bar": {"verify_mounting": True},
    "walker_parking": {"clear_zone_m": 0.7},
    "wheelchair_turning_space": {"diameter_m": 1.5},
    "bedside_commode": {"transfer_clearance_m": 0.75},
    "built_in_storage": {"professional_verification": True, "front_clearance_m": 0.75},
    "island": {"walkway_m": 0.9, "service_verification": True},
    "peninsula": {"walkway_m": 0.9, "service_verification": True},
    "partition": {"concept_only": True, "professional_verification": True},
    "sliding_door": {"opening_width_m": 0.8},
    "glass_divider": {"concept_only": True},
}

_PULLOUT_ZONES = {
    "wardrobe": {"front_m": 0.8, "reason": "door/drawer pull-out"},
    "table": {"front_m": 0.9, "reason": "chair pull-out"},
    "desk": {"front_m": 0.75, "reason": "desk chair pull-out"},
    "sofa": {"front_m": 1.2, "reason": "sofa bed or recliner check"},
    "storage": {"front_m": 0.6, "reason": "drawer/door pull-out"},
}

_DEFAULT_SUBSTITUTIONS = {
    "bed": ["single bed", "storage bed with smaller frame"],
    "sofa": ["compact sofa", "armchair pair"],
    "wardrobe": ["narrow wardrobe", "open rail"],
    "table": ["drop-leaf table", "round compact table"],
    "desk": ["wall desk", "narrow desk"],
    "storage": ["shallow shelf", "wall-mounted cabinet"],
}

_SEED_ITEMS = [
    {
        "id": "ikea-seed-billy-bookcase",
        "source": "ikea",
        "region": "sg",
        "name": "BILLY bookcase",
        "category": "storage",
        "dimensions_m": {"width": 0.80, "height": 2.02, "depth": 0.28},
        "price": None,
        "currency": "SGD",
        "image_url": "",
        "product_url": "https://www.ikea.com/sg/en/search/?q=BILLY%20bookcase",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "ikea-seed-poang-armchair",
        "source": "ikea",
        "region": "sg",
        "name": "POANG armchair",
        "category": "chair",
        "dimensions_m": {"width": 0.68, "height": 1.00, "depth": 0.82},
        "price": None,
        "currency": "SGD",
        "image_url": "",
        "product_url": "https://www.ikea.com/sg/en/search/?q=POANG%20armchair",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "ikea-seed-kallax-shelf",
        "source": "ikea",
        "region": "sg",
        "name": "KALLAX shelving unit",
        "category": "storage",
        "dimensions_m": {"width": 0.77, "height": 1.47, "depth": 0.39},
        "price": None,
        "currency": "SGD",
        "image_url": "",
        "product_url": "https://www.ikea.com/sg/en/search/?q=KALLAX%20shelving",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "ikea-seed-malm-bed",
        "source": "ikea",
        "region": "sg",
        "name": "MALM bed frame",
        "category": "bed",
        "dimensions_m": {"width": 1.59, "height": 0.38, "depth": 2.09},
        "price": None,
        "currency": "SGD",
        "image_url": "",
        "product_url": "https://www.ikea.com/sg/en/search/?q=MALM%20bed",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "wayfair-seed-compact-sofa",
        "source": "wayfair",
        "region": "global",
        "name": "Compact sofa placeholder",
        "category": "sofa",
        "dimensions_m": {"width": 1.85, "height": 0.82, "depth": 0.88},
        "price": None,
        "currency": "USD",
        "image_url": "",
        "product_url": "https://www.wayfair.com/keyword.php?keyword=compact+sofa",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "westelm-seed-home-office-desk",
        "source": "westelm",
        "region": "global",
        "name": "Home office desk placeholder",
        "category": "desk",
        "dimensions_m": {"width": 1.22, "height": 0.76, "depth": 0.61},
        "price": None,
        "currency": "USD",
        "image_url": "",
        "product_url": "https://www.westelm.com/search/results.html?words=desk",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "cb2-seed-dining-table",
        "source": "cb2",
        "region": "global",
        "name": "Dining table placeholder",
        "category": "table",
        "dimensions_m": {"width": 1.83, "height": 0.76, "depth": 0.91},
        "price": None,
        "currency": "USD",
        "image_url": "",
        "product_url": "https://www.cb2.com/search?query=dining%20table",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "article-seed-lounge-chair",
        "source": "article",
        "region": "global",
        "name": "Lounge chair placeholder",
        "category": "chair",
        "dimensions_m": {"width": 0.76, "height": 0.82, "depth": 0.84},
        "price": None,
        "currency": "USD",
        "image_url": "",
        "product_url": "https://www.article.com/search?query=lounge%20chair",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "castlery-seed-queen-bed",
        "source": "castlery",
        "region": "global",
        "name": "Queen bed placeholder",
        "category": "bed",
        "dimensions_m": {"width": 1.62, "height": 0.95, "depth": 2.08},
        "price": None,
        "currency": "USD",
        "image_url": "",
        "product_url": "https://www.castlery.com/search?query=queen%20bed",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "hipvan-seed-storage-cabinet",
        "source": "hipvan",
        "region": "sg",
        "name": "Storage cabinet placeholder",
        "category": "storage",
        "dimensions_m": {"width": 0.9, "height": 1.2, "depth": 0.4},
        "price": None,
        "currency": "SGD",
        "image_url": "",
        "product_url": "https://www.hipvan.com/search?query=storage%20cabinet",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "fortytwo-seed-shoe-cabinet",
        "source": "fortytwo",
        "region": "sg",
        "name": "Shoe cabinet placeholder",
        "category": "storage",
        "dimensions_m": {"width": 0.8, "height": 1.0, "depth": 0.35},
        "price": None,
        "currency": "SGD",
        "image_url": "",
        "product_url": "https://www.fortytwo.sg/catalogsearch/result/?q=shoe%20cabinet",
        "availability": "unknown",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "haus-seed-shower-chair-placeholder",
        "source": "haus",
        "region": "global",
        "name": "Shower chair placeholder",
        "category": "shower_chair",
        "dimensions_m": {"width": 0.50, "height": 0.48, "depth": 0.50},
        "price": None,
        "currency": "unknown",
        "image_url": "",
        "product_url": "",
        "availability": "placeholder",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "haus-seed-sliding-door-placeholder",
        "source": "haus",
        "region": "global",
        "name": "Sliding door partition placeholder",
        "category": "sliding_door",
        "dimensions_m": {"width": 0.90, "height": 2.10, "depth": 0.08},
        "price": None,
        "currency": "unknown",
        "image_url": "",
        "product_url": "",
        "availability": "placeholder",
        "source_provider": "seed",
        "raw": {},
    },
    {
        "id": "haus-seed-kitchen-island-placeholder",
        "source": "haus",
        "region": "global",
        "name": "Kitchen island placeholder",
        "category": "island",
        "dimensions_m": {"width": 1.80, "height": 0.90, "depth": 0.90},
        "price": None,
        "currency": "unknown",
        "image_url": "",
        "product_url": "",
        "availability": "placeholder",
        "source_provider": "seed",
        "raw": {},
    },
]


def _catalog_root() -> Path:
    configured = os.environ.get("HAUS_CATALOG_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".haus" / "catalog"


def catalog_sources() -> list[dict[str, Any]]:
    return [{"id": source, "label": str(config["label"])} for source, config in _SOURCE_CONFIGS.items()]


def _source_dir(source: str) -> Path:
    clean = _normalize_source(source)
    path = _catalog_root() / clean
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ikea_dir() -> Path:
    return _source_dir("ikea")


def _normalize_source(source: str) -> str:
    clean = _slug(source)
    if clean in _SOURCE_CONFIGS or clean == "haus":
        return clean
    return "ikea"


def _normalize_sources(sources: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if sources is None:
        return ("ikea",)
    raw = sources if isinstance(sources, (list, tuple)) else str(sources).split(",")
    normalized = [_normalize_source(str(source)) for source in raw if str(source).strip()]
    if not normalized or "all" in {str(source).strip().lower() for source in raw}:
        return _DEFAULT_SOURCES
    return tuple(dict.fromkeys(normalized))


def _source_from_item_id(item_id: str) -> str | None:
    prefix = _slug(item_id).split("-", 1)[0]
    if prefix in _SOURCE_CONFIGS or prefix == "haus":
        return prefix
    return None


def _item_path(item_id: str, source: str | None = None) -> Path:
    clean = _slug(item_id)
    return _source_dir(source or _source_from_item_id(clean) or "ikea") / "items" / f"{clean}.json"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80] or "item"


def _item_id(name: str, url: str, source: str = "ikea") -> str:
    digest = hashlib.sha1(f"{name}|{url}".encode("utf-8")).hexdigest()[:10]  # noqa: S324
    return f"{_normalize_source(source)}-{_slug(name)}-{digest}"


def _source_label(source: str) -> str:
    return str(_SOURCE_CONFIGS.get(_normalize_source(source), {}).get("label") or source)


def _source_domain(source: str, region: str) -> str:
    config = _SOURCE_CONFIGS.get(_normalize_source(source), {})
    domains = config.get("domains", {})
    return str(domains.get(region) or domains.get("default") or "ikea.com")


def _source_currency(source: str, region: str) -> str:
    config = _SOURCE_CONFIGS.get(_normalize_source(source), {})
    currencies = config.get("currency", {})
    return str(currencies.get(region) or currencies.get("default") or ("SGD" if region == "sg" else "USD"))


def _collapse(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _category(text: str) -> str:
    lower = text.lower()
    for needle, category in _CATEGORY_ALIASES.items():
        if needle in lower:
            return category
    checks = (
        ("wardrobe", "wardrobe"),
        ("bookcase", "storage"),
        ("shelving", "storage"),
        ("shelf", "storage"),
        ("cabinet", "storage"),
        ("storage", "storage"),
        ("sofa", "sofa"),
        ("bed", "bed"),
        ("mattress", "bed"),
        ("desk", "desk"),
        ("chair", "chair"),
        ("table", "table"),
        ("lamp", "lighting"),
        ("light", "lighting"),
        ("rug", "rug"),
    )
    for needle, category in checks:
        if needle in lower:
            return category
    return "furniture"


def _default_dimensions(category: str) -> dict[str, float]:
    spec = _CATEGORY_DEFAULTS.get(category, _CATEGORY_DEFAULTS["furniture"])
    return {"width": float(spec["w"]), "height": float(spec["h"]), "depth": float(spec["d"])}


def _color(category: str) -> int:
    return int(_CATEGORY_DEFAULTS.get(category, _CATEGORY_DEFAULTS["furniture"])["color"])


def _parse_price(text: str, default_currency: str = "SGD") -> tuple[float | None, str]:
    match = re.search(r"(S\$|SGD\s*|US\$|USD\s*|\$)\s*([0-9][0-9,.]*)", text, re.IGNORECASE)
    if not match:
        return None, default_currency
    prefix = match.group(1).upper().replace(" ", "")
    currency = "SGD" if prefix in {"S$", "SGD"} else "USD" if prefix in {"US$", "USD"} else default_currency
    try:
        return float(match.group(2).replace(",", "")), currency
    except ValueError:
        return None, default_currency


def _parse_dimensions(text: str, category: str) -> dict[str, float]:
    lower = text.lower()
    dims = _default_dimensions(category)

    labeled = {
        "width": r"\b(?:width|w)\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m)",
        "depth": r"\b(?:depth|d)\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m)",
        "height": r"\b(?:height|h)\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m)",
    }
    for key, pattern in labeled.items():
        match = re.search(pattern, lower)
        if match:
            dims[key] = _to_m(float(match.group(1)), match.group(2))

    compact = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*[x×]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[x×]\s*([0-9]+(?:\.[0-9]+)?))?\s*(mm|cm|m)",
        lower,
    )
    if compact:
        unit = compact.group(4)
        dims["width"] = _to_m(float(compact.group(1)), unit)
        dims["depth"] = _to_m(float(compact.group(2)), unit)
        if compact.group(3):
            dims["height"] = _to_m(float(compact.group(3)), unit)

    return {key: round(max(0.01, value), 4) for key, value in dims.items()}


def _to_m(value: float, unit: str) -> float:
    if unit == "mm":
        return value / 1000
    if unit == "cm":
        return value / 100
    return value


def _normalize_item(
    *,
    title: str,
    url: str,
    snippet: str,
    region: str,
    source: str,
    provider: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    clean_source = _normalize_source(source)
    label = re.escape(_source_label(clean_source))
    name = re.sub(rf"\s*-\s*{label}.*$", "", title, flags=re.IGNORECASE).strip() or title
    text = f"{name} {snippet}"
    category = _category(text)
    price, currency = _parse_price(text, _source_currency(clean_source, region))
    image_url = _collapse(raw.get("image") or raw.get("image_url") or raw.get("thumbnail"))
    item = {
        "schema_version": _CATALOG_VERSION,
        "id": _item_id(name, url, clean_source),
        "source": clean_source,
        "region": region,
        "name": name,
        "category": category,
        "dimensions_m": _parse_dimensions(text, category),
        "price": price,
        "currency": currency,
        "image_url": image_url,
        "product_url": url,
        "availability": "unknown",
        "source_provider": provider,
        "last_checked_date": date.today().isoformat() if provider != "seed" else None,
        "raw": raw,
    }
    return enrich_catalog_item(item)


def _stale_warning(item: dict[str, Any]) -> str | None:
    provider = str(item.get("source_provider") or "")
    if provider in {"seed", "manual"}:
        return "Seed/manual catalog dimensions and prices should be verified before purchase."
    checked = item.get("last_checked_date")
    if not checked:
        return "Live product dimensions or prices have no last-checked date."
    try:
        checked_day = datetime.fromisoformat(str(checked)).date()
    except ValueError:
        return "Live product dimensions or prices have an invalid last-checked date."
    if (date.today() - checked_day).days > 30:
        return "Live product dimensions or prices may be stale; refresh before purchase."
    return None


def enrich_catalog_item(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    category = str(enriched.get("category") or "furniture")
    enriched["category"] = category
    enriched.setdefault("clearance_rules", _CATEGORY_RULES.get(category, {"front_clearance_m": 0.6}))
    enriched.setdefault("pullout_zones", _PULLOUT_ZONES.get(category, {}))
    enriched.setdefault(
        "delivery_constraints",
        {
            "checkpoints": ["entry door", "corridor", "room door", "elevator placeholder", "stair placeholder"],
            "requires_manual_measurement": True,
        },
    )
    enriched.setdefault(
        "category_aliases",
        sorted(alias for alias, mapped in _CATEGORY_ALIASES.items() if mapped == category),
    )
    enriched.setdefault("default_substitutions", _DEFAULT_SUBSTITUTIONS.get(category, []))
    provider = str(enriched.get("source_provider") or "unknown")
    enriched.setdefault(
        "provenance",
        {
            "source": enriched.get("source", "catalog"),
            "provider": provider,
            "source_url": enriched.get("product_url", ""),
            "retrieved_at": enriched.get("last_checked_date"),
        },
    )
    warning = _stale_warning(enriched)
    if warning:
        enriched["stale_warning"] = warning
    return enriched


def _save_item(item: dict[str, Any]) -> None:
    path = _item_path(str(item["id"]), str(item.get("source") or "ikea"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")


def _load_cached_items(sources: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in sources or _DEFAULT_SOURCES:
        items_dir = _source_dir(source) / "items"
        if not items_dir.exists():
            continue
        for path in sorted(items_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                items.append(payload)
    return items


def _matches(item: dict[str, Any], query: str) -> bool:
    text = f"{item.get('name', '')} {item.get('category', '')} {item.get('source', '')}".lower()
    tokens = [token for token in re.split(r"\W+", query.lower()) if token]
    return not tokens or all(token in text for token in tokens)


def search_furniture_catalog(
    query: str,
    *,
    max_results: int = 12,
    region: str = _DEFAULT_REGION,
    refresh: bool = False,
    sources: str | list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    clean_query = _collapse(query)
    if not clean_query:
        raise ValueError("query must not be empty.")
    limit = max(1, min(int(max_results or 12), 24))
    clean_region = (region or _DEFAULT_REGION).lower()
    source_ids = _normalize_sources(sources)

    seeds = [dict(item) for item in _SEED_ITEMS if str(item.get("source")) in set(source_ids) or str(item.get("source")) == "haus"]
    candidates = _load_cached_items(source_ids) + seeds
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if _matches(item, clean_query):
            deduped[str(item["id"])] = enrich_catalog_item(item)
    results = list(deduped.values())[:limit]

    query_path = _catalog_root() / "queries" / f"{_slug('-'.join(source_ids))}-{_slug(clean_query)}.json"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(
        json.dumps({"query": clean_query, "region": clean_region, "sources": source_ids, "items": results}, indent=2),
        encoding="utf-8",
    )
    return results


def search_ikea_catalog(
    query: str,
    *,
    max_results: int = 12,
    region: str = _DEFAULT_REGION,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    clean_query = _collapse(query)
    if not clean_query:
        raise ValueError("query must not be empty.")
    limit = max(1, min(int(max_results or 12), 24))
    clean_region = (region or _DEFAULT_REGION).lower()
    candidates = _load_cached_items(("ikea",)) + [dict(item) for item in _SEED_ITEMS if item.get("source") in {"ikea", "haus"}]
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if _matches(item, clean_query):
            deduped[str(item["id"])] = enrich_catalog_item(item)
    results = list(deduped.values())[:limit]

    query_path = _ikea_dir() / "queries" / f"{_slug(clean_query)}.json"
    query_path.parent.mkdir(parents=True, exist_ok=True)
    query_path.write_text(json.dumps({"query": clean_query, "region": clean_region, "items": results}, indent=2), encoding="utf-8")
    return results


def catalog_search_meta(
    items: list[dict[str, Any]],
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    providers = sorted({str(item.get("source_provider") or "unknown") for item in items})
    return {
        "source_providers": providers,
        "live_refresh_requested": bool(refresh),
        "live_result_count": 0,
        "fallback_used": bool(refresh),
    }


def get_catalog_item(item_id: str) -> dict[str, Any] | None:
    clean = _slug(item_id)
    path = _item_path(clean)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return enrich_catalog_item(payload)
    for source in _DEFAULT_SOURCES:
        path = _item_path(clean, source)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                return enrich_catalog_item(payload)
    for item in _SEED_ITEMS:
        if item["id"] == item_id:
            return enrich_catalog_item(dict(item))
    return None


def refresh_catalog_item(item_id: str) -> dict[str, Any] | None:
    item = get_catalog_item(item_id)
    return item


def catalog_item_to_layout_item(
    item: dict[str, Any],
    *,
    x: float = 0.0,
    z: float = 0.0,
    rotation_deg: float = 0.0,
) -> dict[str, Any]:
    dims_raw = item.get("dimensions_m")
    dims: dict[str, Any] = dims_raw if isinstance(dims_raw, dict) else {}
    width = float(dims.get("width") or 1.0)
    height = float(dims.get("height") or 0.75)
    depth = float(dims.get("depth") or 0.6)
    category = str(item.get("category") or "furniture")
    source = str(item.get("source") or _source_from_item_id(str(item.get("id") or "")) or "catalog")
    return {
        "type": "furniture",
        "furnitureType": f"{source}:{item['id']}",
        "name": str(item.get("name") or item["id"]),
        "pos": [float(x), height / 2.0, float(z)],
        "rot": float(rotation_deg) * 3.141592653589793 / 180.0,
        "visible": True,
        "geo": [width, height, depth],
        "color": _color(category),
        "catalog": {
            "source": source,
            "item_id": item["id"],
            "product_url": item.get("product_url"),
            "price": item.get("price"),
            "currency": item.get("currency"),
            "category": category,
            "source_provider": item.get("source_provider"),
            "source_confidence": item.get("source_provider") or "unknown",
            "last_checked_date": item.get("last_checked_date"),
            "provenance": item.get("provenance"),
            "stale_warning": item.get("stale_warning"),
            "clearance_rules": item.get("clearance_rules"),
            "pullout_zones": item.get("pullout_zones"),
            "delivery_constraints": item.get("delivery_constraints"),
        },
    }


def format_catalog_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No catalog items found."
    lines = ["Furniture catalog results:"]
    for item in items:
        dims = item.get("dimensions_m", {})
        dim_text = f"{dims.get('width')}m x {dims.get('depth')}m x {dims.get('height')}m"
        price = item.get("price")
        price_text = f" {item.get('currency', 'SGD')} {price}" if price is not None else ""
        lines.append(f"- {item['id']}: {item.get('name')} ({item.get('source')}, {item.get('category')}, {dim_text}){price_text}")
        if item.get("product_url"):
            lines.append(f"  {item['product_url']}")
    return "\n".join(lines)
