from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hooks import Hook, HookManager
from .fusion import fusion_params
from .provider_events import normalize_tool_calls, tool_schema_dicts
from .providers import CachedReplayProvider, Provider, ProviderRequest
from .store import RunStore
from .tools import ToolDispatcher, ToolResult


@dataclass(frozen=True)
class NativeRunResult:
    returncode: int
    stdout: str
    stderr: str
    turns: int
    tool_calls: int
    stopped_reason: str


class ProviderBackedAgentRunner:
    def __init__(
        self,
        provider: Provider,
        store: RunStore,
        run_id: str,
        workdir: Path,
        *,
        hooks: HookManager | list[Hook] | None = None,
        replay_only: bool = False,
        max_turns: int = 8,
        max_tool_calls: int = 32,
    ):
        self.store = store
        self.run_id = run_id
        self.provider = CachedReplayProvider(store, run_id, provider, replay_only=replay_only, hooks=hooks)
        self.tools = ToolDispatcher(store, run_id, workdir=workdir, replay_only=replay_only, hooks=hooks)
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls

    def run(
        self, *, provider_name: str, model: str, prompt: str, system_prompt: str, task_id: str, params: dict[str, Any]
    ) -> NativeRunResult:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        tool_count = 0
        final = ""
        context_bytes = int(params.get("_max_context_bytes") or 80_000)
        provider_params = {key: value for key, value in params.items() if not key.startswith("_")}
        for turn in range(1, self.max_turns + 1):
            messages = self._compact(messages, task_id) if _message_bytes(messages) > context_bytes else messages
            request = ProviderRequest(
                provider=provider_name,
                model=model,
                prompt=prompt,
                system_prompt=system_prompt,
                messages=messages,
                params={**provider_params, "function_tools": tool_schema_dicts(list(self.tools.schemas.values()))},
            )
            response = self.provider.call(request)
            calls = normalize_tool_calls(provider_name, response.raw)
            final = response.content
            self.store.append_event(
                self.run_id,
                "native.turn.completed",
                {"turn": turn, "tool_calls": len(calls), "cached": response.cached},
                task_id,
            )
            if not calls:
                return NativeRunResult(0, final, "", turn, tool_count, "final")
            assistant_items = _assistant_messages(provider_name, response.raw, response.content)
            messages.extend(assistant_items)
            for call in calls:
                if tool_count >= self.max_tool_calls:
                    self.store.append_event(self.run_id, "native.budget_stopped", {"reason": "max_tool_calls"}, task_id)
                    return NativeRunResult(1, final, "native tool-call budget stopped", turn, tool_count, "max_tool_calls")
                result = self.tools.call(call.name, call.arguments, task_id)
                tool_count += 1
                messages.append(_tool_message(provider_name, call.id, call.name, result))
        self.store.append_event(self.run_id, "native.budget_stopped", {"reason": "max_turns"}, task_id)
        return NativeRunResult(1, final, "native turn budget stopped", self.max_turns, tool_count, "max_turns")

    def _compact(self, messages: list[dict[str, Any]], task_id: str) -> list[dict[str, Any]]:
        summary = {
            "role": "system",
            "content": "Compacted prior native-runner transcript deterministically; preserve task, route, tool state, and open work.",
        }
        compacted = [messages[0], summary, *messages[-6:]]
        self.store.append_event(self.run_id, "native.context_compacted", {"from": len(messages), "to": len(compacted)}, task_id)
        return compacted


def native_params(provider_name: str, system_prompt: str, prompt: str, route: dict[str, Any] | None = None) -> dict[str, Any]:
    route = route or {}
    params: dict[str, Any] = {}
    effort = route.get("reasoning_effort") or route.get("effort")
    verbosity = route.get("text_verbosity") or route.get("verbosity")
    if provider_name == "openai":
        if effort in {"low", "medium", "high", "xhigh"}:
            params["reasoning_effort"] = effort
        if verbosity in {"terse", "low"}:
            params["text_verbosity"] = "low"
        elif verbosity in {"normal", "medium"}:
            params["text_verbosity"] = "medium"
        elif verbosity in {"verbose", "high"}:
            params["text_verbosity"] = "high"
        params["prompt_cache_key"] = "poor-cli:" + hashlib.sha256((system_prompt + "\n" + prompt).encode()).hexdigest()[:32]
    if provider_name == "openrouter" and (route.get("fusion") or "fusion" in str(route.get("model") or "").lower()):
        params["fusion"] = fusion_params(route)
    if provider_name == "kimi":
        max_context = _int(route.get("max_context_tokens"))
        if max_context >= 200_000:
            params["_max_context_bytes"] = max_context * 3
    return params


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _assistant_messages(provider: str, raw: dict[str, Any], content: str) -> list[dict[str, Any]]:
    if provider == "openai" and isinstance(raw.get("output"), list):
        return [item for item in raw["output"] if isinstance(item, dict)]
    if provider == "anthropic" and isinstance(raw.get("content"), list):
        return [{"role": "assistant", "content": raw["content"]}]
    choices = raw.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict) and isinstance(choices[0].get("message"), dict):
        return [choices[0]["message"]]
    return [{"role": "assistant", "content": content}]


def _tool_message(provider: str, call_id: str, name: str, result: ToolResult) -> dict[str, Any]:
    text = json.dumps({"ok": result.ok, "output": result.output, "error": result.error}, ensure_ascii=False, sort_keys=True)
    if provider == "openai":
        return {"type": "function_call_output", "call_id": call_id, "output": text}
    if provider == "anthropic":
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": text}]}
    if provider == "gemini":
        return {"role": "user", "parts": [{"function_response": {"name": name, "response": {"result": text}}}]}
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": text}


def _message_bytes(messages: list[dict[str, Any]]) -> int:
    return len(json.dumps(messages, ensure_ascii=False, sort_keys=True, default=str).encode())
