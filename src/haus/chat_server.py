"""Combined static file server + AI chat API for the haus editor.

Serves the viewer files and provides a /api/chat endpoint that uses
configurable LLM providers (Anthropic, OpenAI, Gemini) with tool use.
"""
from __future__ import annotations
import json
import logging
import mimetypes
import os
from pathlib import Path

log = logging.getLogger("haus.chat")
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
import uvicorn
from .mcp_server import (
    list_furniture_catalog, list_objects, add_furniture, add_wall,
    move_object, rotate_object, remove_object, remove_objects_by_type,
    clear_layout, get_layout_json,
    get_object_details, get_layout_summary, resize_object,
    set_color, set_visibility, duplicate_object, batch_move,
)

mimetypes.add_type("model/gltf-binary", ".glb")

_SYSTEM = (
    "You are an AI assistant for the haus floor plan editor. "
    "You ONLY help with floor plan editing — arranging furniture, walls, and layout. "
    "If the user asks something unrelated (general knowledge, coding, etc), "
    "politely decline and remind them you only handle floor plan tasks.\n\n"
    "Coordinate system: X is left-right, Z is forward-back. Positions are in meters.\n"
    "Typical room sizes: bedrooms ~3x3m, living rooms ~4x5m, bathrooms ~2x2m, kitchens ~2.5x3m.\n\n"
    "IMPORTANT RULES:\n"
    "- Before any DESTRUCTIVE action (removing, clearing, or replacing objects), "
    "FIRST describe what you plan to do and ASK for confirmation. "
    "Only proceed after the user confirms. Examples of destructive actions: "
    "remove_object, remove_objects_by_type, clear_layout.\n"
    "- For adding, moving, resizing, recoloring, or hiding objects, proceed directly.\n"
    "- When removing multiple objects, use remove_objects_by_type instead of "
    "calling remove_object in a loop (indices shift after each removal).\n"
    "- batch_move uses RELATIVE offsets (dx, dz), not absolute positions.\n\n"
    "Workflow:\n"
    "1. Call get_layout_summary() for a quick overview of the current layout\n"
    "2. Call list_objects() or get_object_details(index) for specifics\n"
    "3. Call list_furniture_catalog() if you need available furniture types\n"
    "4. Make changes with add_furniture, add_wall, move_object, rotate_object, "
    "remove_object, remove_objects_by_type, resize_object, set_color, "
    "set_visibility, duplicate_object, batch_move\n"
    "5. Confirm what you did briefly\n"
    "Keep responses concise. The editor auto-syncs with your changes."
)

_TOOLS_SPEC = [
    {"name": "list_furniture_catalog", "description": "List all available furniture types with dimensions.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "list_objects", "description": "List all objects in the current layout with index, type, position.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "add_furniture", "description": "Add a furniture item at a position.",
     "parameters": {"type": "object", "properties": {
         "furniture_type": {"type": "string", "description": "Type from catalog (e.g. bed_queen, sofa_3, desk)"},
         "x": {"type": "number", "description": "X position in meters", "default": 0},
         "z": {"type": "number", "description": "Z position in meters", "default": 0},
         "rotation_deg": {"type": "number", "description": "Rotation in degrees", "default": 0},
     }, "required": ["furniture_type"]}},
    {"name": "add_wall", "description": "Add a wall segment between two points.",
     "parameters": {"type": "object", "properties": {
         "x1": {"type": "number"}, "z1": {"type": "number"},
         "x2": {"type": "number"}, "z2": {"type": "number"},
         "height": {"type": "number", "default": 2.6},
         "thickness": {"type": "number", "default": 0.15},
     }, "required": ["x1", "z1", "x2", "z2"]}},
    {"name": "move_object", "description": "Move an object to a new XZ position.",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer", "description": "Object index from list_objects"},
         "x": {"type": "number"}, "z": {"type": "number"},
     }, "required": ["index", "x", "z"]}},
    {"name": "rotate_object", "description": "Set an object's rotation in degrees.",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer"}, "rotation_deg": {"type": "number"},
     }, "required": ["index", "rotation_deg"]}},
    {"name": "remove_object", "description": "Remove an object by index.",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer"},
     }, "required": ["index"]}},
    {"name": "remove_objects_by_type", "description": "Remove all objects of a given type (e.g. 'wall', 'model_part', or a furniture type).",
     "parameters": {"type": "object", "properties": {
         "object_type": {"type": "string", "description": "Type to remove: 'wall', 'model_part', or furniture type like 'bed_queen'"},
     }, "required": ["object_type"]}},
    {"name": "clear_layout", "description": "Remove all objects.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_object_details", "description": "Get full details for one object: type, position, rotation, dimensions, color, visibility.",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer", "description": "Object index from list_objects"},
     }, "required": ["index"]}},
    {"name": "get_layout_summary", "description": "Get layout summary: object counts by type, furniture breakdown, hidden count, XZ bounding box.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "resize_object", "description": "Resize an object. Only provided dimensions are changed. Min 0.05m.",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer", "description": "Object index"},
         "width": {"type": "number", "description": "New width in meters (X axis)"},
         "height": {"type": "number", "description": "New height in meters (Y axis)"},
         "depth": {"type": "number", "description": "New depth in meters (Z axis)"},
     }, "required": ["index"]}},
    {"name": "set_color", "description": "Set an object's color via hex string (e.g. '#ff0000').",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer", "description": "Object index"},
         "color": {"type": "string", "description": "Hex color string like '#ff0000'"},
     }, "required": ["index", "color"]}},
    {"name": "set_visibility", "description": "Show or hide an object.",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer", "description": "Object index"},
         "visible": {"type": "boolean", "description": "True to show, false to hide"},
     }, "required": ["index", "visible"]}},
    {"name": "duplicate_object", "description": "Duplicate an object to a new position, preserving all properties.",
     "parameters": {"type": "object", "properties": {
         "index": {"type": "integer", "description": "Object index to duplicate"},
         "x": {"type": "number", "description": "X position for the copy"},
         "z": {"type": "number", "description": "Z position for the copy"},
     }, "required": ["index", "x", "z"]}},
    {"name": "batch_move", "description": "Move multiple objects by a relative offset. Validates all indices before applying.",
     "parameters": {"type": "object", "properties": {
         "indices": {"type": "array", "items": {"type": "integer"}, "description": "List of object indices to move"},
         "dx": {"type": "number", "description": "Relative X offset in meters"},
         "dz": {"type": "number", "description": "Relative Z offset in meters"},
     }, "required": ["indices", "dx", "dz"]}},
]

