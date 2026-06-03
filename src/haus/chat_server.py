# pyright: reportPrivateImportUsage=false

"""Combined static file server + AI chat API for the haus editor.

Serves viewer files and provides `/api/chat` with tool-using LLM providers.
"""

from __future__ import annotations

import importlib
import json
import mimetypes
import os
import base64
import ipaddress
import socket
import time
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request as UrlRequest, urlopen

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn

from . import mcp_server as _mcp_server
from .logging_utils import configure_logging, new_request_id
from .mcp_server import (
    _save_layout,
    add_furniture,
    add_wall,
    align_objects,
    apply_simulated_option,
    auto_place_furniture,
    batch_move,
    check_overlap,
    check_sightline,
    clear_layout,
    compute_room_area,
    design_flat,
    design_room,
    distribute_objects,
    duplicate_object,
    find_by_name,
    find_nearest,
    find_objects_in_area,
    get_layout_summary,
    get_object_details,
    list_furniture_catalog,
    list_objects,
    list_rooms,
    measure_distance,
    move_object,
    remove_object,
    remove_objects_by_type,
    rename_object,
    resize_object,
    rotate_object,
    set_color,
    set_visibility,
    simulate_layout_options,
    snap_to_grid,
    suggest_furniture_placement,
    swap_furniture,
    tag_room,
)

log = configure_logging("haus.chat")

mimetypes.add_type("model/gltf-binary", ".glb")

_MAX_TOOL_STEPS = 12
_MAX_CHAT_ATTACHMENTS = 3
_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
_ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_WEB_TIMEOUT_SECONDS = 8
_MAX_WEB_RESPONSE_BYTES = 1_000_000
_WEB_SEARCH_ENABLED = os.environ.get("HAUS_ENABLE_WEB_SEARCH", "1").lower() not in {"0", "false", "no"}

_SYSTEM = (
    "You are an AI assistant for the haus floor plan editor. "
    "You ONLY help with floor plan editing — arranging furniture, walls, and layout. "
    "You may use live web references when they support interior design, furniture, HDB/BTO, "
    "renovation, accessibility, materials, or product-dimension decisions. "
    "If the user asks something unrelated (general knowledge, coding, etc), "
    "politely decline and remind them you only handle floor plan tasks.\n\n"
    "Coordinate system: X is left-right, Z is forward-back. Positions are in meters.\n"
    "Typical room sizes: bedrooms ~3x3m, living rooms ~4x5m, bathrooms ~2x2m, kitchens ~2.5x3m.\n\n"
    "IMPORTANT RULES:\n"
    "- Before any DESTRUCTIVE action (removing, clearing, or replacing objects), "
    "FIRST describe what you plan to do and ASK for confirmation.\n"
    "- For whole-room or whole-flat design requests, prefer design_room or design_flat "
    "before falling back to primitive add/move tools.\n"
    "- For vague intents (e.g., best sofa placement with clear TV view), "
    "use simulation tools: suggest_furniture_placement, auto_place_furniture, "
    "simulate_layout_options, apply_simulated_option, and check_sightline.\n"
    "- remove_objects_by_type is safer than repeated remove_object when deleting many.\n"
    "- batch_move uses relative offsets (dx, dz), not absolute positions.\n\n"
    "Reference workflow:\n"
    "- Use web_search for current design/product/HDB references when the user asks for current, "
    "specific, sourced, or live reference guidance.\n"
    "- Use fetch_web_page when the user provides a URL or a search result needs more detail.\n"
    "- Cite source URLs in the final answer whenever web tools influenced the plan.\n"
    "- If the user attaches images, treat them as visual references to replicate with available "
    "Haus furniture, walls, colors, and room tags. Explain approximations when exact objects "
    "or materials are unavailable.\n\n"
    "Workflow:\n"
    "1. get_layout_summary() for high-level state\n"
    "2. list_objects() / get_object_details(index) for specifics\n"
    "3. Spatial checks: measure_distance, find_nearest, check_overlap, find_objects_in_area\n"
    "4. For intent-driven placement, simulate first then apply\n"
    "5. Confirm exactly what changed\n"
    "Keep responses concise."
)

