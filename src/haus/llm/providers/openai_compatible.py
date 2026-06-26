from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any, cast
from urllib.request import Request, urlopen

from .common import image_data_url, safe_json_args, strict_parameters


def _base_url() -> str:
    return os.environ.get("HAUS_OPENAI_COMPAT_BASE_URL", "http://localhost:1234/v1").rstrip("/")


def _api_key(api_key: str) -> str:
    env_key = os.environ.get("HAUS_OPENAI_COMPAT_API_KEY", "").strip()
    if env_key:
        return env_key
    return "" if api_key in {"", "local"} else api_key


def _tools(tools_spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": str(tool["name"]),
                "description": str(tool["description"]),
                "parameters": strict_parameters(cast(dict[str, Any], tool["parameters"])),
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


def _user_content(content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    blocks: list[dict[str, Any]] = []
    has_image = False
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = str(block.get("text", ""))
            if text:
                blocks.append({"type": "text", "text": text})
        elif block.get("type") == "image":
            data_url = image_data_url(block)
            if data_url:
                has_image = True
                blocks.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})
    if has_image:
        return blocks
    return "\n".join(str(block.get("text", "")) for block in blocks)


def _messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        role = str(msg.get("role", "user"))
        content = msg.get("content")
        if role == "assistant" and isinstance(content, list):
            texts = [str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text"]
            tool_uses = [block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"]
            entry: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts) if texts else None}
            if tool_uses:
                entry["tool_calls"] = [
                    {
                        "id": str(tool_use["id"]),
                        "type": "function",
                        "function": {"name": str(tool_use["name"]), "arguments": json.dumps(tool_use.get("input", {}))},
                    }
                    for tool_use in tool_uses
                ]
            out.append(entry)
        elif role == "user" and isinstance(content, list) and content and content[0].get("type") == "tool_result":
            for block in content:
                out.append({"role": "tool", "tool_call_id": str(block.get("tool_use_id", "")), "content": str(block.get("content", ""))})
        elif role == "user":
            out.append({"role": "user", "content": _user_content(content)})
        else:
            text = _content_text(content)
            if text:
                out.append({"role": "assistant" if role == "assistant" else "user", "content": text})
    return out


def _post_chat(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(
        f"{_base_url()}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(req, timeout=120) as response:  # noqa: S310 - user-configured local endpoint.
        return json.loads(response.read().decode("utf-8"))


def _call_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return safe_json_args(str(raw or "{}"))


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
    local_messages = _messages(system, messages)
    tools = _tools(tools_spec)
    token = _api_key(api_key)
    for _ in range(max_tool_steps):
        body = _post_chat({"model": model, "messages": local_messages, "tools": tools, "stream": False, "max_tokens": 1024}, token)
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message", {}) if isinstance(choice, dict) else {}
        tool_calls = msg.get("tool_calls") or []
        text = str(msg.get("content") or "")
        if not tool_calls:
            messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
            return text, messages

        assistant_content: list[dict[str, Any]] = []
        if text:
            assistant_content.append({"type": "text", "text": text})
        local_messages.append(
            {
                "role": "assistant",
                "content": text or None,
                "tool_calls": tool_calls,
            }
        )
        tool_results: list[dict[str, Any]] = []
        for index, call in enumerate(tool_calls):
            fn = call.get("function", {}) if isinstance(call, dict) else {}
            name = str(fn.get("name", ""))
            args = _call_args(fn.get("arguments", {}))
            result = dispatch(name, args)
            call_id = str(call.get("id", f"local-call-{index}")) if isinstance(call, dict) else f"local-call-{index}"
            local_messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            assistant_content.append({"type": "tool_use", "id": call_id, "name": name, "input": args})
            tool_results.append({"type": "tool_result", "tool_use_id": call_id, "content": result})
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})
    raise RuntimeError("Too many tool iterations")
