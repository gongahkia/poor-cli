from __future__ import annotations

import base64
import importlib
from collections.abc import Callable, Iterator
from typing import Any

from ..types import ChatChunk
from .common import decode_image_source, load_provider_module


def _gemini_type(ptype: Any) -> str:
    if ptype == "number":
        return "NUMBER"
    if ptype == "integer":
        return "INTEGER"
    if ptype == "boolean":
        return "BOOLEAN"
    if ptype == "array":
        return "ARRAY"
    return "STRING"


def _legacy_parts(content: Any) -> list[Any]:
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
            decoded = decode_image_source(block)
            if decoded is not None:
                media_type, data = decoded
                parts.append({"mime_type": media_type, "data": data})
    return parts


def _chat_legacy(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    genai = load_provider_module("google.generativeai", "Google Gemini")
    genai.configure(api_key=api_key)

    func_decls = []
    for tool in tools_spec:
        params = tool["parameters"].get("properties", {})
        required = tool["parameters"].get("required", [])
        schema_params: dict[str, Any] = {}
        for name, spec in params.items():
            schema_params[name] = {"type_": _gemini_type(spec.get("type")), "description": spec.get("description", "")}
        schema = None
        if schema_params:
            schema = genai.protos.Schema(
                type_=genai.protos.Type.OBJECT,
                properties={
                    key: genai.protos.Schema(type_=getattr(genai.protos.Type, value["type_"]), description=value["description"])
                    for key, value in schema_params.items()
                },
                required=required,
            )
        func_decls.append(genai.protos.FunctionDeclaration(name=tool["name"], description=tool["description"], parameters=schema))

    tool_config = genai.protos.Tool(function_declarations=func_decls)
    gmodel = genai.GenerativeModel(model, system_instruction=system, tools=[tool_config])

    history: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list) and content and content[0].get("type") == "tool_result":
            continue
        parts = _legacy_parts(content)
        if parts:
            history.append({"role": "user" if msg["role"] == "user" else "model", "parts": parts})

    chat_session = gmodel.start_chat(history=history[:-1] if len(history) > 1 else [])
    last_msg = history[-1]["parts"] if history else ""
    for _ in range(max_tool_steps):
        response = chat_session.send_message(last_msg)
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
                    function_response=genai.protos.FunctionResponse(name=call.function_call.name, response={"result": result})
                )
            )
        last_msg = func_responses

    raise RuntimeError("Too many tool iterations")


def _genai_contents(messages: list[dict[str, Any]]) -> list[Any]:
    contents: list[Any] = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        content = msg.get("content")
        if isinstance(content, list) and content and content[0].get("type") == "tool_result":
            continue
        parts: list[Any] = []
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append({"text": str(block.get("text", ""))})
                elif block.get("type") == "image":
                    decoded = decode_image_source(block)
                    if decoded is not None:
                        media_type, data = decoded
                        parts.append({"inline_data": {"mime_type": media_type, "data": base64.b64encode(data).decode("ascii")}})
        if parts:
            contents.append({"role": role, "parts": parts})
    return contents


def _chat_google_genai(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    genai = importlib.import_module("google.genai")
    types = importlib.import_module("google.genai.types")
    client = genai.Client(api_key=api_key)
    declarations = [
        types.FunctionDeclaration(
            name=str(tool["name"]),
            description=str(tool["description"]),
            parameters_json_schema=tool["parameters"],
        )
        for tool in tools_spec
    ]
    config = types.GenerateContentConfig(system_instruction=system, tools=[types.Tool(function_declarations=declarations)])
    contents = _genai_contents(messages)

    for _ in range(max_tool_steps):
        response = client.models.generate_content(model=model, contents=contents, config=config)
        parts = getattr(getattr(response.candidates[0], "content", None), "parts", []) if getattr(response, "candidates", None) else []
        calls = [part.function_call for part in parts if getattr(part, "function_call", None)]
        if not calls:
            text = getattr(response, "text", "") or "".join(str(getattr(part, "text", "")) for part in parts if getattr(part, "text", ""))
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages
        follow_parts: list[Any] = []
        for call in calls:
            args = dict(getattr(call, "args", {}) or {})
            name = str(getattr(call, "name", ""))
            result = dispatch(name, args)
            follow_parts.append(types.Part.from_function_response(name=name, response={"result": result}))
        contents.append({"role": "model", "parts": parts})
        contents.append({"role": "user", "parts": follow_parts})

    raise RuntimeError("Too many tool iterations")


def chat(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    try:
        return _chat_google_genai(
            api_key,
            messages,
            model,
            dispatch,
            system=system,
            tools_spec=tools_spec,
            max_tool_steps=max_tool_steps,
        )
    except ModuleNotFoundError:
        return _chat_legacy(
            api_key,
            messages,
            model,
            dispatch,
            system=system,
            tools_spec=tools_spec,
            max_tool_steps=max_tool_steps,
        )


def stream_chat(
    api_key: str,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> Iterator[ChatChunk]:
    text, updated = chat(
        api_key,
        messages,
        model,
        dispatch,
        system=system,
        tools_spec=tools_spec,
        max_tool_steps=max_tool_steps,
    )
    if text:
        yield ChatChunk("text", {"delta": text})
    yield ChatChunk("done", {"response": text, "history": updated})