_TOOLS_SPEC = [
    {
        "name": "design_room",
        "description": "High-level tool: furnish one room from a style prompt and constraints.",
        "parameters": {
            "type": "object",
            "properties": {
                "room_id": {"type": "string", "default": ""},
                "style_prompt": {"type": "string", "default": "minimalist HDB"},
                "constraints": {"type": "string", "default": ""},
                "origin_x": {"type": "number"},
                "origin_z": {"type": "number"},
            },
        },
    },
    {
        "name": "design_flat",
        "description": "High-level tool: furnish a whole flat from a style prompt and constraints.",
        "parameters": {
            "type": "object",
            "properties": {
                "style_prompt": {"type": "string", "default": "minimalist 4-room family flat"},
                "constraints": {"type": "string", "default": ""},
                "target": {"type": "string", "default": "whole_flat"},
            },
        },
    },
    {
        "name": "list_furniture_catalog",
        "description": "List all available furniture types with dimensions.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": (
            "Search the live web for current interior design, furniture, HDB/BTO, renovation, "
            "accessibility, material, or product-dimension references. Returns source URLs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query focused on the design task."},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_web_page",
        "description": (
            "Fetch visible text from a specific public http(s) URL for a design reference. "
            "Use this after a user provides a URL or a web_search result needs more detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public http(s) URL to fetch."},
                "max_chars": {"type": "integer", "default": 4000},
            },
            "required": ["url"],
        },
    },
    {
        "name": "list_objects",
        "description": "List all objects in the current layout with index, type, position.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "add_furniture",
        "description": "Add a furniture item at a position.",
        "parameters": {
            "type": "object",
            "properties": {
                "furniture_type": {
                    "type": "string",
                    "description": "Type from catalog (e.g. bed_queen, sofa_3, desk)",
                },
                "x": {"type": "number", "default": 0},
                "z": {"type": "number", "default": 0},
                "rotation_deg": {"type": "number", "default": 0},
            },
            "required": ["furniture_type"],
        },
    },
    {
        "name": "add_wall",
        "description": "Add a wall segment between two points.",
        "parameters": {
            "type": "object",
            "properties": {
                "x1": {"type": "number"},
                "z1": {"type": "number"},
                "x2": {"type": "number"},
                "z2": {"type": "number"},
                "height": {"type": "number", "default": 2.6},
                "thickness": {"type": "number", "default": 0.15},
            },
            "required": ["x1", "z1", "x2", "z2"],
        },
    },
    {
        "name": "move_object",
        "description": "Move an object to a new XZ position.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "x": {"type": "number"},
                "z": {"type": "number"},
            },
            "required": ["index", "x", "z"],
        },
    },
    {
        "name": "rotate_object",
        "description": "Set an object's rotation in degrees.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "rotation_deg": {"type": "number"},
            },
            "required": ["index", "rotation_deg"],
        },
    },
    {
        "name": "remove_object",
        "description": "Remove an object by index.",
        "parameters": {
            "type": "object",
            "properties": {"index": {"type": "integer"}},
            "required": ["index"],
        },
    },
    {
        "name": "remove_objects_by_type",
        "description": "Remove all objects of a given type.",
        "parameters": {
            "type": "object",
            "properties": {"object_type": {"type": "string"}},
            "required": ["object_type"],
        },
    },
    {
        "name": "clear_layout",
        "description": "Remove all objects.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_object_details",
        "description": "Get full details for one object.",
        "parameters": {
            "type": "object",
            "properties": {"index": {"type": "integer"}},
            "required": ["index"],
        },
    },
    {
        "name": "get_layout_summary",
        "description": "Get object counts and layout bounding box.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "resize_object",
        "description": "Resize an object. Only provided dimensions are changed.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "width": {"type": "number"},
                "height": {"type": "number"},
                "depth": {"type": "number"},
            },
            "required": ["index"],
        },
    },
    {
        "name": "set_color",
        "description": "Set object color using hex string.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "color": {"type": "string"},
            },
            "required": ["index", "color"],
        },
    },
    {
        "name": "set_visibility",
        "description": "Show or hide an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "visible": {"type": "boolean"},
            },
            "required": ["index", "visible"],
        },
    },
    {
        "name": "duplicate_object",
        "description": "Duplicate an object to a new position.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "x": {"type": "number"},
                "z": {"type": "number"},
            },
            "required": ["index", "x", "z"],
        },
    },
    {
        "name": "batch_move",
        "description": "Move multiple objects by a relative offset.",
        "parameters": {
            "type": "object",
            "properties": {
                "indices": {"type": "array", "items": {"type": "integer"}},
                "dx": {"type": "number"},
                "dz": {"type": "number"},
            },
            "required": ["indices", "dx", "dz"],
        },
    },
    {
        "name": "measure_distance",
        "description": "XZ distance between two object centers.",
        "parameters": {
            "type": "object",
            "properties": {
                "index1": {"type": "integer"},
                "index2": {"type": "integer"},
            },
            "required": ["index1", "index2"],
        },
    },
    {
        "name": "find_objects_in_area",
        "description": "Find objects whose centers are inside an XZ bounding box.",
        "parameters": {
            "type": "object",
            "properties": {
                "x_min": {"type": "number"},
                "z_min": {"type": "number"},
                "x_max": {"type": "number"},
                "z_max": {"type": "number"},
            },
            "required": ["x_min", "z_min", "x_max", "z_max"],
        },
    },
    {
        "name": "check_overlap",
        "description": "AABB overlap check on XZ plane.",
        "parameters": {
            "type": "object",
            "properties": {
                "index1": {"type": "integer"},
                "index2": {"type": "integer"},
            },
            "required": ["index1", "index2"],
        },
    },
    {
        "name": "find_nearest",
        "description": "Find nearest objects by XZ distance.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "count": {"type": "integer", "default": 3},
            },
            "required": ["index"],
        },
    },
    {
        "name": "align_objects",
        "description": "Align multiple objects along X or Z.",
        "parameters": {
            "type": "object",
            "properties": {
                "indices": {"type": "array", "items": {"type": "integer"}},
                "axis": {"type": "string"},
                "reference": {"type": "string", "default": "center"},
            },
            "required": ["indices", "axis"],
        },
    },
    {
        "name": "distribute_objects",
        "description": "Evenly space objects along X or Z.",
        "parameters": {
            "type": "object",
            "properties": {
                "indices": {"type": "array", "items": {"type": "integer"}},
                "axis": {"type": "string"},
            },
            "required": ["indices", "axis"],
        },
    },
    {
        "name": "snap_to_grid",
        "description": "Snap positions to the nearest grid multiple.",
        "parameters": {
            "type": "object",
            "properties": {
                "indices": {"type": "array", "items": {"type": "integer"}},
                "grid_size": {"type": "number", "default": 0.25},
            },
            "required": ["indices"],
        },
    },
    {
        "name": "rename_object",
        "description": "Assign a human-readable label to an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "name": {"type": "string"},
            },
            "required": ["index", "name"],
        },
    },
    {
        "name": "find_by_name",
        "description": "Case-insensitive search on object names.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "tag_room",
        "description": "Assign room label to objects.",
        "parameters": {
            "type": "object",
            "properties": {
                "indices": {"type": "array", "items": {"type": "integer"}},
                "room_name": {"type": "string"},
            },
            "required": ["indices", "room_name"],
        },
    },
    {
        "name": "list_rooms",
        "description": "List room labels and associated objects.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "swap_furniture",
        "description": "Swap furniture type while keeping placement metadata.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "new_type": {"type": "string"},
            },
            "required": ["index", "new_type"],
        },
    },
    {
        "name": "compute_room_area",
        "description": "Compute room area from tagged-object bounds.",
        "parameters": {
            "type": "object",
            "properties": {"room_name": {"type": "string"}},
            "required": ["room_name"],
        },
    },
    {
        "name": "check_sightline",
        "description": "Check whether line-of-sight between two objects is blocked.",
        "parameters": {
            "type": "object",
            "properties": {
                "index_from": {"type": "integer"},
                "index_to": {"type": "integer"},
                "safety_margin": {"type": "number", "default": 0.05},
                "include_hidden": {"type": "boolean", "default": False},
            },
            "required": ["index_from", "index_to"],
        },
    },
    {
        "name": "suggest_furniture_placement",
        "description": "Simulate and return ranked placement candidates for furniture.",
        "parameters": {
            "type": "object",
            "properties": {
                "furniture_type": {"type": "string"},
                "near_index": {"type": "integer"},
                "face_index": {"type": "integer"},
                "room_name": {"type": "string"},
                "min_distance": {"type": "number", "default": 1.0},
                "max_distance": {"type": "number", "default": 4.0},
                "require_clear_sightline": {"type": "boolean", "default": False},
                "max_candidates": {"type": "integer", "default": 5},
                "grid_size": {"type": "number", "default": 0.25},
            },
            "required": ["furniture_type"],
        },
    },
    {
        "name": "auto_place_furniture",
        "description": "Auto-place a furniture item from best simulation candidate.",
        "parameters": {
            "type": "object",
            "properties": {
                "furniture_type": {"type": "string"},
                "near_index": {"type": "integer"},
                "face_index": {"type": "integer"},
                "room_name": {"type": "string"},
                "min_distance": {"type": "number", "default": 1.0},
                "max_distance": {"type": "number", "default": 4.0},
                "require_clear_sightline": {"type": "boolean", "default": False},
                "candidate_rank": {"type": "integer", "default": 1},
                "grid_size": {"type": "number", "default": 0.25},
            },
            "required": ["furniture_type"],
        },
    },
    {
        "name": "simulate_layout_options",
        "description": "Generate multi-object simulated options from vague requirement text.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirement": {"type": "string"},
                "room_name": {"type": "string", "default": ""},
                "max_options": {"type": "integer", "default": 3},
            },
            "required": ["requirement"],
        },
    },
    {
        "name": "apply_simulated_option",
        "description": "Apply one previously simulated option into the live layout.",
        "parameters": {
            "type": "object",
            "properties": {"option_index": {"type": "integer", "default": 1}},
        },
    },
]


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._capture_title = False
        self._capture_snippet = False
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._pending_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        cls = attr.get("class", "")
        if tag == "a" and "result__a" in cls:
            self._capture_title = True
            self._title_parts = []
            self._pending_href = attr.get("href", "")
        elif "result__snippet" in cls:
            self._capture_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
            title = _collapse_ws(" ".join(self._title_parts))
            url = _normalize_result_url(self._pending_href)
            if title and url:
                self.results.append({"title": title, "url": url, "snippet": ""})
        elif self._capture_snippet and tag in {"a", "div"}:
            self._capture_snippet = False
            snippet = _collapse_ws(" ".join(self._snippet_parts))
            if snippet and self.results:
                self.results[-1]["snippet"] = snippet

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        elif self._capture_snippet:
            self._snippet_parts.append(data)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._capture_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif tag == "title":
            self._capture_title = True
            self._title_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title" and self._capture_title:
            self._capture_title = False
            self.title = _collapse_ws(" ".join(self._title_parts))

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        elif self._skip_depth == 0:
            text = _collapse_ws(data)
            if text:
                self.text_parts.append(text)


