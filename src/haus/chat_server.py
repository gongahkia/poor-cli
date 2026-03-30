# pyright: reportPrivateImportUsage=false

"""Combined static file server + AI chat API for the haus editor.

Serves viewer files and provides `/api/chat` with tool-using LLM providers.
"""

from __future__ import annotations

import importlib
import json
import mimetypes
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn

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

_SYSTEM = (
    "You are an AI assistant for the haus floor plan editor. "
    "You ONLY help with floor plan editing — arranging furniture, walls, and layout. "
    "If the user asks something unrelated (general knowledge, coding, etc), "
    "politely decline and remind them you only handle floor plan tasks.\n\n"
    "Coordinate system: X is left-right, Z is forward-back. Positions are in meters.\n"
    "Typical room sizes: bedrooms ~3x3m, living rooms ~4x5m, bathrooms ~2x2m, kitchens ~2.5x3m.\n\n"
    "IMPORTANT RULES:\n"
    "- Before any DESTRUCTIVE action (removing, clearing, or replacing objects), "
    "FIRST describe what you plan to do and ASK for confirmation.\n"
    "- For vague intents (e.g., best sofa placement with clear TV view), "
    "use simulation tools: suggest_furniture_placement, auto_place_furniture, "
    "simulate_layout_options, apply_simulated_option, and check_sightline.\n"
    "- remove_objects_by_type is safer than repeated remove_object when deleting many.\n"
    "- batch_move uses relative offsets (dx, dz), not absolute positions.\n\n"
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
        "name": "list_furniture_catalog",
        "description": "List all available furniture types with dimensions.",
        "parameters": {"type": "object", "properties": {}},
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

_DISPATCH_RAW: dict[str, Callable[[dict[str, Any]], str]] = {
    "list_furniture_catalog": lambda a: list_furniture_catalog(),
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

    history = []
    for msg in messages:
        if isinstance(msg.get("content"), str):
            history.append({"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]})

    chat = gmodel.start_chat(history=history[:-1] if len(history) > 1 else [])
    last_msg = history[-1]["parts"][0] if history else ""

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
        if isinstance(content, (str, list)):
            out.append({"role": role, "content": content})
    return out


async def _chat_status(request: Request) -> JSONResponse:
    providers = _provider_available()
    return JSONResponse(
        {
            "available": True,
            "providers_with_env_keys": providers,
            "supported_providers": list(_CHAT_FNS.keys()),
            "default_models": _DEFAULT_MODELS,
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

    if not user_msg:
        return JSONResponse({"error": "Message must not be empty.", "request_id": request_id}, 400)

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
    messages = history + [{"role": "user", "content": user_msg}]

    def dispatch(name: str, args: dict[str, Any]) -> str:
        return _dispatch(name, args, request_id=request_id, tool_log=tool_log)

    log.info("[%s] chat request provider=%s model=%s", request_id, provider, model)

    try:
        text, updated_history = _CHAT_FNS[provider](api_key, messages, model, dispatch)
        return JSONResponse(
            {
                "response": text,
                "history": updated_history,
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


def create_app(root_dir: str) -> Starlette:
    return Starlette(
        routes=[
            Route("/api/chat/status", _chat_status, methods=["GET"]),
            Route("/api/chat", _chat, methods=["POST"]),
            Route("/api/sync-layout", _sync_layout, methods=["POST"]),
            Mount("/", StaticFiles(directory=root_dir, html=True)),
        ]
    )


def run_server(root_dir: str, port: int = 8080) -> None:
    os.environ["_HAUS_ROOT"] = root_dir
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
    return create_app(os.environ["_HAUS_ROOT"])
