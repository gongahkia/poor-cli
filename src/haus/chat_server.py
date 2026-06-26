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
import re
import socket
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, parse_qsl, quote_plus, urlencode, unquote, urlparse, urlunparse
from urllib.request import Request as UrlRequest, urlopen

from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn

from . import mcp_server as _mcp_server
from . import geometry
from .agent_loop import RoomPlan, plan_flat, plan_room
from .catalog import catalog_item_to_layout_item, catalog_search_meta, get_catalog_item, search_ikea_catalog
from .llm import DEFAULT_MODELS, ENV_KEYS, provider_specs, provider_status, providers_with_env_keys, resolve_model, supported_provider_ids
from .llm.providers import anthropic as anthropic_provider
from .llm.providers import gemini as gemini_provider
from .llm.providers import local_cli as local_cli_provider
from .llm.providers import ollama as ollama_provider
from .llm.providers import openai as openai_provider
from .llm.providers import openai_compatible as openai_compatible_provider
from .llm.types import ChatChunk
from .logging_utils import configure_logging, new_request_id
from .pipeline import run_vectorize
from .types import VectorizeConfig
from .mcp_server import (
    _coerce_float,
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
    score_layout,
    set_color,
    set_visibility,
    simulate_layout_options,
    snap_to_grid,
    score_walkway,
    suggest_furniture_placement,
    swap_furniture,
    tag_room,
    get_semantic_layout_json,
    bim_readiness_report,
    search_ikea_catalog as search_ikea_catalog_tool,
    get_ikea_catalog_item,
    add_catalog_furniture,
    refresh_ikea_catalog,
)
from .room_capture import build_room_capture_layout
from .workbench import validate_layout_schema

log = configure_logging("haus.chat")

mimetypes.add_type("model/gltf-binary", ".glb")

_MAX_TOOL_STEPS = 12
_MAX_CHAT_ATTACHMENTS = 3
_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
_MAX_FLOORPLAN_BYTES = 15 * 1024 * 1024
_ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_ALLOWED_FLOORPLAN_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_FLOORPLAN_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_WEB_TIMEOUT_SECONDS = 8
_MAX_WEB_RESPONSE_BYTES = 1_000_000
_SEARCH_PROVIDER_DEFAULTS = ("serper", "exa", "tinyfish", "duckduckgo")
_PLANNER_MODES = {"auto", "deterministic", "llm_reviewed", "llm_structured"}
_DEFAULT_STANDARDS_PROFILE = "apartment_compact"
_SEARCH_PROVIDER_KEY_ENV = {
    "serper": "SERPER_API_KEY",
    "exa": "EXA_API_KEY",
    "tinyfish": "TINYFISH_API_KEY",
}
_TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
}
_MAX_DESIGN_PLANS = 20
_DESIGN_PLAN_CACHE: dict[str, dict[str, Any]] = {}
_DESIGN_PLAN_ORDER: list[str] = []
_MAX_TOOL_CONFIRMATIONS = 20
_TOOL_CONFIRMATION_TTL_SECONDS = 10 * 60
_TOOL_CONFIRMATION_CACHE: dict[str, dict[str, Any]] = {}
_TOOL_CONFIRMATION_ORDER: list[str] = []

_CONCEPT_ACTION_RE = re.compile(
    r"\b(build|create|design|draft|generate|layout|make|plan|renovate|replicate|rework|style)\b",
    re.IGNORECASE,
)
_CONCEPT_ATTACHMENT_RE = re.compile(
    r"\b(build|create|design|draft|generate|layout|plan|renovate|replicate|rework|style)\b",
    re.IGNORECASE,
)
_CONCEPT_DOMAIN_RE = re.compile(
    r"\b("
    r"apartment|bathroom|bedroom|bto|condo|dining|flat|floor\s*plan|floorplan|furniture|haus|hdb|"
    r"home|house|interior|kitchen|layout|living|office|renovation|room|space|study"
    r")\b",
    re.IGNORECASE,
)

_SYSTEM = (
    "You are an AI assistant for the haus floor plan editor. "
    "You ONLY help with floor plan editing — arranging furniture, walls, and layout. "
    "You may use live web references when they support interior design, furniture, uploaded floor plans, HDB/BTO, "
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
    "- Use web_search for current design/product/local-housing references when the user asks for current, "
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
                "style_prompt": {"type": "string", "default": "minimalist apartment"},
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
        "name": "search_ikea_catalog",
        "description": "Search IKEA products through TinyFish when configured, with local cache fallback.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 8},
                "region": {"type": "string", "default": "sg"},
                "refresh": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_ikea_catalog_item",
        "description": "Return one cached IKEA catalog item as JSON.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "refresh": {"type": "boolean", "default": False},
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "add_catalog_furniture",
        "description": "Place a cached IKEA catalog item as editable furniture.",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "x": {"type": "number", "default": 0},
                "z": {"type": "number", "default": 0},
                "rotation_deg": {"type": "number", "default": 0},
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "refresh_ikea_catalog",
        "description": "Force a TinyFish-backed IKEA catalog search and refresh local cache.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 12},
                "region": {"type": "string", "default": "sg"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the live web for current interior design, furniture, floor-plan, renovation, "
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
    {
        "name": "score_walkway",
        "description": "Score a primary walkway/corridor between two XZ points.",
        "parameters": {
            "type": "object",
            "properties": {
                "x1": {"type": "number"},
                "z1": {"type": "number"},
                "x2": {"type": "number"},
                "z2": {"type": "number"},
                "min_width": {"type": "number", "default": 0.9},
            },
            "required": ["x1", "z1", "x2", "z2"],
        },
    },
    {
        "name": "score_layout",
        "description": "Score the full layout against a usability standards profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "profile": {
                    "type": "string",
                    "default": "apartment_compact",
                    "description": "One of apartment_compact, comfortable_home, accessible, rental_room, hdb_bto, kitchen_basic, bedroom_basic, bathroom_basic.",
                }
            },
        },
    },
    {
        "name": "get_semantic_layout_json",
        "description": "Return semantic JSON for future BIM/IFC mapping and export validation.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "bim_readiness_report",
        "description": "Report what is and is not ready for BIM/IFC-style interoperability.",
        "parameters": {"type": "object", "properties": {}},
    },
]

_TOOL_SAFETY: dict[str, str] = {
    "design_room": "mutating",
    "design_flat": "mutating",
    "add_furniture": "mutating",
    "add_catalog_furniture": "mutating",
    "add_wall": "mutating",
    "move_object": "mutating",
    "rotate_object": "mutating",
    "resize_object": "mutating",
    "set_color": "mutating",
    "set_visibility": "mutating",
    "duplicate_object": "mutating",
    "batch_move": "mutating",
    "align_objects": "mutating",
    "distribute_objects": "mutating",
    "snap_to_grid": "mutating",
    "rename_object": "mutating",
    "tag_room": "mutating",
    "swap_furniture": "mutating",
    "auto_place_furniture": "mutating",
    "apply_simulated_option": "mutating",
    "remove_object": "destructive",
    "remove_objects_by_type": "destructive",
    "clear_layout": "destructive",
}


def _tool_safety(name: str) -> str:
    return _TOOL_SAFETY.get(name, "read")


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    strict = json.loads(json.dumps(schema))

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)
            for child in node.get("properties", {}).values():
                visit(child)
        if node.get("type") == "array":
            visit(node.get("items"))

    visit(strict)
    return strict


def _strict_tool_spec(tool: dict[str, Any]) -> dict[str, Any]:
    return {**tool, "parameters": _strict_schema(cast(dict[str, Any], tool["parameters"]))}


_TOOLS_SPEC = [_strict_tool_spec(tool) for tool in _TOOLS_SPEC]
_TOOL_SPEC_BY_NAME = {str(tool["name"]): tool for tool in _TOOLS_SPEC}


def _schema_type_error(path: str, expected: str, value: Any) -> str | None:
    if expected == "string":
        ok = isinstance(value, str)
    elif expected == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif expected == "boolean":
        ok = isinstance(value, bool)
    elif expected == "array":
        ok = isinstance(value, list)
    elif expected == "object":
        ok = isinstance(value, dict)
    else:
        ok = True
    if ok:
        return None
    return f"{path} must be {expected}, got {type(value).__name__}."


def _validate_schema_value(schema: dict[str, Any], value: Any, path: str) -> str | None:
    expected = schema.get("type")
    if isinstance(expected, str):
        if err := _schema_type_error(path, expected, value):
            return err

    if expected == "array":
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                if err := _validate_schema_value(item_schema, item, f"{path}[{idx}]"):
                    return err

    if expected == "object":
        if not isinstance(value, dict):
            return f"{path} must be object."
        properties = schema.get("properties", {})
        if isinstance(properties, dict) and schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                return f"{path} has unknown field(s): {', '.join(unknown)}."
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = [str(key) for key in required if key not in value]
            if missing:
                return f"{path} missing required field(s): {', '.join(missing)}."
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    if err := _validate_schema_value(child_schema, value[key], f"{path}.{key}"):
                        return err
    return None


def _validate_tool_args(name: str, args: Any) -> tuple[dict[str, Any], str | None]:
    if not isinstance(args, dict):
        return {}, "Tool arguments must be a JSON object."
    tool = _TOOL_SPEC_BY_NAME.get(name)
    if tool is None:
        return dict(args), None
    schema = cast(dict[str, Any], tool["parameters"])
    required = set(str(item) for item in schema.get("required", []) if isinstance(item, str))
    args = {key: value for key, value in args.items() if value is not None or key in required}
    if err := _validate_schema_value(schema, args, "args"):
        return {}, err
    return dict(args), None


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