def _collapse_ws(text: str) -> str:
    return " ".join(text.split())


def _normalize_result_url(url: str) -> str:
    if url.startswith("//"):
        url = f"https:{url}"
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.query:
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return url


def _read_public_url(url: str, *, timeout: int = _WEB_TIMEOUT_SECONDS) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only public http(s) URLs can be fetched.")
    host = parsed.hostname or ""
    if host.lower() == "localhost":
        raise ValueError("Localhost URLs are not allowed for web references.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        raise ValueError("Private network URLs are not allowed for web references.")
    if ip is None:
        try:
            for address in socket.getaddrinfo(host, None):
                resolved_ip = ipaddress.ip_address(address[4][0])
                if (
                    resolved_ip.is_private
                    or resolved_ip.is_loopback
                    or resolved_ip.is_link_local
                    or resolved_ip.is_reserved
                ):
                    raise ValueError("Private network URLs are not allowed for web references.")
        except socket.gaierror:
            pass

    req = UrlRequest(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Haus/0.1"
            )
        },
    )
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - URL is validated above.
        content_type = response.headers.get("content-type", "")
        body = response.read(_MAX_WEB_RESPONSE_BYTES + 1)
    if len(body) > _MAX_WEB_RESPONSE_BYTES:
        raise ValueError("Web reference response was too large.")
    encoding = "utf-8"
    if "charset=" in content_type:
        encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip() or encoding
    return body.decode(encoding, errors="replace"), content_type