_DISPATCH_RAW = {
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
}

_tool_log: list[dict] = []  # collects tool calls per request


def _dispatch(name: str, args: dict) -> str:
    fn = _DISPATCH_RAW.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    result = fn(args)
    entry = {"tool": name, "args": args, "result": result}
    _tool_log.append(entry)
    log.info("tool %s(%s) -> %s", name, json.dumps(args), result[:200] if len(result) > 200 else result)
    return result

# --- provider detection ---

def _detect_provider() -> tuple[str, str]:
    """Return (provider_name, api_key) from env vars. Checks in order: Anthropic, OpenAI, Gemini."""
    for env, name in [
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("OPENAI_API_KEY", "openai"),
        ("GEMINI_API_KEY", "gemini"),
    ]:
        key = os.environ.get(env)
        if key:
            return name, key
    return "", ""


def _provider_available() -> dict:
    """Check which providers are available."""
    providers = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append("anthropic")
    if os.environ.get("OPENAI_API_KEY"):
        providers.append("openai")
    if os.environ.get("GEMINI_API_KEY"):
        providers.append("gemini")
    return providers


# --- Anthropic provider ---

def _anthropic_tools():
    """Convert tool specs to Anthropic format (input_schema)."""
    return [
        {**t, "input_schema": t["parameters"]}
        for t in [{k: v for k, v in tool.items() if k != "parameters"} | {"parameters": tool["parameters"]} for tool in _TOOLS_SPEC]
    ]


def _chat_anthropic(api_key: str, messages: list, model: str) -> tuple[str, list]:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in _TOOLS_SPEC]
    for _ in range(10):
        response = client.messages.create(model=model, max_tokens=1024, system=_SYSTEM, tools=tools, messages=messages)
        content = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        messages.append({"role": "assistant", "content": content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            return text, messages
        results = []
        for tu in tool_uses:
            result = _dispatch(tu.name, tu.input)
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result})
        messages.append({"role": "user", "content": results})
    raise RuntimeError("Too many tool iterations")


# --- OpenAI provider ---

def _openai_tools():
    """Convert tool specs to OpenAI function calling format."""
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in _TOOLS_SPEC]


def _to_oai_messages(messages: list) -> list:
    """Convert internal message format to OpenAI format."""
    oai = [{"role": "system", "content": _SYSTEM}]
    for m in messages:
        role = m["role"]
        content = m.get("content")
        if isinstance(content, str):
            oai.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue
        # assistant message: group text + tool_calls into one message
        if role == "assistant":
            texts = [b["text"] for b in content if b.get("type") == "text"]
            tus = [b for b in content if b.get("type") == "tool_use"]
            entry = {"role": "assistant", "content": "\n".join(texts) if texts else None}
            if tus:
                entry["tool_calls"] = [
                    {"id": tu["id"], "type": "function", "function": {"name": tu["name"], "arguments": json.dumps(tu["input"])}}
                    for tu in tus
                ]
            oai.append(entry)
        # user message with tool_results: each becomes a separate tool message
        elif role == "user" and content and content[0].get("type") == "tool_result":
            for b in content:
                oai.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
        else:
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            oai.append({"role": role, "content": "\n".join(texts) if texts else ""})
    return oai


