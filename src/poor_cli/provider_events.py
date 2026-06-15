from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool = True


@dataclass(frozen=True)
class ProviderToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProviderEvent:
    type: str
    text_delta: str = ""
    tool_call: ProviderToolCall | None = None
    raw: dict[str, Any] | None = None


CAPABILITIES: dict[str, dict[str, Any]] = {
    "openai": {"tools": True, "streaming": True, "structured_outputs": True, "web": True, "cache": True, "multimodal": True},
    "anthropic": {"tools": True, "streaming": True, "structured_outputs": False, "web": False, "cache": False, "multimodal": True},
    "gemini": {"tools": True, "streaming": True, "structured_outputs": True, "web": True, "cache": False, "multimodal": True},
    "openai-compatible": {"tools": True, "streaming": True, "structured_outputs": True, "web": False, "cache": False, "multimodal": False},
    "vllm": {"tools": True, "streaming": True, "structured_outputs": True, "web": False, "cache": True, "multimodal": False},
    "sglang": {"tools": True, "streaming": True, "structured_outputs": True, "web": False, "cache": True, "multimodal": False},
    "ollama": {"tools": False, "streaming": False, "structured_outputs": False, "web": False, "cache": False, "multimodal": False},
}


def provider_capabilities(kind: str, context_window: int | None = None) -> dict[str, Any]:
    caps = dict(CAPABILITIES.get(kind, CAPABILITIES["openai-compatible"]))
    caps["max_context"] = context_window
    return caps


def tool_schema_dicts(schemas: list[ToolSchema]) -> list[dict[str, Any]]:
    return [asdict(schema) for schema in schemas]


def normalize_tool_calls(provider: str, raw: dict[str, Any]) -> list[ProviderToolCall]:
    calls = _direct_calls(raw)
    if provider == "openai":
        calls += _openai_calls(raw)
    elif provider == "anthropic":
        calls += _anthropic_calls(raw)
    elif provider == "gemini":
        calls += _gemini_calls(raw)
    else:
        calls += _chat_calls(raw)
    seen: set[tuple[str, str]] = set()
    out = []
    for call in calls:
        key = (call.id, call.name)
        if call.name and key not in seen:
            seen.add(key)
            out.append(call)
    return out


def normalize_events(provider: str, raw: dict[str, Any]) -> list[ProviderEvent]:
    events = []
    for event in raw.get("events", []) if isinstance(raw.get("events"), list) else []:
        if isinstance(event, dict):
            delta = event.get("delta") if event.get("type") in {"response.output_text.delta", "content_block_delta"} else ""
            events.append(ProviderEvent(type=str(event.get("type") or "provider.event"), text_delta=str(delta or ""), raw=event))
    events.extend(ProviderEvent(type="tool_call", tool_call=call, raw={}) for call in normalize_tool_calls(provider, raw))
    return events


def _direct_calls(raw: dict[str, Any]) -> list[ProviderToolCall]:
    items = raw.get("tool_calls")
    if not isinstance(items, list):
        return []
    return [_call(item) for item in items if isinstance(item, dict)]


def _openai_calls(raw: dict[str, Any]) -> list[ProviderToolCall]:
    calls = []
    for item in raw.get("output", []) if isinstance(raw.get("output"), list) else []:
        if isinstance(item, dict) and item.get("type") in {"function_call", "custom_tool_call"}:
            calls.append(_call(item))
    for event in raw.get("events", []) if isinstance(raw.get("events"), list) else []:
        if isinstance(event, dict) and str(event.get("type")) == "response.function_call_arguments.done":
            item = event.get("item")
            calls.append(_call(item if isinstance(item, dict) else event))
    return calls


def _anthropic_calls(raw: dict[str, Any]) -> list[ProviderToolCall]:
    return [
        _call(block)
        for block in raw.get("content", [])
        if isinstance(raw.get("content"), list)
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def _gemini_calls(raw: dict[str, Any]) -> list[ProviderToolCall]:
    calls = []
    for cand in raw.get("candidates", []) if isinstance(raw.get("candidates"), list) else []:
        parts = cand.get("content", {}).get("parts", []) if isinstance(cand, dict) else []
        for part in parts if isinstance(parts, list) else []:
            fc = part.get("functionCall") or part.get("function_call") if isinstance(part, dict) else None
            if isinstance(fc, dict):
                calls.append(_call(fc))
    return calls


def _chat_calls(raw: dict[str, Any]) -> list[ProviderToolCall]:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return []
    msg = choices[0].get("message")
    items = msg.get("tool_calls") if isinstance(msg, dict) else None
    return [_call(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _call(item: dict[str, Any]) -> ProviderToolCall:
    fn = item.get("function")
    fn = fn if isinstance(fn, dict) else item
    raw_args = fn.get("arguments", item.get("arguments", item.get("input", item.get("args", {}))))
    return ProviderToolCall(
        str(item.get("call_id") or item.get("id") or ""),
        str(fn.get("name") or item.get("name") or ""),
        _args(raw_args),
    )


def _args(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {"input": value}
        return loaded if isinstance(loaded, dict) else {"value": loaded}
    return {}