def _web_search(query: str, max_results: int = 5) -> str:
    if not _WEB_SEARCH_ENABLED:
        return "Web search is disabled by HAUS_ENABLE_WEB_SEARCH=0."

    query = _collapse_ws(query)
    if not query:
        return "Error: web_search requires a non-empty query."

    limit = max(1, min(int(max_results or 5), 8))
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        html, _ = _read_public_url(search_url)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return f"Error: web_search failed: {exc}"

    parser = _DuckDuckGoResultParser()
    parser.feed(html)
    results = parser.results[:limit]
    if not results:
        return f"No web search results found for: {query}"

    lines = [f"Web search results for: {query}"]
    for idx, result in enumerate(results, start=1):
        lines.append(f"[{idx}] {result['title']}")
        lines.append(f"URL: {result['url']}")
        if result.get("snippet"):
            lines.append(f"Snippet: {result['snippet']}")
    return "\n".join(lines)


def _fetch_web_page(url: str, max_chars: int = 4000) -> str:
    if not _WEB_SEARCH_ENABLED:
        return "Web fetch is disabled by HAUS_ENABLE_WEB_SEARCH=0."

    limit = max(500, min(int(max_chars or 4000), 12000))
    try:
        html, content_type = _read_public_url(url)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return f"Error: fetch_web_page failed: {exc}"

    if "html" not in content_type.lower():
        text = _collapse_ws(html)
        excerpt = text[:limit]
        return f"Fetched {url}\nContent-Type: {content_type}\n\n{excerpt}"

    parser = _VisibleTextParser()
    parser.feed(html)
    text = _collapse_ws(" ".join(parser.text_parts))
    excerpt = text[:limit]
    title = f"Title: {parser.title}\n" if parser.title else ""
    return f"Fetched {url}\n{title}\n{excerpt}"