def _web_search_enabled() -> bool:
    return os.environ.get("HAUS_ENABLE_WEB_SEARCH", "1").lower() not in {"0", "false", "no"}


def _configured_search_providers() -> list[str]:
    raw = os.environ.get("HAUS_SEARCH_PROVIDERS", ",".join(_SEARCH_PROVIDER_DEFAULTS))
    providers: list[str] = []
    for name in raw.split(","):
        normalized = name.strip().lower()
        if normalized in _SEARCH_PROVIDER_DEFAULTS and normalized not in providers:
            providers.append(normalized)
    return providers or ["duckduckgo"]


def _available_search_providers() -> list[str]:
    if not _web_search_enabled():
        return []

    available: list[str] = []
    for provider in _configured_search_providers():
        key_env = _SEARCH_PROVIDER_KEY_ENV.get(provider)
        if key_env is None or os.environ.get(key_env):
            available.append(provider)
    return available


def _validate_public_reference_url(url: str) -> None:
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


def _read_public_url(url: str, *, timeout: int = _WEB_TIMEOUT_SECONDS) -> tuple[str, str]:
    _validate_public_reference_url(url)

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


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req_headers = {
        "User-Agent": "Haus/0.1",
        **(headers or {}),
    }
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")

    req = UrlRequest(url, data=body, headers=req_headers, method=method)
    with urlopen(req, timeout=_WEB_TIMEOUT_SECONDS) as response:  # noqa: S310 - provider URLs are fixed.
        raw = response.read(_MAX_WEB_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_WEB_RESPONSE_BYTES:
        raise ValueError("Search provider response was too large.")
    return json.loads(raw.decode("utf-8", errors="replace"))


def _canonical_url(url: str) -> str:
    normalized = _normalize_result_url(url.strip())
    parsed = urlparse(normalized)
    if not parsed.scheme or not parsed.netloc:
        return normalized

    query_pairs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower = key.lower()
        if lower.startswith("utm_") or lower in _TRACKING_QUERY_PARAMS:
            continue
        query_pairs.append((key, value))

    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(sorted(query_pairs)),
            "",
        )
    )


