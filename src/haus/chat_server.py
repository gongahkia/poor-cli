"""Combined static file server + AI chat API for the haus editor.

Serves the viewer files and provides a /api/chat endpoint that uses
Claude API with tool use to manipulate the floor plan layout.
"""
from __future__ import annotations
import json
import mimetypes
import os
from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
import uvicorn
from .mcp_server import (
    list_furniture_catalog, list_objects, add_furniture, add_wall,
    move_object, rotate_object, remove_object, clear_layout, get_layout_json,
)

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

mimetypes.add_type("model/gltf-binary", ".glb")

_SYSTEM = (
    "You are an AI assistant for the haus floor plan editor. "
    "You help users arrange furniture and walls in their floor plan by calling tools.\n\n"
    "Coordinate system: X is left-right, Z is forward-back. Positions are in meters.\n"
    "When the user asks you to do something:\n"
    "1. Call list_objects() to understand the current layout\n"
    "2. Call list_furniture_catalog() if you need to know available furniture types\n"
    "3. Make changes with add_furniture, add_wall, move_object, rotate_object, remove_object\n"
    "4. Confirm what you did briefly\n"
    "Keep responses concise. The editor auto-syncs with your changes."
)

_TOOLS = [
    {"name": "list_furniture_catalog", "description": "List all available furniture types with dimensions.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_objects", "description": "List all objects in the current layout with index, type, position.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "add_furniture", "description": "Add a furniture item at a position.",
     "input_schema": {"type": "object", "properties": {
         "furniture_type": {"type": "string", "description": "Type from catalog (e.g. bed_queen, sofa_3, desk)"},
         "x": {"type": "number", "description": "X position in meters", "default": 0},
         "z": {"type": "number", "description": "Z position in meters", "default": 0},
         "rotation_deg": {"type": "number", "description": "Rotation in degrees", "default": 0},
     }, "required": ["furniture_type"]}},
    {"name": "add_wall", "description": "Add a wall segment between two points.",
     "input_schema": {"type": "object", "properties": {
         "x1": {"type": "number"}, "z1": {"type": "number"},
         "x2": {"type": "number"}, "z2": {"type": "number"},
         "height": {"type": "number", "default": 2.6},
         "thickness": {"type": "number", "default": 0.15},
     }, "required": ["x1", "z1", "x2", "z2"]}},
    {"name": "move_object", "description": "Move an object to a new XZ position.",
     "input_schema": {"type": "object", "properties": {
         "index": {"type": "integer", "description": "Object index from list_objects"},
         "x": {"type": "number"}, "z": {"type": "number"},
     }, "required": ["index", "x", "z"]}},
    {"name": "rotate_object", "description": "Set an object's rotation in degrees.",
     "input_schema": {"type": "object", "properties": {
         "index": {"type": "integer"}, "rotation_deg": {"type": "number"},
     }, "required": ["index", "rotation_deg"]}},
    {"name": "remove_object", "description": "Remove an object by index.",
     "input_schema": {"type": "object", "properties": {
         "index": {"type": "integer"},
     }, "required": ["index"]}},
    {"name": "clear_layout", "description": "Remove all objects.",
     "input_schema": {"type": "object", "properties": {}}},
]

_DISPATCH = {
    "list_furniture_catalog": lambda a: list_furniture_catalog(),
    "list_objects": lambda a: list_objects(),
    "add_furniture": lambda a: add_furniture(**a),
    "add_wall": lambda a: add_wall(**a),
    "move_object": lambda a: move_object(**a),
    "rotate_object": lambda a: rotate_object(**a),
    "remove_object": lambda a: remove_object(**a),
    "clear_layout": lambda a: clear_layout(),
}


def _serialize_content(content):
    out = []
    for block in content:
        if block.type == "text":
            out.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            out.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
    return out


async def _chat_status(request: Request):
    if not _HAS_ANTHROPIC:
        return JSONResponse({"available": False, "reason": "anthropic SDK not installed. Run: uv pip install anthropic"})
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return JSONResponse({"available": False, "reason": "Set ANTHROPIC_API_KEY env var to enable AI chat."})
    return JSONResponse({"available": True})


async def _chat(request: Request):
    if not _HAS_ANTHROPIC:
        return JSONResponse({"error": "anthropic SDK not installed"}, 400)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return JSONResponse({"error": "ANTHROPIC_API_KEY not set"}, 400)

    body = await request.json()
    user_msg = body.get("message", "")
    history = body.get("history", [])

    client = anthropic.Anthropic(api_key=api_key)
    messages = history + [{"role": "user", "content": user_msg}]

    for _ in range(10):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=_SYSTEM,
                tools=_TOOLS,
                messages=messages,
            )
        except Exception as e:
            return JSONResponse({"error": str(e)}, 500)

        content = _serialize_content(response.content)
        messages.append({"role": "assistant", "content": content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            return JSONResponse({"response": text, "history": messages})

        results = []
        for tu in tool_uses:
            fn = _DISPATCH.get(tu.name)
            result = fn(tu.input) if fn else f"Unknown tool: {tu.name}"
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result})
        messages.append({"role": "user", "content": results})

    return JSONResponse({"error": "Too many tool iterations"}, 500)


def create_app(root_dir: str) -> Starlette:
    return Starlette(routes=[
        Route("/api/chat/status", _chat_status, methods=["GET"]),
        Route("/api/chat", _chat, methods=["POST"]),
        Mount("/", StaticFiles(directory=root_dir, html=True)),
    ])


def run_server(root_dir: str, port: int = 8080) -> None:
    app = create_app(root_dir)
    uvicorn.run(app, host="127.0.0.1", port=port)