def _normalize_attachments(raw: Any) -> tuple[list[dict[str, str]], str | None]:
    if raw in (None, ""):
        return [], None
    if not isinstance(raw, list):
        return [], "Attachments must be a list."
    if len(raw) > _MAX_CHAT_ATTACHMENTS:
        return [], f"At most {_MAX_CHAT_ATTACHMENTS} image references can be attached."

    attachments: list[dict[str, str]] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            return [], f"Attachment {idx} must be an object."

        name = _collapse_ws(str(item.get("name", f"reference-{idx}")))[:120] or f"reference-{idx}"
        media_type = str(item.get("mime_type") or item.get("mimeType") or "").lower().strip()
        data = str(item.get("data_base64") or item.get("data") or "").strip()
        data_url = str(item.get("data_url") or item.get("dataUrl") or "").strip()

        if data_url:
            if not data_url.startswith("data:") or ";base64," not in data_url:
                return [], f"Attachment {idx} data_url must be a base64 data URL."
            header, data = data_url.split(",", 1)
            media_type = header.removeprefix("data:").split(";", 1)[0].lower().strip()

        if media_type not in _ALLOWED_IMAGE_MIME_TYPES:
            allowed = ", ".join(sorted(_ALLOWED_IMAGE_MIME_TYPES))
            return [], f"Attachment {idx} must be one of: {allowed}."
        if not data:
            return [], f"Attachment {idx} is missing base64 image data."

        try:
            decoded = base64.b64decode(data, validate=True)
        except Exception:
            return [], f"Attachment {idx} contains invalid base64 image data."
        if len(decoded) > _MAX_ATTACHMENT_BYTES:
            return [], f"Attachment {idx} is larger than {_MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB."

        attachments.append({"name": name, "media_type": media_type, "data": data})

    return attachments, None


def _build_user_content(user_msg: str, attachments: list[dict[str, str]]) -> str | list[dict[str, Any]]:
    if not attachments:
        return user_msg

    lines = [user_msg, "", "Attached visual references to replicate or adapt:"]
    for item in attachments:
        lines.append(f"- {item['name']} ({item['media_type']})")
    lines.append("Use these images as visual references for layout, style, colors, and furniture placement.")

    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(lines)}]
    for item in attachments:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": item["media_type"],
                    "data": item["data"],
                },
            }
        )
    return content