def _normalize_reference(
    *,
    title: Any,
    url: Any,
    snippet: Any = "",
    source_provider: str,
    published_date: Any = None,
) -> dict[str, Any] | None:
    normalized_url = _normalize_result_url(str(url or "").strip())
    if not normalized_url:
        return None

    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    clean_title = _collapse_ws(str(title or "")) or parsed.netloc
    clean_snippet = _collapse_ws(str(snippet or ""))
    published = _collapse_ws(str(published_date or "")) or None

    return {
        "title": clean_title[:240],
        "url": normalized_url,
        "snippet": clean_snippet[:800],
        "source_provider": source_provider,
        "published_date": published,
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _dedupe_references(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        key = _canonical_url(str(result.get("url", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _search_duckduckgo(query: str, max_results: int) -> list[dict[str, Any]]:
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html, _ = _read_public_url(search_url)
    parser = _DuckDuckGoResultParser()
    parser.feed(html)

    results: list[dict[str, Any]] = []
    for result in parser.results[:max_results]:
        normalized = _normalize_reference(
            title=result.get("title"),
            url=result.get("url"),
            snippet=result.get("snippet"),
            source_provider="duckduckgo",
        )
        if normalized:
            results.append(normalized)
    return results


def _search_serper(query: str, max_results: int) -> list[dict[str, Any]]:
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return []

    data = _request_json(
        "https://google.serper.dev/search",
        method="POST",
        payload={"q": query, "num": max_results},
        headers={"X-API-KEY": api_key},
    )
    raw_results = data.get("organic", []) if isinstance(data, dict) else []
    results: list[dict[str, Any]] = []
    if isinstance(raw_results, list):
        for result in raw_results[:max_results]:
            if not isinstance(result, dict):
                continue
            normalized = _normalize_reference(
                title=result.get("title"),
                url=result.get("link") or result.get("url"),
                snippet=result.get("snippet") or result.get("description"),
                source_provider="serper",
                published_date=result.get("date"),
            )
            if normalized:
                results.append(normalized)
    return results


def _search_exa(query: str, max_results: int) -> list[dict[str, Any]]:
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        return []

    data = _request_json(
        "https://api.exa.ai/search",
        method="POST",
        payload={"query": query, "numResults": max_results, "contents": {"text": True}},
        headers={"x-api-key": api_key},
    )
    raw_results = data.get("results", []) if isinstance(data, dict) else []
    results: list[dict[str, Any]] = []
    if isinstance(raw_results, list):
        for result in raw_results[:max_results]:
            if not isinstance(result, dict):
                continue
            normalized = _normalize_reference(
                title=result.get("title"),
                url=result.get("url"),
                snippet=result.get("text") or result.get("summary") or result.get("snippet"),
                source_provider="exa",
                published_date=result.get("publishedDate") or result.get("published_date"),
            )
            if normalized:
                results.append(normalized)
    return results


def _tinyfish_result_list(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("results", "data", "items", "organic"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _search_tinyfish(query: str, max_results: int) -> list[dict[str, Any]]:
    api_key = os.environ.get("TINYFISH_API_KEY")
    if not api_key:
        return []

    data = _request_json(
        f"https://api.search.tinyfish.ai?{urlencode({'query': query, 'limit': max_results})}",
        headers={"X-API-Key": api_key},
    )
    results: list[dict[str, Any]] = []
    for result in _tinyfish_result_list(data)[:max_results]:
        if not isinstance(result, dict):
            continue
        normalized = _normalize_reference(
            title=result.get("title") or result.get("name"),
            url=result.get("url") or result.get("link"),
            snippet=result.get("snippet") or result.get("description") or result.get("text"),
            source_provider="tinyfish",
            published_date=result.get("published_date") or result.get("publishedDate") or result.get("date"),
        )
        if normalized:
            results.append(normalized)
    return results


_SEARCH_FNS: dict[str, Callable[[str, int], list[dict[str, Any]]]] = {
    "serper": _search_serper,
    "exa": _search_exa,
    "tinyfish": _search_tinyfish,
    "duckduckgo": _search_duckduckgo,
}


def search_references(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    if not _web_search_enabled():
        return []

    query = _collapse_ws(query)
    if not query:
        return []

    limit = max(1, min(int(max_results or 5), 8))
    results: list[dict[str, Any]] = []
    for provider in _available_search_providers():
        fn = _SEARCH_FNS.get(provider)
        if fn is None:
            continue
        try:
            results.extend(fn(query, limit))
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            log.warning("search provider %s failed: %s", provider, exc)
        results = _dedupe_references(results)
        if len(results) >= limit:
            break
    return results[:limit]


def _format_reference_results(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return f"No web search results found for: {query}"

    lines = [f"Web search results for: {query}"]
    for idx, result in enumerate(results, start=1):
        lines.append(f"[{idx}] {result['title']}")
        lines.append(f"URL: {result['url']}")
        lines.append(f"Provider: {result['source_provider']}")
        if result.get("published_date"):
            lines.append(f"Published: {result['published_date']}")
        if result.get("snippet"):
            lines.append(f"Snippet: {result['snippet']}")
    return "\n".join(lines)


def _web_search(query: str, max_results: int = 5) -> str:
    if not _web_search_enabled():
        return "Web search is disabled by HAUS_ENABLE_WEB_SEARCH=0."

    query = _collapse_ws(query)
    if not query:
        return "Error: web_search requires a non-empty query."

    try:
        results = search_references(query, max_results=max_results)
    except Exception as exc:  # pragma: no cover - provider failures are defensive.
        return f"Error: web_search failed: {exc}"
    return _format_reference_results(query, results)


def _fetch_with_tinyfish(url: str, max_chars: int) -> str | None:
    api_key = os.environ.get("TINYFISH_API_KEY")
    if not api_key or "tinyfish" not in _available_search_providers():
        return None

    _validate_public_reference_url(url)
    data = _request_json(
        "https://api.fetch.tinyfish.ai",
        method="POST",
        payload={"url": url},
        headers={"X-API-Key": api_key},
    )
    if not isinstance(data, dict):
        return None

    title = _collapse_ws(str(data.get("title") or ""))
    text = _collapse_ws(
        str(
            data.get("text")
            or data.get("markdown")
            or data.get("content")
            or data.get("body")
            or data.get("html")
            or ""
        )
    )
    if not text:
        return None

    title_line = f"Title: {title}\n" if title else ""
    return f"Fetched {url}\nProvider: tinyfish\n{title_line}\n{text[:max_chars]}"


def _fetch_web_page(url: str, max_chars: int = 4000) -> str:
    if not _web_search_enabled():
        return "Web fetch is disabled by HAUS_ENABLE_WEB_SEARCH=0."

    limit = max(500, min(int(max_chars or 4000), 12000))
    try:
        tinyfish_result = _fetch_with_tinyfish(url, limit)
        if tinyfish_result:
            return tinyfish_result
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        log.warning("tinyfish fetch failed: %s", exc)

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


def _is_concept_request(user_msg: str, attachments: list[dict[str, str]]) -> bool:
    if attachments and _CONCEPT_ATTACHMENT_RE.search(user_msg):
        return True
    return bool(_CONCEPT_ACTION_RE.search(user_msg) and _CONCEPT_DOMAIN_RE.search(user_msg))


def _parse_revision_request(user_msg: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*revise\s+plan\s+([A-Za-z0-9_-]+)\s*:?\s*(.*)$", user_msg, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return match.group(1), _collapse_ws(match.group(2)) or "Refine the existing plan while keeping the original intent."


def _design_scope_from_brief(brief: str) -> str:
    text = brief.lower()
    if re.search(r"\b(whole|entire|full|flat|apartment|home|house|hdb|bto|condo|studio|3-room|4-room|5-room)\b", text):
        return "whole_flat"
    return "room"


def _room_id_from_brief(brief: str) -> str:
    text = brief.lower()
    room_keywords = [
        ("kitchen", "Kitchen"),
        ("dining", "Dining"),
        ("master", "Master Bedroom"),
        ("bedroom", "Bedroom"),
        ("study", "Study"),
        ("office", "Study"),
        ("bathroom", "Bathroom"),
        ("living", "Living"),
    ]
    for keyword, room_name in room_keywords:
        if keyword in text:
            return room_name
    return "Living"


def _layout_bounds_dict(bounds: tuple[float, float, float, float]) -> dict[str, float]:
    x_min, z_min, x_max, z_max = bounds
    return {
        "x_min": round(x_min, 3),
        "z_min": round(z_min, 3),
        "x_max": round(x_max, 3),
        "z_max": round(z_max, 3),
    }


def _bounds_dict(bounds: tuple[float, float, float, float] | None) -> dict[str, float] | None:
    if bounds is None:
        return None
    return _layout_bounds_dict(bounds)


def _planned_furniture(plan: RoomPlan) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for spec in plan.items:
        catalog_spec = _mcp_server.FURNITURE_CATALOG.get(spec.furniture_type, {})
        items.append(
            {
                "label": spec.name or spec.furniture_type,
                "furniture_type": spec.furniture_type,
                "x": round(plan.origin_x + spec.dx, 3),
                "z": round(plan.origin_z + spec.dz, 3),
                "rotation_deg": round(spec.rotation_deg, 1),
                "width_m": catalog_spec.get("w"),
                "depth_m": catalog_spec.get("d"),
            }
        )
    return items


def _estimate_zone_area(plan: RoomPlan) -> float:
    if not plan.items:
        return 0.0

    x_values: list[float] = []
    z_values: list[float] = []
    for spec in plan.items:
        catalog_spec = _mcp_server.FURNITURE_CATALOG.get(spec.furniture_type, {})
        width = float(catalog_spec.get("w", 1.0))
        depth = float(catalog_spec.get("d", 1.0))
        x = plan.origin_x + spec.dx
        z = plan.origin_z + spec.dz
        x_values.extend([x - width / 2, x + width / 2])
        z_values.extend([z - depth / 2, z + depth / 2])

    width_m = max(x_values) - min(x_values) + 1.0
    depth_m = max(z_values) - min(z_values) + 1.0
    return round(max(0.0, width_m * depth_m), 2)


def _room_plan_to_zone(plan: RoomPlan) -> dict[str, Any]:
    planned = _planned_furniture(plan)
    return {
        "name": plan.room_id,
        "intent": plan.room_kind.replace("_", " "),
        "target_center": {"x": round(plan.origin_x, 3), "z": round(plan.origin_z, 3)},
        "bounds": _bounds_dict(plan.bounds),
        "polygon": [{"x": round(x, 3), "z": round(z, 3)} for x, z in plan.room_polygon or ()],
        "zone_source": plan.zone_source,
        "planned_furniture": planned,
        "estimated_area_m2": _estimate_zone_area(plan),
        "circulation_notes": "Keep the selected profile's primary walkway target and preserve direct access to seating, storage, and work surfaces.",
    }


def _planned_item_records(room_plans: list[RoomPlan]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for plan in room_plans:
        for item in _planned_furniture(plan):
            records.append({"room": plan.room_id, **item})
    return records


def _furniture_footprint_m2(room_plans: list[RoomPlan]) -> float:
    total = 0.0
    for plan in room_plans:
        for spec in plan.items:
            catalog_spec = _mcp_server.FURNITURE_CATALOG.get(spec.furniture_type, {})
            total += float(catalog_spec.get("w", 1.0)) * float(catalog_spec.get("d", 1.0))
    return round(total, 2)


def _draft_room_plans(brief: str, scope: str) -> tuple[list[RoomPlan], tuple[float, float, float, float], int]:
    data = _mcp_server._load_layout()
    bounds = _mcp_server._layout_bounds(data)
    if scope == "whole_flat":
        room_zones = _mcp_server._layout_room_zones(data)
        return (
            plan_flat(
                style_prompt=brief,
                constraints="Concept plan only; maintain 0.75m circulation and avoid collisions on apply.",
                target="whole_flat",
                bounds=bounds,
                room_zones=room_zones,
            ),
            bounds,
            len(data["items"]),
        )

    x_min, z_min, x_max, z_max = bounds
    room_id = _room_id_from_brief(brief)
    zone = _mcp_server._find_room_zone(data, room_id)
    origin_x = (x_min + x_max) / 2
    origin_z = (z_min + z_max) / 2
    room_bounds = None
    zone_source = "inferred"
    if zone is not None:
        origin_x, origin_z = zone.center
        room_bounds = zone.bounds
        zone_source = zone.source

    return (
        [
            plan_room(
                room_id=room_id,
                style_prompt=brief,
                constraints="Concept plan only; maintain 0.75m circulation and avoid collisions on apply.",
                origin_x=origin_x,
                origin_z=origin_z,
                bounds=room_bounds,
                zone_source=zone_source,
                room_polygon=zone.polygon if zone is not None else None,
            )
        ],
        bounds,
        len(data["items"]),
    )


def _cache_design_plan(plan: dict[str, Any]) -> None:
    plan_id = str(plan["id"])
    _DESIGN_PLAN_CACHE[plan_id] = plan
    if plan_id in _DESIGN_PLAN_ORDER:
        _DESIGN_PLAN_ORDER.remove(plan_id)
    _DESIGN_PLAN_ORDER.append(plan_id)

    while len(_DESIGN_PLAN_ORDER) > _MAX_DESIGN_PLANS:
        old_id = _DESIGN_PLAN_ORDER.pop(0)
        _DESIGN_PLAN_CACHE.pop(old_id, None)


def _public_design_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if not key.startswith("_")}


def _design_search_query(brief: str) -> str:
    return f"{brief} interior design floor plan furniture dimensions circulation"


def _resolve_planner_mode(requested: str, provider: str, api_key: str) -> tuple[str, str | None]:
    mode = requested.strip().lower().replace("-", "_").replace(" ", "_") or "auto"
    if mode not in _PLANNER_MODES:
        mode = "auto"
    if mode == "auto":
        return ("llm_reviewed", None) if provider in _CHAT_FNS and api_key else ("deterministic", None)
    if mode.startswith("llm") and (provider not in _CHAT_FNS or not api_key):
        return "deterministic", f"Requested {mode}, but no provider credential was available; used deterministic planner."
    return mode, None


def _planner_label(mode: str) -> str:
    labels = {
        "deterministic": "Deterministic Haus room-kit planner",
        "llm_reviewed": "LLM-reviewed Haus planner",
        "llm_structured": "LLM-structured draft with Haus validation",
    }
    return labels.get(mode, labels["deterministic"])


def _extract_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _run_plan_llm_review(
    *,
    provider: str,
    api_key: str,
    model: str,
    mode: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    prompt = (
        "Review this Haus interior layout concept for real-user usability. "
        "Do not call tools. Be direct about unsupported requests, circulation risks, "
        "room-fit issues, and next revisions. "
        "For llm_structured mode, return concise JSON first if possible, then prose.\n\n"
        f"Planner mode: {mode}\n"
        f"Plan JSON:\n{json.dumps(_public_design_plan(plan), indent=2)}"
    )
    messages = [{"role": "user", "content": prompt}]

    def disabled_dispatch(name: str, args: dict[str, Any]) -> str:
        return f"Tool '{name}' is disabled during plan review; review the supplied JSON only."

    try:
        text, _ = _CHAT_FNS[provider](api_key, messages, model, disabled_dispatch)
    except Exception as exc:
        log.warning("planner LLM review failed: %s", exc)
        return {"status": "unavailable", "text": f"LLM review unavailable: {exc}", "structured_suggestion": None}

    return {
        "status": "reviewed",
        "provider": provider,
        "model": model,
        "text": _collapse_ws(text)[:4000],
        "structured_suggestion": _extract_json_object(text) if mode == "llm_structured" else None,
    }


def _draft_design_plan(
    brief: str,
    *,
    references: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, str]] | None = None,
    plan_id: str | None = None,
    status: str = "draft",
    revision_of: str | None = None,
    planner_mode: str = "deterministic",
    standards_profile: str = _DEFAULT_STANDARDS_PROFILE,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    clean_brief = _collapse_ws(brief)
    scope = _design_scope_from_brief(clean_brief)
    room_plans, bounds, existing_count = _draft_room_plans(clean_brief, scope)
    zones = [_room_plan_to_zone(plan) for plan in room_plans]
    planned_items = _planned_item_records(room_plans)
    refs = references if references is not None else search_references(_design_search_query(clean_brief), max_results=5)
    visual_refs = attachments or []
    profile_name, profile_spec = _mcp_server._profile(standards_profile)

    generated_id = plan_id or new_request_id("plan")
    plan: dict[str, Any] = {
        "id": generated_id,
        "title": f"{'Whole-flat' if scope == 'whole_flat' else zones[0]['name']} concept plan",
        "brief": clean_brief,
        "scope": scope,
        "planner": {
            "mode": planner_mode,
            "label": _planner_label(planner_mode),
            "applyable_source": "Haus deterministic geometry validator",
            "fallback_reason": fallback_reason,
        },
        "confidence": "medium" if planner_mode == "deterministic" else "medium-high",
        "standards_profile": {
            "id": profile_name,
            "label": profile_spec["label"],
            "min_walkway_m": profile_spec["min_walkway_m"],
            "notes": profile_spec["notes"],
        },
        "apply_readiness": "ready_to_apply",
        "validation_status": "ready_to_apply",
        "warnings": [],
        "assumptions": [
            "Concept-level output for spatial planning, not construction drawings or code compliance.",
            "Furniture uses the current Haus catalog and snaps to the existing 0.25m layout grid on apply.",
            "Existing layout bounds are treated as the available planning envelope.",
            f"Using {profile_spec['label']} targets; {profile_spec['notes']}",
        ],
        "web_references": refs,
        "zones": zones,
        "planned_items": planned_items,
        "metrics": {
            "existing_item_count": existing_count,
            "planned_item_count": len(planned_items),
            "zone_count": len(zones),
            "zone_areas_m2": {zone["name"]: zone["estimated_area_m2"] for zone in zones},
            "estimated_furniture_footprint_m2": _furniture_footprint_m2(room_plans),
            "walkway_target_m": profile_spec["min_walkway_m"],
            "layout_bounds": _layout_bounds_dict(bounds),
            "reference_count": len(refs),
            "visual_reference_count": len(visual_refs),
            "planner_mode": planner_mode,
            "standards_profile": profile_name,
            "overlap_risk": "checked during apply with collision-aware placement and post-apply overlap checks",
        },
        "validation_targets": [
            f"score_walkway across the planned envelope using a {profile_spec['min_walkway_m']}m target",
            "check_overlap on newly applied furniture pairs",
            "check_sightline where a sofa and TV console are planned in the same zone",
            "compute_room_area for every tagged zone after apply",
            f"score_layout(profile='{profile_name}') after apply",
        ],
        "rationale": [
            "Uses deterministic Haus room kits so the draft can be applied directly and repeatably.",
            "Keeps the plan verbal until the user applies it, so the current layout is not mutated by drafting.",
            "Live references are attached to the concept package when search providers are available.",
        ],
        "status": status,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "_room_plans": room_plans,
    }
    if revision_of:
        plan["revision_of"] = revision_of

    _cache_design_plan(plan)
    return _public_design_plan(plan)


def _design_plan_response_text(plan: dict[str, Any]) -> str:
    metrics = plan.get("metrics", {})
    zone_names = ", ".join(zone.get("name", "Zone") for zone in plan.get("zones", []))
    return (
        f"Drafted {plan['title']} as a concept plan. "
        f"Zones: {zone_names}. "
        f"Planned {metrics.get('planned_item_count', 0)} item(s) with a "
        f"{metrics.get('walkway_target_m', 0.75)}m circulation target. "
        f"Planner: {plan.get('planner', {}).get('label', 'Haus planner') if isinstance(plan.get('planner'), dict) else 'Haus planner'}. "
        "Review or revise the plan, then apply it to update the layout."
    )


def _find_plan(plan_id: str) -> dict[str, Any] | None:
    return _DESIGN_PLAN_CACHE.get(plan_id)


def _post_apply_validation(
    data: dict[str, Any],
    room_plans: list[RoomPlan],
    applied_by_room: dict[str, list[int]],
    standards_profile: str = _DEFAULT_STANDARDS_PROFILE,
) -> dict[str, Any]:
    room_areas = {plan.room_id: compute_room_area(plan.room_id) for plan in room_plans}
    applied_indices = [idx for indices in applied_by_room.values() for idx in indices]
    room_bounds = {
        plan.room_id: geometry.room_bound_plan_application(
            data,
            plan.room_id,
            [data["items"][idx] for idx in applied_by_room.get(plan.room_id, []) if idx < len(data["items"])],
        )
        for plan in room_plans
    }

    overlap_checks: list[str] = []
    for pos, left_idx in enumerate(applied_indices[:8]):
        for right_idx in applied_indices[pos + 1 : 8]:
            overlap_checks.append(check_overlap(left_idx, right_idx))

    sightlines: list[str] = []
    for plan in room_plans:
        indices = applied_by_room.get(plan.room_id, [])
        sofa_idx = None
        tv_idx = None
        for idx in indices:
            item = data["items"][idx]
            furniture_type = str(item.get("furnitureType", ""))
            if sofa_idx is None and furniture_type.startswith("sofa"):
                sofa_idx = idx
            if tv_idx is None and furniture_type == "tv_console":
                tv_idx = idx
        if sofa_idx is not None and tv_idx is not None:
            sightlines.append(check_sightline(sofa_idx, tv_idx))

    x_min, z_min, x_max, z_max = _mcp_server._layout_bounds(data)
    walkway = "No walkway check available."
    profile_name, profile_spec = _mcp_server._profile(standards_profile)
    if abs(x_max - x_min) > 0.01 or abs(z_max - z_min) > 0.01:
        walkway = score_walkway(x_min, z_min, x_max, z_max, min_width=float(profile_spec["min_walkway_m"]))

    return {
        "layout_summary": get_layout_summary(),
        "rooms": list_rooms(),
        "room_areas": room_areas,
        "room_bound_plan_application": room_bounds,
        "walkway": walkway,
        "quality_profile": profile_name,
        "layout_quality": score_layout(profile_name),
        "overlap_checks": overlap_checks,
        "sightlines": sightlines,
    }


def _apply_design_plan(plan_id: str) -> tuple[dict[str, Any], int]:
    plan = _find_plan(plan_id)
    if plan is None:
        return {"ok": False, "error": f"Plan '{plan_id}' was not found."}, 404
    if plan.get("status") == "applied":
        return {"ok": False, "error": f"Plan '{plan_id}' has already been applied."}, 409

    room_plans = cast(list[RoomPlan], plan.get("_room_plans", []))
    if not room_plans:
        return {"ok": False, "error": f"Plan '{plan_id}' has no applyable room plans."}, 422

    data = _mcp_server._load_layout()
    trace: list[dict[str, Any]] = [
        {
            "tool": "get_layout_summary",
            "args": {},
            "result": f"read {len(data['items'])} existing layout item(s)",
        }
    ]
    applied_by_room: dict[str, list[int]] = {}
    skipped_by_room: dict[str, list[str]] = {}
    for room_plan in room_plans:
        applied, skipped = _mcp_server._apply_room_plan(data, room_plan, trace)
        applied_by_room[room_plan.room_id] = applied
        skipped_by_room[room_plan.room_id] = skipped

    save_err = _mcp_server._save_layout(data)
    if save_err:
        return {"ok": False, "error": save_err}, 500

    profile = plan.get("standards_profile", {})
    standards_profile = str(profile.get("id", _DEFAULT_STANDARDS_PROFILE)) if isinstance(profile, dict) else _DEFAULT_STANDARDS_PROFILE
    validation = _post_apply_validation(data, room_plans, applied_by_room, standards_profile=standards_profile)
    total_applied = sum(len(indices) for indices in applied_by_room.values())
    plan["status"] = "applied"
    plan["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    plan["metrics"]["applied_item_count"] = total_applied

    return (
        {
            "ok": True,
            "summary": f"Applied plan {plan_id}: added {total_applied} item(s) across {len(room_plans)} zone(s).",
            "plan": _public_design_plan(plan),
            "actions": trace,
            "applied_by_room": applied_by_room,
            "skipped_by_room": skipped_by_room,
            "validation": validation,
        },
        200,
    )


def _revise_design_plan(plan_id: str, revision: str, *, web_search_disabled: bool = False) -> tuple[dict[str, Any], int]:
    plan = _find_plan(plan_id)
    if plan is None:
        return {"ok": False, "error": f"Plan '{plan_id}' was not found."}, 404

    old_brief = str(plan.get("brief", ""))
    revised_brief = _collapse_ws(f"{old_brief} Revision: {revision}")
    references = list(plan.get("web_references", [])) if web_search_disabled else search_references(_design_search_query(revised_brief), max_results=5) or list(plan.get("web_references", []))
    planner = plan.get("planner", {})
    profile = plan.get("standards_profile", {})
    planner_mode = str(planner.get("mode", "deterministic")) if isinstance(planner, dict) else "deterministic"
    standards_profile = str(profile.get("id", _DEFAULT_STANDARDS_PROFILE)) if isinstance(profile, dict) else _DEFAULT_STANDARDS_PROFILE
    public_plan = _draft_design_plan(
        revised_brief,
        references=references,
        plan_id=plan_id,
        status="revised_draft",
        revision_of=str(plan.get("revision_of") or plan_id),
        planner_mode=planner_mode,
        standards_profile=standards_profile,
    )
    return {"ok": True, "plan": public_plan, "summary": f"Revised plan {plan_id}."}, 200


def _design_plan_report(plan: dict[str, Any]) -> str:
    lines = [
        f"# {plan['title']}",
        "",
        f"Plan ID: {plan['id']}",
        f"Status: {plan['status']}",
        f"Scope: {plan['scope']}",
        f"Planner: {plan.get('planner', {}).get('label', 'Deterministic Haus room-kit planner') if isinstance(plan.get('planner'), dict) else 'Deterministic Haus room-kit planner'}",
        f"Standards profile: {plan.get('standards_profile', {}).get('label', 'Compact apartment circulation') if isinstance(plan.get('standards_profile'), dict) else 'Compact apartment circulation'}",
        "",
        "## Brief",
        plan["brief"],
        "",
        "## Assumptions",
    ]
    lines.extend(f"- {item}" for item in plan.get("assumptions", []))
    lines.extend(["", "## Zones"])
    for zone in plan.get("zones", []):
        furniture = ", ".join(item["label"] for item in zone.get("planned_furniture", []))
        lines.append(f"- {zone['name']}: {zone['intent']}; center ({zone['target_center']['x']}, {zone['target_center']['z']}); {zone['estimated_area_m2']}m2; {furniture}")
        lines.append(f"  Circulation: {zone['circulation_notes']}")

    metrics = plan.get("metrics", {})
    lines.extend(
        [
            "",
            "## Metrics",
            f"- Planned items: {metrics.get('planned_item_count', 0)}",
            f"- Zones: {metrics.get('zone_count', 0)}",
            f"- Walkway target: {metrics.get('walkway_target_m', 0.9)}m",
            f"- Estimated furniture footprint: {metrics.get('estimated_furniture_footprint_m2', 0)}m2",
            f"- References: {metrics.get('reference_count', 0)}",
            "",
            "## Validation Targets",
        ]
    )
    lines.extend(f"- {item}" for item in plan.get("validation_targets", []))
    lines.extend(["", "## References"])
    refs = plan.get("web_references", [])
    if refs:
        for ref in refs:
            provider = ref.get("source_provider", "web")
            lines.append(f"- [{ref.get('title', ref.get('url'))}]({ref.get('url')}) ({provider})")
    else:
        lines.append("- No live references were available for this draft.")
    lines.extend(["", "## Rationale"])
    lines.extend(f"- {item}" for item in plan.get("rationale", []))
    review = plan.get("llm_review")
    if isinstance(review, dict):
        lines.extend(["", "## LLM Review", review.get("text", "No review text available.")])
    return "\n".join(lines) + "\n"


_DISPATCH_RAW: dict[str, Callable[[dict[str, Any]], str]] = {
    "design_room": lambda a: design_room(**a),
    "design_flat": lambda a: design_flat(**a),
    "list_furniture_catalog": lambda a: list_furniture_catalog(),
    "search_ikea_catalog": lambda a: search_ikea_catalog_tool(**a),
    "get_ikea_catalog_item": lambda a: get_ikea_catalog_item(**a),
    "add_catalog_furniture": lambda a: add_catalog_furniture(**a),
    "refresh_ikea_catalog": lambda a: refresh_ikea_catalog(**a),
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
    "score_walkway": lambda a: score_walkway(**a),
    "score_layout": lambda a: score_layout(**a),
    "get_semantic_layout_json": lambda a: get_semantic_layout_json(),
    "bim_readiness_report": lambda a: bim_readiness_report(),
}


def _confirmation_summary(name: str, args: dict[str, Any]) -> str:
    if name == "clear_layout":
        return "Remove every object from the current layout."
    if name == "remove_object":
        return f"Remove object index {args.get('index')} from the current layout."
    if name == "remove_objects_by_type":
        return f"Remove every object matching type '{args.get('object_type')}'."
    return f"Run destructive tool {name}."


def _prune_tool_confirmations() -> None:
    now = time.time()
    expired = [
        token
        for token in list(_TOOL_CONFIRMATION_ORDER)
        if now - float(_TOOL_CONFIRMATION_CACHE.get(token, {}).get("created_at", 0.0)) > _TOOL_CONFIRMATION_TTL_SECONDS
    ]
    for token in expired:
        _TOOL_CONFIRMATION_CACHE.pop(token, None)
        if token in _TOOL_CONFIRMATION_ORDER:
            _TOOL_CONFIRMATION_ORDER.remove(token)
    while len(_TOOL_CONFIRMATION_ORDER) > _MAX_TOOL_CONFIRMATIONS:
        old = _TOOL_CONFIRMATION_ORDER.pop(0)
        _TOOL_CONFIRMATION_CACHE.pop(old, None)


def _cache_tool_confirmation(name: str, args: dict[str, Any]) -> dict[str, Any]:
    _prune_tool_confirmations()
    token = new_request_id("confirm")
    confirmation = {
        "token": token,
        "tool": name,
        "args": args,
        "safety": "destructive",
        "summary": _confirmation_summary(name, args),
        "created_at": time.time(),
        "expires_in_seconds": _TOOL_CONFIRMATION_TTL_SECONDS,
    }
    _TOOL_CONFIRMATION_CACHE[token] = confirmation
    _TOOL_CONFIRMATION_ORDER.append(token)
    _prune_tool_confirmations()
    return confirmation


def _confirmation_required_result(name: str, args: dict[str, Any]) -> str:
    confirmation = _cache_tool_confirmation(name, args)
    return json.dumps(
        {
            "ok": False,
            "requires_confirmation": True,
            "message": f"Confirmation required before executing destructive tool '{name}'.",
            "confirmation": confirmation,
        }
    )


def _dispatch(
    name: str,
    args: dict[str, Any],
    *,
    request_id: str,
    tool_log: list[dict[str, Any]],
    confirmation_token: str | None = None,
    web_search_disabled: bool = False,
) -> str:
    fn = _DISPATCH_RAW.get(name)
    start = time.perf_counter()

    if web_search_disabled and name in {"web_search", "web_fetch"}:
        result = f"Error: {name} is disabled by this chat session's privacy settings."
    elif fn is None:
        result = f"Error: unknown tool '{name}'."
    else:
        args, validation_error = _validate_tool_args(name, args)
        if validation_error:
            result = f"Error: invalid arguments for '{name}': {validation_error}"
        elif _tool_safety(name) == "destructive" and not confirmation_token:
            result = _confirmation_required_result(name, args)
        else:
            if confirmation_token:
                cached = _TOOL_CONFIRMATION_CACHE.pop(confirmation_token, None)
                if confirmation_token in _TOOL_CONFIRMATION_ORDER:
                    _TOOL_CONFIRMATION_ORDER.remove(confirmation_token)
                if not cached or cached.get("tool") != name or cached.get("args") != args:
                    result = f"Error: confirmation token is invalid or expired for '{name}'."
                else:
                    try:
                        result = fn(args)
                    except Exception as exc:  # pragma: no cover - defensive for runtime tool failures
                        log.exception("[%s] tool failure: %s", request_id, name)
                        result = f"Error: tool '{name}' failed: {exc}"
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
    try:
        parsed_result = json.loads(result)
        if isinstance(parsed_result, (dict, list)):
            entry["result_json"] = parsed_result
    except json.JSONDecodeError:
        pass
    tool_log.append(entry)

    preview = result[:200] + "..." if len(result) > 200 else result
    log.info("[%s] tool %s(%s) -> %s (%sms)", request_id, name, json.dumps(args), preview, elapsed_ms)
    return result


def _provider_available() -> list[str]:
    return providers_with_env_keys()


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


def _openai_strict_parameters(schema: dict[str, Any]) -> dict[str, Any]:
    strict = json.loads(json.dumps(schema))

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            properties = node.get("properties", {})
            original_required = set(str(item) for item in node.get("required", []) if isinstance(item, str))
            if isinstance(properties, dict):
                node["required"] = list(properties.keys())
                for key, child in properties.items():
                    if isinstance(child, dict):
                        if key not in original_required and isinstance(child.get("type"), str):
                            child["type"] = [child["type"], "null"]
                        visit(child)
            node["additionalProperties"] = False
        elif node.get("type") == "array":
            visit(node.get("items"))

    visit(strict)
    return strict


def _openai_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": _openai_strict_parameters(cast(dict[str, Any], t["parameters"])),
                "strict": True,
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


def _run_anthropic(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return anthropic_provider.chat(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_openai(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return openai_provider.chat(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_gemini(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return gemini_provider.chat(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_ollama(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return ollama_provider.chat(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_codex(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return local_cli_provider.chat_codex(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_gemini_cli(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return local_cli_provider.chat_gemini_cli(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_claude_code(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return local_cli_provider.chat_claude_code(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_opencode(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return local_cli_provider.chat_opencode(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_aider(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return local_cli_provider.chat_aider(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


def _run_openai_compatible_local(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, Any]]]:
    return openai_compatible_provider.chat(
        api_key,
        messages,
        model,
        dispatch,
        system=_SYSTEM,
        tools_spec=_TOOLS_SPEC,
        max_tool_steps=_MAX_TOOL_STEPS,
    )


_DEFAULT_MODELS = DEFAULT_MODELS

_CHAT_FNS: dict[
    str,
    Callable[[str, list[dict[str, Any]], str, Callable[[str, dict[str, Any]], str]], tuple[str, list[dict[str, Any]]]],
] = {
    "anthropic": _run_anthropic,
    "openai": _run_openai,
    "gemini": _run_gemini,
    "ollama": _run_ollama,
    "codex": _run_codex,
    "gemini-cli": _run_gemini_cli,
    "claude-code": _run_claude_code,
    "opencode": _run_opencode,
    "aider": _run_aider,
    "openai-compatible-local": _run_openai_compatible_local,
}

_STREAM_FNS: dict[
    str,
    Callable[[str, list[dict[str, Any]], str, Callable[[str, dict[str, Any]], str]], Iterator[ChatChunk]],
] = {
    "anthropic": lambda api_key, messages, model, dispatch: anthropic_provider.stream_chat(
        api_key, messages, model, dispatch, system=_SYSTEM, tools_spec=_TOOLS_SPEC, max_tool_steps=_MAX_TOOL_STEPS
    ),
    "openai": lambda api_key, messages, model, dispatch: openai_provider.stream_chat(
        api_key, messages, model, dispatch, system=_SYSTEM, tools_spec=_TOOLS_SPEC, max_tool_steps=_MAX_TOOL_STEPS
    ),
    "gemini": lambda api_key, messages, model, dispatch: gemini_provider.stream_chat(
        api_key, messages, model, dispatch, system=_SYSTEM, tools_spec=_TOOLS_SPEC, max_tool_steps=_MAX_TOOL_STEPS
    ),
    "ollama": lambda api_key, messages, model, dispatch: ollama_provider.stream_chat(
        api_key, messages, model, dispatch, system=_SYSTEM, tools_spec=_TOOLS_SPEC, max_tool_steps=_MAX_TOOL_STEPS
    ),
}

_ENV_KEYS = ENV_KEYS
_PROVIDER_SPECS = provider_specs()


def _resolve_provider_token(provider: str, client_key: str) -> str:
    if provider not in _CHAT_FNS:
        return ""
    env_key = _ENV_KEYS.get(provider, "")
    if client_key:
        return client_key
    if env_key:
        env_value = os.environ.get(env_key, "")
        if env_value:
            return env_value
    spec = _PROVIDER_SPECS.get(provider)
    return "local" if spec and not spec.requires_api_key else ""


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
    status = provider_status()
    providers = status["providers_with_env_keys"]
    configured_search = _configured_search_providers() if _web_search_enabled() else []
    available_search = _available_search_providers()
    return JSONResponse(
        {
            "available": True,
            "providers_with_env_keys": providers,
            "supported_providers": supported_provider_ids(),
            "default_models": _DEFAULT_MODELS,
            "providers": status["providers"],
            "search_providers_configured": configured_search,
            "search_providers_available": available_search,
            "search_fallback_provider": "duckduckgo" if "duckduckgo" in configured_search else "",
            "capabilities": {
                "web_search": _web_search_enabled(),
                "web_fetch": _web_search_enabled(),
                "image_references": True,
                "room_capture": True,
                "ikea_catalog": True,
                "catalog_cache": True,
                "design_plans": True,
                "planner_requires_api_key": False,
                "planner_modes": ["auto", "deterministic", "llm_reviewed", "llm_structured"],
                "default_planner_mode": "auto",
                "destructive_confirmation": True,
                "strict_tool_validation": True,
                "provider_native_streaming": True,
                "standards_profiles": list(_mcp_server.STANDARD_PROFILES.keys()),
                "max_image_attachments": _MAX_CHAT_ATTACHMENTS,
                "max_image_attachment_mb": _MAX_ATTACHMENT_BYTES // (1024 * 1024),
                "image_mime_types": sorted(_ALLOWED_IMAGE_MIME_TYPES),
            },
        }
    )


async def _chat_models(request: Request) -> JSONResponse:
    del request
    return JSONResponse(provider_status())


def _design_chat_payload(
    *,
    user_msg: str,
    history: list[dict[str, Any]],
    attachments: list[dict[str, str]],
    request_id: str,
    conversation_id: str = "",
    provider: str,
    api_key: str,
    model: str,
    planner_mode: str,
    standards_profile: str,
    fallback_reason: str | None = None,
    web_search_disabled: bool = False,
) -> JSONResponse:
    start = time.perf_counter()
    references = [] if web_search_disabled else search_references(_design_search_query(user_msg), max_results=5)
    plan = _draft_design_plan(
        user_msg,
        references=references,
        attachments=attachments,
        planner_mode=planner_mode,
        standards_profile=standards_profile,
        fallback_reason=fallback_reason,
    )
    raw_plan = _find_plan(str(plan["id"]))
    if raw_plan is not None and planner_mode in {"llm_reviewed", "llm_structured"}:
        review = _run_plan_llm_review(provider=provider, api_key=api_key, model=model, mode=planner_mode, plan=raw_plan)
        raw_plan["llm_review"] = review
        if review["status"] == "reviewed":
            raw_plan.setdefault("planner", {})["provider_reviewed"] = True
            raw_plan["rationale"].append("Provider review was attached, but Haus geometry validation remains the source of applyable placements.")
        if planner_mode == "llm_structured" and review.get("structured_suggestion"):
            raw_plan["structured_suggestion"] = review["structured_suggestion"]
        plan = _public_design_plan(raw_plan)
    text = _design_plan_response_text(plan)
    messages = history + [
        {"role": "user", "content": _build_user_content(user_msg, attachments)},
        {"role": "assistant", "content": [{"type": "text", "text": text}]},
    ]
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    action = {
        "tool": "draft_design_plan",
        "args": {
            "brief": user_msg,
            "reference_count": len(references),
            "planner_mode": planner_mode,
            "standards_profile": standards_profile,
            "web_search_disabled": web_search_disabled,
        },
        "result": f"Drafted concept plan {plan['id']}.",
        "result_json": plan,
        "elapsed_ms": elapsed_ms,
    }
    return JSONResponse(
        {
            "response": text,
            "history": _redact_history_for_client(messages),
            "provider": "haus-planner",
            "model": f"{planner_mode}-concept-planner",
            "actions": [action],
            "pending_plan": plan,
            "references": references,
            "request_id": request_id,
            "conversation_id": conversation_id,
        }
    )


def _revision_chat_payload(
    *,
    plan_id: str,
    revision: str,
    history: list[dict[str, Any]],
    user_msg: str,
    request_id: str,
    conversation_id: str = "",
    web_search_disabled: bool = False,
) -> JSONResponse:
    start = time.perf_counter()
    payload, status = _revise_design_plan(plan_id, revision, web_search_disabled=web_search_disabled)
    if status != 200:
        return JSONResponse({"error": payload.get("error", "Revision failed."), "request_id": request_id}, status)

    plan = payload["plan"]
    text = _design_plan_response_text(plan)
    messages = history + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": [{"type": "text", "text": text}]},
    ]
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    action = {
        "tool": "revise_design_plan",
        "args": {"plan_id": plan_id, "revision": revision},
        "result": payload["summary"],
        "result_json": plan,
        "elapsed_ms": elapsed_ms,
    }
    return JSONResponse(
        {
            "response": text,
            "history": _redact_history_for_client(messages),
            "provider": "haus-planner",
            "model": "deterministic-concept-planner",
            "actions": [action],
            "pending_plan": plan,
            "references": plan.get("web_references", []),
            "request_id": request_id,
            "conversation_id": conversation_id,
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
    conversation_id = str(body.get("conversation_id") or body.get("conversationId") or uuid.uuid4()).strip()
    client_key = str(body.get("api_key", "")).strip()
    planner_mode_requested = str(body.get("planner_mode") or body.get("plannerMode") or "auto")
    standards_profile = str(body.get("standards_profile") or body.get("standardsProfile") or _DEFAULT_STANDARDS_PROFILE)
    raw_web_search_disabled = body.get("web_search_disabled", body.get("disable_web_search", False))
    web_search_disabled = raw_web_search_disabled is True or str(raw_web_search_disabled).lower() in {"1", "true", "yes", "on"}
    attachments, attachment_error = _normalize_attachments(body.get("attachments", []))

    if not user_msg:
        return JSONResponse({"error": "Message must not be empty.", "request_id": request_id}, 400)
    if attachment_error:
        return JSONResponse({"error": attachment_error, "request_id": request_id}, 400)

    revision_request = _parse_revision_request(user_msg)
    concept_request = _is_concept_request(user_msg, attachments)

    try:
        concept_model, _ = resolve_model(provider, model_override) if provider in _CHAT_FNS else ("deterministic", False)
    except ValueError as exc:
        return JSONResponse({"error": str(exc), "request_id": request_id, "conversation_id": conversation_id}, 400)
    concept_api_key = _resolve_provider_token(provider, client_key)
    resolved_planner_mode, planner_fallback_reason = _resolve_planner_mode(
        planner_mode_requested,
        provider,
        concept_api_key,
    )

    if revision_request is not None:
        plan_id, revision = revision_request
        return _revision_chat_payload(
            plan_id=plan_id,
            revision=revision,
            history=history,
            user_msg=user_msg,
            request_id=request_id,
            conversation_id=conversation_id,
            web_search_disabled=web_search_disabled,
        )

    if concept_request:
        return _design_chat_payload(
            user_msg=user_msg,
            history=history,
            attachments=attachments,
            request_id=request_id,
            conversation_id=conversation_id,
            provider=provider,
            api_key=concept_api_key,
            model=concept_model,
            planner_mode=resolved_planner_mode,
            standards_profile=standards_profile,
            fallback_reason=planner_fallback_reason,
            web_search_disabled=web_search_disabled,
        )

    if provider not in _CHAT_FNS:
        return JSONResponse(
            {
                "error": f"Provider '{provider}' not supported.",
                "supported": supported_provider_ids(),
                "request_id": request_id,
                "conversation_id": conversation_id,
            },
            400,
        )

    api_key = _resolve_provider_token(provider, client_key)
    if not api_key:
        return JSONResponse(
            {
                "error": f"No API key for {provider}. Add one in chat settings.",
                "request_id": request_id,
                "conversation_id": conversation_id,
            },
            400,
        )

    try:
        model, custom_model = resolve_model(provider, model_override)
    except ValueError as exc:
        return JSONResponse({"error": str(exc), "request_id": request_id, "conversation_id": conversation_id}, 400)
    tool_log: list[dict[str, Any]] = []
    messages = history + [{"role": "user", "content": _build_user_content(user_msg, attachments)}]

    def dispatch(name: str, args: dict[str, Any]) -> str:
        return _dispatch(name, args, request_id=request_id, tool_log=tool_log, web_search_disabled=web_search_disabled)

    log.info("[%s] chat request provider=%s model=%s", request_id, provider, model)

    try:
        text, updated_history = _CHAT_FNS[provider](api_key, messages, model, dispatch)
        return JSONResponse(
            {
                "response": text,
                "history": _redact_history_for_client(updated_history),
                "provider": provider,
                "model": model,
                "custom_model": custom_model,
                "conversation_id": conversation_id,
                "actions": tool_log,
                "request_id": request_id,
            }
        )
    except Exception as exc:
        log.exception("[%s] chat error", request_id)
        return JSONResponse({"error": str(exc), "request_id": request_id, "conversation_id": conversation_id}, 500)


def _json_response_body(response: JSONResponse) -> dict[str, Any]:
    try:
        body = json.loads(bytes(response.body).decode("utf-8"))
    except Exception:
        return {"error": "Could not decode response body."}
    return body if isinstance(body, dict) else {"response": body}


async def _chat_stream(request: Request) -> StreamingResponse:
    request_id = new_request_id("chat-stream")

    try:
        body = await request.json()
    except Exception:
        async def bad_json() -> AsyncIterator[str]:
            yield ChatChunk("error", {"error": "Invalid JSON body.", "request_id": request_id}).sse_event()

        return StreamingResponse(bad_json(), media_type="text/event-stream")

    user_msg = str(body.get("message", "")).strip()
    history = _sanitize_history(body.get("history", []))
    provider = str(body.get("provider", "")).strip().lower()
    model_override = str(body.get("model", "")).strip()
    conversation_id = str(body.get("conversation_id") or body.get("conversationId") or uuid.uuid4()).strip()
    client_key = str(body.get("api_key", "")).strip()
    planner_mode_requested = str(body.get("planner_mode") or body.get("plannerMode") or "auto")
    standards_profile = str(body.get("standards_profile") or body.get("standardsProfile") or _DEFAULT_STANDARDS_PROFILE)
    raw_web_search_disabled = body.get("web_search_disabled", body.get("disable_web_search", False))
    web_search_disabled = raw_web_search_disabled is True or str(raw_web_search_disabled).lower() in {"1", "true", "yes", "on"}
    attachments, attachment_error = _normalize_attachments(body.get("attachments", []))

    async def events() -> AsyncIterator[str]:
        if not user_msg:
            yield ChatChunk("error", {"error": "Message must not be empty.", "request_id": request_id, "conversation_id": conversation_id}).sse_event()
            return
        if attachment_error:
            yield ChatChunk("error", {"error": attachment_error, "request_id": request_id, "conversation_id": conversation_id}).sse_event()
            return

        revision_request = _parse_revision_request(user_msg)
        concept_request = _is_concept_request(user_msg, attachments)
        api_key = _resolve_provider_token(provider, client_key)
        try:
            model, custom_model = resolve_model(provider, model_override) if provider in _CHAT_FNS else ("deterministic", False)
        except ValueError as exc:
            yield ChatChunk("error", {"error": str(exc), "request_id": request_id, "conversation_id": conversation_id}).sse_event()
            return

        if revision_request is not None:
            plan_id, revision = revision_request
            payload = _json_response_body(
                _revision_chat_payload(
                    plan_id=plan_id,
                    revision=revision,
                    history=history,
                    user_msg=user_msg,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    web_search_disabled=web_search_disabled,
                )
            )
            if payload.get("error"):
                yield ChatChunk("error", payload).sse_event()
                return
            yield ChatChunk("meta", {k: v for k, v in payload.items() if k not in {"response", "history"}}).sse_event()
            yield ChatChunk("text", {"delta": str(payload.get("response", ""))}).sse_event()
            yield ChatChunk("done", payload).sse_event()
            return

        if concept_request:
            resolved_planner_mode, fallback_reason = _resolve_planner_mode(planner_mode_requested, provider, api_key)
            payload = _json_response_body(
                _design_chat_payload(
                    user_msg=user_msg,
                    history=history,
                    attachments=attachments,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    planner_mode=resolved_planner_mode,
                    standards_profile=standards_profile,
                    fallback_reason=fallback_reason,
                    web_search_disabled=web_search_disabled,
                )
            )
            yield ChatChunk("meta", {k: v for k, v in payload.items() if k not in {"response", "history"}}).sse_event()
            yield ChatChunk("text", {"delta": str(payload.get("response", ""))}).sse_event()
            yield ChatChunk("done", payload).sse_event()
            return

        if provider not in _CHAT_FNS:
            yield ChatChunk("error", {"error": f"Provider '{provider}' not supported.", "supported": supported_provider_ids(), "request_id": request_id, "conversation_id": conversation_id}).sse_event()
            return
        if not api_key:
            yield ChatChunk("error", {"error": f"No API key for {provider}. Add one in chat settings.", "request_id": request_id, "conversation_id": conversation_id}).sse_event()
            return

        tool_log: list[dict[str, Any]] = []
        messages = history + [{"role": "user", "content": _build_user_content(user_msg, attachments)}]

        def dispatch(name: str, args: dict[str, Any]) -> str:
            return _dispatch(name, args, request_id=request_id, tool_log=tool_log, web_search_disabled=web_search_disabled)

        yield ChatChunk(
            "meta",
            {
                "request_id": request_id,
                "conversation_id": conversation_id,
                "provider": provider,
                "model": model,
                "custom_model": custom_model,
            },
        ).sse_event()
        try:
            if provider not in _STREAM_FNS:
                text, updated_history = _CHAT_FNS[provider](api_key, messages, model, dispatch)
                final = {
                    "response": text,
                    "history": _redact_history_for_client(updated_history),
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "provider": provider,
                    "model": model,
                    "custom_model": custom_model,
                    "actions": tool_log,
                }
                if text:
                    yield ChatChunk("text", {"delta": text}).sse_event()
                yield ChatChunk("done", final).sse_event()
                return

            final: dict[str, Any] = {}
            for chunk in _STREAM_FNS[provider](api_key, messages, model, dispatch):
                if chunk.type == "done":
                    final = dict(chunk.data)
                    final["history"] = _redact_history_for_client(final.get("history", messages))
                    final.update(
                        {
                            "request_id": request_id,
                            "conversation_id": conversation_id,
                            "provider": provider,
                            "model": model,
                            "custom_model": custom_model,
                            "actions": tool_log,
                        }
                    )
                    yield ChatChunk("done", final).sse_event()
                else:
                    yield chunk.sse_event()
            if not final:
                yield ChatChunk(
                    "done",
                    {
                        "response": "",
                        "history": _redact_history_for_client(messages),
                        "request_id": request_id,
                        "conversation_id": conversation_id,
                        "provider": provider,
                        "model": model,
                        "actions": tool_log,
                    },
                ).sse_event()
        except Exception as exc:
            log.exception("[%s] stream chat error", request_id)
            yield ChatChunk("error", {"error": str(exc), "request_id": request_id, "conversation_id": conversation_id}).sse_event()

    return StreamingResponse(events(), media_type="text/event-stream")


async def _design_plan_apply(request: Request) -> JSONResponse:
    request_id = new_request_id("apply-plan")
    plan_id = str(request.path_params.get("plan_id", "")).strip()
    payload, status = _apply_design_plan(plan_id)
    payload["request_id"] = request_id
    return JSONResponse(payload, status)


async def _design_plan_revise(request: Request) -> JSONResponse:
    request_id = new_request_id("revise-plan")
    plan_id = str(request.path_params.get("plan_id", "")).strip()
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body.", "request_id": request_id}, 400)

    revision = _collapse_ws(str(body.get("revision", "")))
    if not revision:
        return JSONResponse({"ok": False, "error": "Revision must not be empty.", "request_id": request_id}, 400)

    raw_web_search_disabled = body.get("web_search_disabled", body.get("disable_web_search", False))
    web_search_disabled = raw_web_search_disabled is True or str(raw_web_search_disabled).lower() in {"1", "true", "yes", "on"}
    payload, status = _revise_design_plan(plan_id, revision, web_search_disabled=web_search_disabled)
    payload["request_id"] = request_id
    return JSONResponse(payload, status)


async def _design_plan_report_route(request: Request) -> PlainTextResponse | JSONResponse:
    plan_id = str(request.path_params.get("plan_id", "")).strip()
    plan = _find_plan(plan_id)
    if plan is None:
        return JSONResponse({"ok": False, "error": f"Plan '{plan_id}' was not found."}, 404)
    return PlainTextResponse(_design_plan_report(_public_design_plan(plan)), media_type="text/markdown")


async def _tool_confirmation_apply(request: Request) -> JSONResponse:
    request_id = new_request_id("confirm-tool")
    token = str(request.path_params.get("token", "")).strip()
    _prune_tool_confirmations()
    confirmation = _TOOL_CONFIRMATION_CACHE.get(token)
    if confirmation is None:
        return JSONResponse({"ok": False, "error": "Confirmation token was not found or has expired.", "request_id": request_id}, 404)

    tool_log: list[dict[str, Any]] = []
    result = _dispatch(
        str(confirmation["tool"]),
        cast(dict[str, Any], confirmation["args"]),
        request_id=request_id,
        tool_log=tool_log,
        confirmation_token=token,
    )
    ok = not result.startswith("Error:")
    return JSONResponse(
        {
            "ok": ok,
            "summary": result,
            "actions": tool_log,
            "request_id": request_id,
        },
        200 if ok else 400,
    )


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

    validation = validate_layout_schema(body)
    if not validation["ok"]:
        return JSONResponse(
            {"ok": False, "error": "Layout schema validation failed.", "details": validation["errors"], "request_id": request_id},
            400,
        )

    err = _save_layout(validation["layout"])
    if err:
        log.error("[%s] sync failed: %s", request_id, err)
        return JSONResponse({"ok": False, "error": err, "request_id": request_id}, 500)

    log.info("[%s] layout synced (%s items)", request_id, len(body.get("items", [])))
    return JSONResponse({"ok": True, "warnings": validation["warnings"], "request_id": request_id})


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


async def _room_capture_layout(request: Request) -> JSONResponse:
    request_id = new_request_id("room-capture")
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body.", "request_id": request_id}, 400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "Room capture payload must be a JSON object.", "request_id": request_id}, 400)
    try:
        layout = build_room_capture_layout(body)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "request_id": request_id}, 400)
    return JSONResponse({"ok": True, "layout": layout, "request_id": request_id})


def _runtime_root() -> Path:
    configured = os.environ.get("HAUS_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".haus").resolve()


def _form_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _form_float(value: Any, default: float | None = None) -> float | None:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = float(str(value))
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _floorplan_warnings(metadata: dict[str, Any], layout: dict[str, Any], scale_override: float | None) -> list[str]:
    warnings: list[str] = []
    wall_count = int(layout.get("metadata", {}).get("wall_count") or metadata.get("walls", {}).get("total_segments") or 0)
    if wall_count < 4:
        warnings.append("Few walls were detected. Use the image overlay and draw walls manually if the extraction looks sparse.")
    scale = layout.get("metadata", {}).get("scale_m_per_px") or metadata.get("scale", {}).get("m_per_px")
    if scale is None:
        warnings.append("Scale could not be estimated. Calibrate with a known length before judging measurements.")
    elif scale_override is None:
        warnings.append("Scale is estimated from wall thickness. Calibrate with a known length for better measurements.")
    opening_count = int(layout.get("metadata", {}).get("opening_count") or metadata.get("openings", {}).get("total") or 0)
    if opening_count == 0:
        warnings.append("No doors or windows were detected. Add openings manually where needed.")
    return warnings


async def _floorplan_vectorize(request: Request) -> JSONResponse:
    request_id = new_request_id("floorplan")
    try:
        form = await request.form()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid multipart form body.", "request_id": request_id}, 400)

    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        return JSONResponse({"ok": False, "error": "Missing floor plan file field 'file'.", "request_id": request_id}, 400)

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_FLOORPLAN_MIME_TYPES:
        return JSONResponse(
            {
                "ok": False,
                "error": "Unsupported floor plan type. Upload PNG, JPG, or WebP.",
                "request_id": request_id,
            },
            400,
        )

    raw = await upload.read(_MAX_FLOORPLAN_BYTES + 1)
    if not raw:
        return JSONResponse({"ok": False, "error": "Floor plan file is empty.", "request_id": request_id}, 400)
    if len(raw) > _MAX_FLOORPLAN_BYTES:
        return JSONResponse({"ok": False, "error": "Floor plan file exceeds 15MB.", "request_id": request_id}, 413)

    upload_id = uuid.uuid4().hex[:12]
    root = _runtime_root() / "uploads" / upload_id
    root.mkdir(parents=True, exist_ok=True)
    ext = _FLOORPLAN_EXTENSIONS[content_type]
    image_path = root / f"source{ext}"
    image_path.write_bytes(raw)
    out_dir = root / "vectorized"
    debug_dir = root / "debug"
    scale_override = _form_float(form.get("scale_m_per_px"))
    wall_height = _form_float(form.get("wall_height_m"), 2.6) or 2.6
    clean = _form_bool(form.get("clean"), True)

    try:
        metadata = run_vectorize(
            VectorizeConfig(
                image_path=image_path,
                out_dir=out_dir,
                debug_dir=debug_dir,
                wall_height=wall_height,
                scale_override=scale_override,
                clean=clean,
            )
        )
        layout_path = Path(str(metadata["output_layout"]))
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.exception("[%s] floor plan vectorization failed", request_id)
        return JSONResponse({"ok": False, "error": str(exc), "request_id": request_id}, 500)

    layout_metadata = layout.setdefault("metadata", {})
    if isinstance(layout_metadata, dict):
        layout_metadata["source_type"] = "upload"
        layout_metadata["source_filename"] = upload.filename or image_path.name
        layout_metadata["upload_id"] = upload_id
        if scale_override is not None:
            layout_metadata["calibration"] = {"scale_m_per_px": scale_override, "source": "user"}
    warnings = _floorplan_warnings(metadata, layout, scale_override)
    if warnings and isinstance(layout_metadata, dict):
        layout_metadata["extraction_warnings"] = warnings

    return JSONResponse(
        {
            "ok": True,
            "layout": layout,
            "metadata": metadata,
            "warnings": warnings,
            "artifacts": {
                "upload_id": upload_id,
                "source": str(image_path),
                "layout": str(layout_path),
                "glb": str(out_dir / "model.glb"),
                "vector_clean": str(out_dir / "vector_clean.png"),
                "debug_dir": str(debug_dir),
            },
            "request_id": request_id,
        }
    )


async def _catalog_ikea_search(request: Request) -> JSONResponse:
    request_id = new_request_id("catalog-search")
    params = request.query_params
    query = _collapse_ws(str(params.get("q") or params.get("query") or ""))
    if not query:
        return JSONResponse({"ok": False, "error": "query must not be empty.", "request_id": request_id}, 400)
    try:
        max_results = int(params.get("max_results") or params.get("limit") or 12)
    except ValueError:
        max_results = 12
    refresh = str(params.get("refresh") or "").lower() in {"1", "true", "yes", "on"}
    region = str(params.get("region") or "sg")
    try:
        items = search_ikea_catalog(query, max_results=max_results, region=region, refresh=refresh)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "request_id": request_id}, 400)
    return JSONResponse({
        "ok": True,
        "items": items,
        "catalog": catalog_search_meta(items, refresh=refresh),
        "request_id": request_id,
    })


async def _catalog_ikea_item(request: Request) -> JSONResponse:
    request_id = new_request_id("catalog-item")
    item_id = str(request.path_params.get("item_id") or "").strip()
    item = get_catalog_item(item_id)
    if item is None:
        return JSONResponse({"ok": False, "error": f"IKEA catalog item '{item_id}' was not found.", "request_id": request_id}, 404)
    return JSONResponse({"ok": True, "item": item, "request_id": request_id})


async def _catalog_ikea_layout_item(request: Request) -> JSONResponse:
    request_id = new_request_id("catalog-layout-item")
    item_id = str(request.path_params.get("item_id") or "").strip()
    item = get_catalog_item(item_id)
    if item is None:
        return JSONResponse({"ok": False, "error": f"IKEA catalog item '{item_id}' was not found.", "request_id": request_id}, 404)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    layout_item = catalog_item_to_layout_item(
        item,
        x=_coerce_float(body.get("x", 0.0), 0.0),
        z=_coerce_float(body.get("z", 0.0), 0.0),
        rotation_deg=_coerce_float(body.get("rotation_deg", body.get("rotationDeg", 0.0)), 0.0),
    )
    return JSONResponse({"ok": True, "item": item, "layout_item": layout_item, "request_id": request_id})


def create_app(root_dir: str) -> Starlette:
    return Starlette(
        routes=[
            Route("/api/chat/status", _chat_status, methods=["GET"]),
            Route("/api/chat/models", _chat_models, methods=["GET"]),
            Route("/api/chat/stream", _chat_stream, methods=["POST"]),
            Route("/api/chat", _chat, methods=["POST"]),
            Route("/api/design-plans/{plan_id}/apply", _design_plan_apply, methods=["POST"]),
            Route("/api/design-plans/{plan_id}/revise", _design_plan_revise, methods=["POST"]),
            Route("/api/design-plans/{plan_id}/report", _design_plan_report_route, methods=["GET"]),
            Route("/api/tool-confirmations/{token}/confirm", _tool_confirmation_apply, methods=["POST"]),
            Route("/api/sync-layout", _sync_layout, methods=["POST"]),
            Route("/api/mcp/clear-layout", _mcp_clear_layout, methods=["POST"]),
            Route("/api/room-capture/layout", _room_capture_layout, methods=["POST"]),
            Route("/api/floorplans/vectorize", _floorplan_vectorize, methods=["POST"]),
            Route("/api/catalog/ikea/search", _catalog_ikea_search, methods=["GET"]),
            Route("/api/catalog/ikea/items/{item_id}", _catalog_ikea_item, methods=["GET"]),
            Route("/api/catalog/ikea/items/{item_id}/layout-item", _catalog_ikea_layout_item, methods=["POST"]),
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
