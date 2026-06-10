from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_TINYFISH_SEARCH_URL = "https://api.search.tinyfish.ai"
_TINYFISH_FETCH_URL = "https://api.fetch.tinyfish.ai"
_CATALOG_VERSION = 1
_DEFAULT_REGION = "sg"
_DEFAULT_TIMEOUT_SECONDS = 8

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
    "furniture": {"w": 1.0, "h": 0.75, "d": 0.6, "color": 0x888888},
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
]


def _catalog_root() -> Path:
    configured = os.environ.get("HAUS_CATALOG_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".haus" / "catalog"


def _ikea_dir() -> Path:
    path = _catalog_root() / "ikea"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _item_path(item_id: str) -> Path:
    return _ikea_dir() / "items" / f"{item_id}.json"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80] or "item"


def _item_id(name: str, url: str) -> str:
    digest = hashlib.sha1(f"{name}|{url}".encode("utf-8")).hexdigest()[:10]  # noqa: S324
    return f"ikea-{_slug(name)}-{digest}"


def _collapse(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _category(text: str) -> str:
    lower = text.lower()
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


def _parse_price(text: str) -> tuple[float | None, str]:
    match = re.search(r"(?:S\$|SGD\s*|\$)\s*([0-9][0-9,.]*)", text, re.IGNORECASE)
    if not match:
        return None, "SGD"
    try:
        return float(match.group(1).replace(",", "")), "SGD"
    except ValueError:
        return None, "SGD"


def _parse_dimensions(text: str, category: str) -> dict[str, float]:
    lower = text.lower()
    dims = _default_dimensions(category)

    labeled = {
        "width": r"(?:width|w)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m)",
        "depth": r"(?:depth|d)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m)",
        "height": r"(?:height|h)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m)",
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


def _tinyfish_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    api_key = os.environ.get("TINYFISH_API_KEY")
    if not api_key:
        raise ValueError("TINYFISH_API_KEY is not set.")
    body = None
    headers = {"X-API-Key": api_key}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, method=method, headers=headers)
    with urlopen(req, timeout=_DEFAULT_TIMEOUT_SECONDS) as res:  # noqa: S310 - public API endpoint.
        return json.loads(res.read().decode("utf-8"))


def _result_list(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("results", "data", "items", "organic"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _search_tinyfish(query: str, max_results: int, region: str) -> list[dict[str, Any]]:
    site = "ikea.com/sg/en" if region == "sg" else "ikea.com"
    search_query = f"site:{site} {query} IKEA product dimensions price"
    data = _tinyfish_json(f"{_TINYFISH_SEARCH_URL}?{urlencode({'query': search_query, 'limit': max_results})}")
    items: list[dict[str, Any]] = []
    for result in _result_list(data)[:max_results]:
        if not isinstance(result, dict):
            continue
        title = _collapse(result.get("title") or result.get("name"))
        url = _collapse(result.get("url") or result.get("link"))
        snippet = _collapse(result.get("snippet") or result.get("description") or result.get("text"))
        if not title or not url or "ikea." not in url.lower():
            continue
        items.append(_normalize_item(title=title, url=url, snippet=snippet, region=region, provider="tinyfish", raw=result))
    return items


def _normalize_item(
    *,
    title: str,
    url: str,
    snippet: str,
    region: str,
    provider: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    name = re.sub(r"\s*-\s*IKEA.*$", "", title, flags=re.IGNORECASE).strip() or title
    text = f"{name} {snippet}"
    category = _category(text)
    price, currency = _parse_price(text)
    image_url = _collapse(raw.get("image") or raw.get("image_url") or raw.get("thumbnail"))
    return {
        "schema_version": _CATALOG_VERSION,
        "id": _item_id(name, url),
        "source": "ikea",
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
        "raw": raw,
    }


def _save_item(item: dict[str, Any]) -> None:
    path = _item_path(str(item["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")


def _load_cached_items() -> list[dict[str, Any]]:
    items_dir = _ikea_dir() / "items"
    if not items_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(items_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _matches(item: dict[str, Any], query: str) -> bool:
    text = f"{item.get('name', '')} {item.get('category', '')}".lower()
    tokens = [token for token in re.split(r"\W+", query.lower()) if token]
    return not tokens or all(token in text for token in tokens)


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

    live_items: list[dict[str, Any]] = []
    if refresh or os.environ.get("TINYFISH_API_KEY"):
        try:
            live_items = _search_tinyfish(clean_query, limit, clean_region)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
            live_items = []
        for item in live_items:
            _save_item(item)

    candidates = live_items + _load_cached_items() + [dict(item) for item in _SEED_ITEMS]
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if _matches(item, clean_query):
            deduped[str(item["id"])] = item
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
    live_count = sum(1 for item in items if item.get("source_provider") == "tinyfish")
    return {
        "source_providers": providers,
        "live_refresh_requested": bool(refresh),
        "live_result_count": live_count,
        "fallback_used": bool(refresh) and live_count == 0,
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
            return payload
    for item in _SEED_ITEMS:
        if item["id"] == item_id:
            return dict(item)
    return None


def refresh_catalog_item(item_id: str) -> dict[str, Any] | None:
    item = get_catalog_item(item_id)
    if item is None:
        return None
    url = str(item.get("product_url") or "")
    if not url or not os.environ.get("TINYFISH_API_KEY"):
        return item
    try:
        data = _tinyfish_json(_TINYFISH_FETCH_URL, method="POST", payload={"url": url})
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        return item
    if isinstance(data, dict):
        text = _collapse(data.get("text") or data.get("markdown") or data.get("content") or data.get("body"))
        title = _collapse(data.get("title") or item.get("name"))
        updated = _normalize_item(title=title, url=url, snippet=text[:4000], region=str(item.get("region") or _DEFAULT_REGION), provider="tinyfish", raw=data)
        updated["id"] = item["id"]
        _save_item(updated)
        return updated
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
    return {
        "type": "furniture",
        "furnitureType": f"ikea:{item['id']}",
        "name": str(item.get("name") or item["id"]),
        "pos": [float(x), height / 2.0, float(z)],
        "rot": float(rotation_deg) * 3.141592653589793 / 180.0,
        "visible": True,
        "geo": [width, height, depth],
        "color": _color(category),
        "catalog": {
            "source": "ikea",
            "item_id": item["id"],
            "product_url": item.get("product_url"),
            "price": item.get("price"),
            "currency": item.get("currency"),
            "category": category,
        },
    }


def format_catalog_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No IKEA catalog items found."
    lines = ["IKEA catalog results:"]
    for item in items:
        dims = item.get("dimensions_m", {})
        dim_text = f"{dims.get('width')}m x {dims.get('depth')}m x {dims.get('height')}m"
        price = item.get("price")
        price_text = f" {item.get('currency', 'SGD')} {price}" if price is not None else ""
        lines.append(f"- {item['id']}: {item.get('name')} ({item.get('category')}, {dim_text}){price_text}")
        if item.get("product_url"):
            lines.append(f"  {item['product_url']}")
    return "\n".join(lines)