def _redact_history_for_client(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            redacted.append(dict(msg))
            continue

        blocks = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") == "image":
                continue
            blocks.append(block)
        redacted.append({**msg, "content": blocks})
    return redacted


_DISPATCH_RAW: dict[str, Callable[[dict[str, Any]], str]] = {
    "design_room": lambda a: design_room(**a),
    "design_flat": lambda a: design_flat(**a),
    "list_furniture_catalog": lambda a: list_furniture_catalog(),
    "web_search": lambda a: _web_search(**a),
    "fetch_web_page": lambda a: _fetch_web_page(**a),
    "list_objects": lambda a: list_objects(),
    "add_furniture": lambda a: add_furniture(**a),
    "add_wall": lambda a: add_wall(**a),
    "move_object": lambda a: move_object(**a),
    "rotate_object": lambda a: rotate_object(**a),
    "remove_object": lambda a: remove_object(**a),
    "remove_objects_by_type": lambda a: remove_objects_by_type(**a),
    "clear_layout": lambda a: clear_layout(),
    "get_object_details": lambda a: get_object_details(**a),
    "get_layout_summary": lambda a: get_layout_summary(),
    "resize_object": lambda a: resize_object(**a),
    "set_color": lambda a: set_color(**a),
    "set_visibility": lambda a: set_visibility(**a),
    "duplicate_object": lambda a: duplicate_object(**a),
    "batch_move": lambda a: batch_move(**a),
    "measure_distance": lambda a: measure_distance(**a),
    "find_objects_in_area": lambda a: find_objects_in_area(**a),
    "check_overlap": lambda a: check_overlap(**a),
    "find_nearest": lambda a: find_nearest(**a),
    "align_objects": lambda a: align_objects(**a),
    "distribute_objects": lambda a: distribute_objects(**a),
    "snap_to_grid": lambda a: snap_to_grid(**a),
    "rename_object": lambda a: rename_object(**a),
    "find_by_name": lambda a: find_by_name(**a),
    "tag_room": lambda a: tag_room(**a),
    "list_rooms": lambda a: list_rooms(),
    "swap_furniture": lambda a: swap_furniture(**a),
    "compute_room_area": lambda a: compute_room_area(**a),
    "check_sightline": lambda a: check_sightline(**a),
    "suggest_furniture_placement": lambda a: suggest_furniture_placement(**a),
    "auto_place_furniture": lambda a: auto_place_furniture(**a),
    "simulate_layout_options": lambda a: simulate_layout_options(**a),
    "apply_simulated_option": lambda a: apply_simulated_option(**a),
}


def _dispatch(
    name: str,
    args: dict[str, Any],
    *,
    request_id: str,
    tool_log: list[dict[str, Any]],
) -> str:
    fn = _DISPATCH_RAW.get(name)
    start = time.perf_counter()

    if fn is None:
        result = f"Error: unknown tool '{name}'."
    else:
        try:
            result = fn(args)
        except Exception as exc:  # pragma: no cover - defensive for runtime tool failures
            log.exception("[%s] tool failure: %s", request_id, name)
            result = f"Error: tool '{name}' failed: {exc}"

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    entry = {
        "tool": name,
        "args": args,
        "result": result,
        "elapsed_ms": elapsed_ms,
    }
    tool_log.append(entry)

    preview = result[:200] + "..." if len(result) > 200 else result
    log.info("[%s] tool %s(%s) -> %s (%sms)", request_id, name, json.dumps(args), preview, elapsed_ms)
    return result


def _provider_available() -> list[str]:
    providers: list[str] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append("anthropic")
    if os.environ.get("OPENAI_API_KEY"):
        providers.append("openai")
    if os.environ.get("GEMINI_API_KEY"):
        providers.append("gemini")
    return providers


def _load_provider_module(module_name: str, provider_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"{provider_name} support requires optional dependency '{module_name}'. "
            "Install the provider extra before using this model."
        ) from exc


def _chat_anthropic(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    anthropic = _load_provider_module("anthropic", "Anthropic")
    client = anthropic.Anthropic(api_key=api_key)
    tools = [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in _TOOLS_SPEC
    ]

    for _ in range(_MAX_TOOL_STEPS):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM,
            tools=cast(Any, tools),
            messages=messages,
        )

        content: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": dict(block.input),
                    }
                )

        messages.append({"role": "assistant", "content": content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            return text, messages

        results: list[dict[str, Any]] = []
        for tu in tool_uses:
            result = dispatch(tu.name, dict(tu.input))
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result})
        messages.append({"role": "user", "content": results})

    raise RuntimeError("Too many tool iterations")


def _openai_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in _TOOLS_SPEC
    ]


def _image_data_url(block: dict[str, Any]) -> str:
    source = block.get("source")
    if not isinstance(source, dict):
        return ""
    media_type = str(source.get("media_type", "")).strip()
    data = str(source.get("data", "")).strip()
    if not media_type or not data:
        return ""
    return f"data:{media_type};base64,{data}"


def _to_oai_user_content(content: list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    has_image = False
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            text = str(block.get("text", ""))
            if text:
                blocks.append({"type": "text", "text": text})
        elif block_type == "image":
            data_url = _image_data_url(block)
            if data_url:
                has_image = True
                blocks.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})

    if not has_image:
        return "\n".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text")
    return blocks


def _to_oai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    oai: list[dict[str, Any]] = [{"role": "system", "content": _SYSTEM}]

    for msg in messages:
        role = str(msg.get("role", "user"))
        content = msg.get("content")

        if isinstance(content, str):
            oai.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            continue

        if role == "assistant":
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(texts) if texts else None,
            }
            if tool_uses:
                entry["tool_calls"] = [
                    {
                        "id": tu["id"],
                        "type": "function",
                        "function": {
                            "name": tu["name"],
                            "arguments": json.dumps(tu.get("input", {})),
                        },
                    }
                    for tu in tool_uses
                ]
            oai.append(entry)
            continue

        if role == "user" and content and content[0].get("type") == "tool_result":
            for block in content:
                oai.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block["content"],
                    }
                )
            continue

        if role == "user":
            oai.append({"role": role, "content": _to_oai_user_content(content)})
        else:
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            oai.append({"role": role, "content": "\n".join(texts) if texts else ""})

    return oai


