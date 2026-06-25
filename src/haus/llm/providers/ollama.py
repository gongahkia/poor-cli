from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from typing import Any
from urllib.request import Request, urlopen

from ..types import ChatChunk


def _base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def _tools(tools_spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in tools_spec
    ]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    lines: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            lines.append(str(block.get("text", "")))
        elif block.get("type") == "tool_result":
            lines.append(str(block.get("content", "")))
    return "\n".join(line for line in lines if line)


def _messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{"role": "system", "content": system}]
    for msg in messages:
        role = str(msg.get("role", "user"))
        if role == "user" and isinstance(msg.get("content"), list) and msg["content"] and msg["content"][0].get("type") == "tool_result":
            for block in msg["content"]:
                out.append({"role": "tool", "content": str(block.get("content", ""))})
            continue
        text = _content_text(msg.get("content"))
        if text:
            out.append({"role": "assistant" if role == "assistant" else "user", "content": text})
    return out


def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(f"{_base_url()}/api/chat", data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as response:  # noqa: S310 - local configurable Ollama endpoint.
        return json.loads(response.read().decode("utf-8"))


def _call_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
    del api_key
    ollama_messages = _messages(system, messages)
    tools = _tools(tools_spec)
    for _ in range(max_tool_steps):
        body = _post_chat({"model": model, "messages": ollama_messages, "tools": tools, "stream": False})
        msg = body.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        text = str(msg.get("content", ""))
        if not tool_calls:
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages
        assistant_content: list[dict[str, Any]] = []
        if text:
            assistant_content.append({"type": "text", "text": text})
        ollama_messages.append(msg)
        tool_results: list[dict[str, Any]] = []
        for index, call in enumerate(tool_calls):
            fn = call.get("function", {}) if isinstance(call, dict) else {}
            name = str(fn.get("name", ""))
            args = _call_args(fn.get("arguments", {}))
            result = dispatch(name, args)
            call_id = str(call.get("id", f"ollama-call-{index}")) if isinstance(call, dict) else f"ollama-call-{index}"
            assistant_content.append({"type": "tool_use", "id": call_id, "name": name, "input": args})
            tool_results.append({"type": "tool_result", "tool_use_id": call_id, "content": result})
            ollama_messages.append({"role": "tool", "content": result})
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
    del api_key
    payload = {"model": model, "messages": _messages(system, messages), "tools": _tools(tools_spec), "stream": True}
    req = Request(f"{_base_url()}/api/chat", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    text_parts: list[str] = []
    with urlopen(req, timeout=120) as response:  # noqa: S310 - local configurable Ollama endpoint.
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            event = json.loads(line)
            msg = event.get("message", {})
            delta = str(msg.get("content", ""))
            if delta:
                text_parts.append(delta)
                yield ChatChunk("text", {"delta": delta})
            if event.get("done"):
                break
    text = "".join(text_parts)
    messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
    yield ChatChunk("done", {"response": text, "history": messages})
