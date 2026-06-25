from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any, cast

from ..types import ChatChunk
from .common import image_data_url, load_provider_module, safe_json_args, strict_parameters, text_blocks


def _responses_tools(tools_spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": str(tool["name"]),
            "description": str(tool["description"]),
            "parameters": strict_parameters(cast(dict[str, Any], tool["parameters"])),
            "strict": True,
        }
        for tool in tools_spec
    ]


def _chat_completion_tools(tools_spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": str(tool["name"]),
                "description": str(tool["description"]),
                "parameters": strict_parameters(cast(dict[str, Any], tool["parameters"])),
                "strict": True,
            },
        }
        for tool in tools_spec
    ]


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
            data_url = image_data_url(block)
            if data_url:
                has_image = True
                blocks.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})
    if not has_image:
        return "\n".join(str(block.get("text", "")) for block in blocks if block.get("type") == "text")
    return blocks


def _to_chat_completion_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    oai: list[dict[str, Any]] = [{"role": "system", "content": system}]
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
            entry: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts) if texts else None}
            if tool_uses:
                entry["tool_calls"] = [
                    {
                        "id": tool_use["id"],
                        "type": "function",
                        "function": {"name": tool_use["name"], "arguments": json.dumps(tool_use.get("input", {}))},
                    }
                    for tool_use in tool_uses
                ]
            oai.append(entry)
            continue
        if role == "user" and content and content[0].get("type") == "tool_result":
            for block in content:
                oai.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": block["content"]})
            continue
        if role == "user":
            oai.append({"role": role, "content": _to_oai_user_content(content)})
        else:
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            oai.append({"role": role, "content": "\n".join(texts) if texts else ""})
    return oai


def _to_response_content(role: str, content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    blocks: list[dict[str, Any]] = []
    text_type = "output_text" if role == "assistant" else "input_text"
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = str(block.get("text", ""))
            if text:
                blocks.append({"type": text_type, "text": text})
        elif block.get("type") == "image" and role == "user":
            data_url = image_data_url(block)
            if data_url:
                blocks.append({"type": "input_image", "image_url": data_url})
    return blocks or "\n".join(text_blocks(content))


def _to_response_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role", "user"))
        content = msg.get("content")
        if role == "user" and isinstance(content, list) and content and content[0].get("type") == "tool_result":
            for block in content:
                items.append({"type": "function_call_output", "call_id": block["tool_use_id"], "output": block["content"]})
            continue
        if role not in {"user", "assistant", "developer", "system"}:
            role = "user"
        items.append({"role": role, "content": _to_response_content(role, content)})
    return items


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", "")
    if text:
        return str(text)
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            part = getattr(content, "text", "")
            if part:
                chunks.append(str(part))
    return "".join(chunks)


def _response_function_calls(response: Any) -> list[Any]:
    return [item for item in getattr(response, "output", []) or [] if getattr(item, "type", "") == "function_call"]


def _chat_completions(
    client: Any,
    messages: list[dict[str, Any]],
    model: str,
    dispatch: Callable[[str, dict[str, Any]], str],
    *,
    system: str,
    tools_spec: list[dict[str, Any]],
    max_tool_steps: int,
) -> tuple[str, list[dict[str, Any]]]:
    tools = _chat_completion_tools(tools_spec)
    oai_messages = _to_chat_completion_messages(system, messages)
    for _ in range(max_tool_steps):
        response = client.chat.completions.create(model=model, messages=oai_messages, tools=cast(Any, tools), max_tokens=1024)
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
                        "id": tool_call.id,
                        "type": "function",
                        "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments},
                    }
                    for tool_call in tool_calls
                ],
            }
        )
        if msg.content:
            assistant_content.append({"type": "text", "text": msg.content})
        tool_results: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            args = safe_json_args(tool_call.function.arguments)
            result = dispatch(tool_call.function.name, args)
            oai_messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
            assistant_content.append({"type": "tool_use", "id": tool_call.id, "name": tool_call.function.name, "input": args})
            tool_results.append({"type": "tool_result", "tool_use_id": tool_call.id, "content": result})
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})
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
    openai = load_provider_module("openai", "OpenAI")
    client = openai.OpenAI(api_key=api_key)
    if not hasattr(client, "responses"):
        return _chat_completions(client, messages, model, dispatch, system=system, tools_spec=tools_spec, max_tool_steps=max_tool_steps)

    tools = _responses_tools(tools_spec)
    response_input = _to_response_input(messages)
    for _ in range(max_tool_steps):
        response = client.responses.create(
            model=model,
            instructions=system,
            input=response_input,
            tools=cast(Any, tools),
            max_output_tokens=1024,
        )
        calls = _response_function_calls(response)
        if not calls:
            text = _extract_response_text(response)
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages

        assistant_content: list[dict[str, Any]] = []
        response_input.extend(getattr(response, "output", []) or [])
        text = _extract_response_text(response)
        if text:
            assistant_content.append({"type": "text", "text": text})
        tool_results: list[dict[str, Any]] = []
        for call in calls:
            args = safe_json_args(getattr(call, "arguments", "{}"))
            call_id = str(getattr(call, "call_id", getattr(call, "id", "")))
            name = str(getattr(call, "name", ""))
            result = dispatch(name, args)
            response_input.append({"type": "function_call_output", "call_id": call_id, "output": result})
            assistant_content.append({"type": "tool_use", "id": call_id, "name": name, "input": args})
            tool_results.append({"type": "tool_result", "tool_use_id": call_id, "content": result})
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError("Too many tool iterations")


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