def _chat_openai(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    openai = _load_provider_module("openai", "OpenAI")
    client = openai.OpenAI(api_key=api_key)
    tools = _openai_tools()
    oai_messages = _to_oai_messages(messages)

    for _ in range(_MAX_TOOL_STEPS):
        response = client.chat.completions.create(
            model=model,
            messages=oai_messages,
            tools=cast(Any, tools),
            max_tokens=1024,
        )

        msg = response.choices[0].message
        tool_calls = cast(list[Any], msg.tool_calls or [])

        if not tool_calls:
            text = msg.content or ""
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages

        assistant_content: list[dict[str, Any]] = []
        oai_messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        if msg.content:
            assistant_content.append({"type": "text", "text": msg.content})

        tool_results: list[dict[str, Any]] = []
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            result = dispatch(tc.function.name, args)
            oai_messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            assistant_content.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": args,
                }
            )
            tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Too many tool iterations")


def _chat_gemini(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    genai = _load_provider_module("google.generativeai", "Google Gemini")
    genai.configure(api_key=api_key)

    func_decls = []
    for tool in _TOOLS_SPEC:
        params = tool["parameters"].get("properties", {})
        required = tool["parameters"].get("required", [])

        schema_params: dict[str, Any] = {}
        for name, spec in params.items():
            gtype = "STRING"
            ptype = spec.get("type")
            if ptype == "number":
                gtype = "NUMBER"
            elif ptype == "integer":
                gtype = "INTEGER"
            elif ptype == "boolean":
                gtype = "BOOLEAN"
            elif ptype == "array":
                gtype = "ARRAY"

            schema_params[name] = {
                "type_": gtype,
                "description": spec.get("description", ""),
            }

        schema = None
        if schema_params:
            schema = genai.protos.Schema(
                type_=genai.protos.Type.OBJECT,
                properties={
                    k: genai.protos.Schema(
                        type_=getattr(genai.protos.Type, v["type_"]),
                        description=v["description"],
                    )
                    for k, v in schema_params.items()
                },
                required=required,
            )

        func_decls.append(
            genai.protos.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=schema,
            )
        )

    tool_config = genai.protos.Tool(function_declarations=func_decls)
    gmodel = genai.GenerativeModel(model, system_instruction=_SYSTEM, tools=[tool_config])

    def gemini_parts(content: Any) -> list[Any]:
        if isinstance(content, str):
            return [content]
        if not isinstance(content, list):
            return []

        parts: list[Any] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = str(block.get("text", ""))
                if text:
                    parts.append(text)
            elif block.get("type") == "image":
                source = block.get("source")
                if not isinstance(source, dict):
                    continue
                data = str(source.get("data", ""))
                media_type = str(source.get("media_type", ""))
                if data and media_type:
                    parts.append({"mime_type": media_type, "data": base64.b64decode(data)})
        return parts

    history: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list) and content and content[0].get("type") == "tool_result":
            continue
        parts = gemini_parts(content)
        if parts:
            history.append({"role": "user" if msg["role"] == "user" else "model", "parts": parts})

    chat = gmodel.start_chat(history=history[:-1] if len(history) > 1 else [])
    last_msg = history[-1]["parts"] if history else ""

    for _ in range(_MAX_TOOL_STEPS):
        response = chat.send_message(last_msg)
        candidate = response.candidates[0]
        parts = candidate.content.parts

        func_calls = [part for part in parts if part.function_call and part.function_call.name]
        if not func_calls:
            text = "".join(part.text for part in parts if part.text)
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages

        func_responses = []
        for call in func_calls:
            args = dict(call.function_call.args)
            result = dispatch(call.function_call.name, args)
            func_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=call.function_call.name,
                        response={"result": result},
                    )
                )
            )

        last_msg = func_responses

    raise RuntimeError("Too many tool iterations")


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
}

_CHAT_FNS: dict[
    str,
    Callable[[str, list[dict[str, Any]], str, Callable[[str, dict[str, Any]], str]], tuple[str, list[dict[str, Any]]]],
] = {
    "anthropic": _chat_anthropic,
    "openai": _chat_openai,
    "gemini": _chat_gemini,
}

