from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, cast

from ..types import ChatChunk
from .common import load_provider_module


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
    anthropic = load_provider_module("anthropic", "Anthropic")
    client = anthropic.Anthropic(api_key=api_key)
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools_spec]

    for _ in range(max_tool_steps):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            tools=cast(Any, tools),
            messages=messages,
        )

        content: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)})

        messages.append({"role": "assistant", "content": content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            return text, messages

        results: list[dict[str, Any]] = []
        for tool_use in tool_uses:
            result = dispatch(tool_use.name, dict(tool_use.input))
            results.append({"type": "tool_result", "tool_use_id": tool_use.id, "content": result})
        messages.append({"role": "user", "content": results})

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
    anthropic = load_provider_module("anthropic", "Anthropic")
    client = anthropic.Anthropic(api_key=api_key)
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools_spec]

    for _ in range(max_tool_steps):
        try:
            with client.messages.stream(
                model=model,
                max_tokens=1024,
                system=system,
                tools=cast(Any, tools),
                messages=messages,
            ) as stream:
                for event in stream:
                    if getattr(event, "type", "") == "content_block_delta":
                        delta = getattr(getattr(event, "delta", None), "text", "")
                        if delta:
                            yield ChatChunk("text", {"delta": str(delta)})
                response = stream.get_final_message()
        except AttributeError:
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
            return

        content: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)})

        messages.append({"role": "assistant", "content": content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            yield ChatChunk("done", {"response": text, "history": messages})
            return

        results: list[dict[str, Any]] = []
        for tool_use in tool_uses:
            result = dispatch(tool_use.name, dict(tool_use.input))
            yield ChatChunk("tool_result", {"tool": tool_use.name, "result": result})
            results.append({"type": "tool_result", "tool_use_id": tool_use.id, "content": result})
        messages.append({"role": "user", "content": results})

    raise RuntimeError("Too many tool iterations")