def _chat_openai(api_key: str, messages: list, model: str) -> tuple[str, list]:
    import openai
    client = openai.OpenAI(api_key=api_key)
    tools = _openai_tools()
    oai_messages = _to_oai_messages(messages)

    for _ in range(10):
        response = client.chat.completions.create(model=model, messages=oai_messages, tools=tools, max_tokens=1024)
        msg = response.choices[0].message
        if not msg.tool_calls:
            text = msg.content or ""
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages
        # build assistant message for both formats
        assistant_content = []
        oai_entry = {"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]}
        oai_messages.append(oai_entry)
        if msg.content:
            assistant_content.append({"type": "text", "text": msg.content})
        tool_results = []
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = _dispatch(tc.function.name, args)
            oai_messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            assistant_content.append({"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args})
            tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})
    raise RuntimeError("Too many tool iterations")


# --- Gemini provider ---

def _chat_gemini(api_key: str, messages: list, model: str) -> tuple[str, list]:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    # build function declarations
    func_decls = []
    for t in _TOOLS_SPEC:
        params = t["parameters"].get("properties", {})
        required = t["parameters"].get("required", [])
        schema_params = {}
        for pname, pspec in params.items():
            gtype = "STRING"
            if pspec.get("type") == "number":
                gtype = "NUMBER"
            elif pspec.get("type") == "integer":
                gtype = "INTEGER"
            schema_params[pname] = {"type_": gtype, "description": pspec.get("description", "")}
        func_decls.append(genai.protos.FunctionDeclaration(
            name=t["name"], description=t["description"],
            parameters=genai.protos.Schema(type_=genai.protos.Type.OBJECT, properties={
                k: genai.protos.Schema(type_=getattr(genai.protos.Type, v["type_"]), description=v["description"])
                for k, v in schema_params.items()
            }, required=required) if schema_params else None,
        ))
    tool_config = genai.protos.Tool(function_declarations=func_decls)
    gmodel = genai.GenerativeModel(model, system_instruction=_SYSTEM, tools=[tool_config])
    # convert messages to gemini content format
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        if isinstance(m.get("content"), str):
            contents.append({"role": role, "parts": [m["content"]]})
    chat = gmodel.start_chat(history=contents[:-1] if len(contents) > 1 else [])
    last_msg = contents[-1]["parts"][0] if contents else ""
    for _ in range(10):
        response = chat.send_message(last_msg)
        candidate = response.candidates[0]
        parts = candidate.content.parts
        func_calls = [p for p in parts if p.function_call.name]
        if not func_calls:
            text = "".join(p.text for p in parts if p.text)
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages
        # execute tool calls
        func_responses = []
        for fc in func_calls:
            args = dict(fc.function_call.args)
            result = _dispatch(fc.function_call.name, args)
            func_responses.append(genai.protos.Part(function_response=genai.protos.FunctionResponse(
                name=fc.function_call.name, response={"result": result})))
        last_msg = func_responses
    raise RuntimeError("Too many tool iterations")


# --- provider router ---

_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
}

_CHAT_FNS = {
    "anthropic": _chat_anthropic,
    "openai": _chat_openai,
    "gemini": _chat_gemini,
}


# --- endpoints ---

_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


async def _chat_status(request: Request):
    """Status endpoint — always available since keys can come from the client."""
    providers = _provider_available()
    return JSONResponse({"available": True, "providers": providers})


async def _chat(request: Request):
    body = await request.json()
    user_msg = body.get("message", "")
    history = body.get("history", [])
    preferred = body.get("provider", "")
    model_override = body.get("model", "")
    client_key = body.get("api_key", "")

    if not preferred:
        return JSONResponse({"error": "No provider specified."}, 400)

    # client-provided key takes priority, then env var
    api_key = client_key or os.environ.get(_ENV_KEYS.get(preferred, ""), "")
    if not api_key:
        return JSONResponse({"error": f"No API key for {preferred}. Add one in chat settings."}, 400)

    provider = preferred
    model = model_override or _DEFAULT_MODELS.get(provider, "")
    chat_fn = _CHAT_FNS.get(provider)
    if not chat_fn:
        return JSONResponse({"error": f"Provider '{provider}' not supported"}, 400)

    messages = history + [{"role": "user", "content": user_msg}]
    _tool_log.clear()
    log.info("chat request: provider=%s model=%s msg=%s", provider, model, user_msg[:100])
    try:
        text, messages = chat_fn(api_key, messages, model)
        actions = list(_tool_log)
        _tool_log.clear()
        return JSONResponse({"response": text, "history": messages, "provider": provider, "model": model, "actions": actions})
    except Exception as e:
        log.exception("chat error")
        return JSONResponse({"error": str(e)}, 500)


async def _sync_layout(request: Request):
    """Receive full layout from editor so MCP tools see all objects."""
    body = await request.json()
    if body.get("items") is not None:
        from .mcp_server import _save_layout
        _save_layout(body)
    return JSONResponse({"ok": True})


def create_app(root_dir: str) -> Starlette:
    return Starlette(routes=[
        Route("/api/chat/status", _chat_status, methods=["GET"]),
        Route("/api/chat", _chat, methods=["POST"]),
        Route("/api/sync-layout", _sync_layout, methods=["POST"]),
        Mount("/", StaticFiles(directory=root_dir, html=True)),
    ])


def run_server(root_dir: str, port: int = 8080) -> None:
    os.environ["_HAUS_ROOT"] = root_dir
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