_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _sanitize_history(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for msg in raw:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user"))
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
        elif isinstance(content, list):
            blocks = []
            for block in content:
                if not isinstance(block, dict) or block.get("type") == "image":
                    continue
                blocks.append(block)
            out.append({"role": role, "content": blocks})
    return out


async def _chat_status(request: Request) -> JSONResponse:
    providers = _provider_available()
    return JSONResponse(
        {
            "available": True,
            "providers_with_env_keys": providers,
            "supported_providers": list(_CHAT_FNS.keys()),
            "default_models": _DEFAULT_MODELS,
            "capabilities": {
                "web_search": _WEB_SEARCH_ENABLED,
                "web_fetch": _WEB_SEARCH_ENABLED,
                "image_references": True,
                "max_image_attachments": _MAX_CHAT_ATTACHMENTS,
                "max_image_attachment_mb": _MAX_ATTACHMENT_BYTES // (1024 * 1024),
                "image_mime_types": sorted(_ALLOWED_IMAGE_MIME_TYPES),
            },
        }
    )


async def _chat(request: Request) -> JSONResponse:
    request_id = new_request_id("chat")

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body.", "request_id": request_id}, 400)

    user_msg = str(body.get("message", "")).strip()
    history = _sanitize_history(body.get("history", []))
    provider = str(body.get("provider", "")).strip().lower()
    model_override = str(body.get("model", "")).strip()
    client_key = str(body.get("api_key", "")).strip()
    attachments, attachment_error = _normalize_attachments(body.get("attachments", []))

    if not user_msg:
        return JSONResponse({"error": "Message must not be empty.", "request_id": request_id}, 400)
    if attachment_error:
        return JSONResponse({"error": attachment_error, "request_id": request_id}, 400)

    if provider not in _CHAT_FNS:
        return JSONResponse(
            {
                "error": f"Provider '{provider}' not supported.",
                "supported": list(_CHAT_FNS.keys()),
                "request_id": request_id,
            },
            400,
        )

    api_key = client_key or os.environ.get(_ENV_KEYS[provider], "")
    if not api_key:
        return JSONResponse(
            {
                "error": f"No API key for {provider}. Add one in chat settings.",
                "request_id": request_id,
            },
            400,
        )

    model = model_override or _DEFAULT_MODELS[provider]
    tool_log: list[dict[str, Any]] = []
    messages = history + [{"role": "user", "content": _build_user_content(user_msg, attachments)}]

    def dispatch(name: str, args: dict[str, Any]) -> str:
        return _dispatch(name, args, request_id=request_id, tool_log=tool_log)

    log.info("[%s] chat request provider=%s model=%s", request_id, provider, model)

    try:
        text, updated_history = _CHAT_FNS[provider](api_key, messages, model, dispatch)
        return JSONResponse(
            {
                "response": text,
                "history": _redact_history_for_client(updated_history),
                "provider": provider,
                "model": model,
                "actions": tool_log,
                "request_id": request_id,
            }
        )
    except Exception as exc:
        log.exception("[%s] chat error", request_id)
        return JSONResponse({"error": str(exc), "request_id": request_id}, 500)


async def _sync_layout(request: Request) -> JSONResponse:
    request_id = new_request_id("sync")

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body.", "request_id": request_id}, 400)

    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Layout payload must be a JSON object.", "request_id": request_id}, 400)

    if "items" not in body:
        return JSONResponse({"ok": False, "error": "Missing 'items' in layout payload.", "request_id": request_id}, 400)

    err = _save_layout(body)
    if err:
        log.error("[%s] sync failed: %s", request_id, err)
        return JSONResponse({"ok": False, "error": err, "request_id": request_id}, 500)

    log.info("[%s] layout synced (%s items)", request_id, len(body.get("items", [])))
    return JSONResponse({"ok": True, "request_id": request_id})


async def _mcp_clear_layout(_: Request) -> JSONResponse:
    request_id = new_request_id("mcp-clear")
    result = clear_layout()
    ok = not result.startswith("Error")

    if ok:
        log.info("[%s] mcp clear_layout -> %s", request_id, result)
    else:
        log.error("[%s] mcp clear_layout failed -> %s", request_id, result)

    return JSONResponse(
        {"ok": ok, "result": result, "request_id": request_id},
        200 if ok else 500,
    )


def create_app(root_dir: str) -> Starlette:
    return Starlette(
        routes=[
            Route("/api/chat/status", _chat_status, methods=["GET"]),
            Route("/api/chat", _chat, methods=["POST"]),
            Route("/api/sync-layout", _sync_layout, methods=["POST"]),
            Route("/api/mcp/clear-layout", _mcp_clear_layout, methods=["POST"]),
            Mount("/", StaticFiles(directory=root_dir, html=True)),
        ]
    )


def run_server(root_dir: str, port: int = 8080, layout_path: str | None = None) -> None:
    os.environ["_HAUS_ROOT"] = root_dir
    if layout_path is not None:
        os.environ["_HAUS_LAYOUT_PATH"] = layout_path
        _mcp_server.LAYOUT_PATH = Path(layout_path)
    configure_logging("haus.chat")
    uvicorn.run(
        "haus.chat_server:_reload_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        reload=True,
        reload_dirs=[str(Path(__file__).resolve().parent)],
    )


def _reload_app() -> Starlette:
    layout_path = os.environ.get("_HAUS_LAYOUT_PATH")
    if layout_path:
        _mcp_server.LAYOUT_PATH = Path(layout_path)
    return create_app(os.environ["_HAUS_ROOT"])
