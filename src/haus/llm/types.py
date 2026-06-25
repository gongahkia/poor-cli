from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal


DispatchFn = Callable[[str, dict[str, Any]], str]
ChatFn = Callable[[str, list[dict[str, Any]], str, DispatchFn], tuple[str, list[dict[str, Any]]]]
StreamFn = Callable[[str, list[dict[str, Any]], str, DispatchFn], Iterator["ChatChunk"]]


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    capabilities: tuple[str, ...] = ()
    default: bool = False
    notes: str = ""


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    env_var: str
    default_model: str
    optional_extra: str
    install_hint: str
    capabilities: tuple[str, ...]
    models: tuple[ModelSpec, ...]
    requires_api_key: bool = True
    base_url_env: str = ""
    allow_custom_models: bool = True


@dataclass(frozen=True)
class ChatResult:
    text: str
    history: list[dict[str, Any]]
    provider: str
    model: str
    response_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatChunk:
    type: Literal["text", "tool_call", "tool_result", "error", "done", "meta"]
    data: dict[str, Any]

    def sse_event(self) -> str:
        import json

        return f"event: {self.type}\ndata: {json.dumps(self.data, separators=(',', ':'))}\n\n"
