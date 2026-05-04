"""Shadow next-tool prediction for default-off speculative warming.

Phase 1 intentionally does not implement provider-side speculative decoding:
public provider APIs do not expose useful draft-token verification semantics for
tool-use traces. This module instead predicts the next read-only tool call and
warms session caches in the background. A mismatch is harmless because warmed
entries are one-turn, in-memory cache entries.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional

from poor_cli.tool_blocks import ToolResult, wrap_legacy_result


READ_ONLY_TOOL_WHITELIST = {
    "read_file",
    "glob_files",
    "grep_files",
    "git_status",
    "git_diff",
    "list_directory",
    "semantic_search",
}
MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class SpeculativePrediction:
    tool: str
    args: Dict[str, Any]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "args": dict(self.args), "confidence": self.confidence}


@dataclass(frozen=True)
class WarmResult:
    warmed: bool
    tool: str = ""
    reason: str = ""
    from_speculation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "warmed": self.warmed,
            "tool": self.tool,
            "reason": self.reason,
            "from_speculation": self.from_speculation,
        }


ToolDispatcher = Callable[[str, Dict[str, Any]], Awaitable[Any] | Any]


async def predict_next_tool(
    history: List[Mapping[str, Any]],
    tools: Iterable[str | Mapping[str, Any]],
    draft_provider: Any,
    draft_model: str = "llama3.1",
) -> Optional[Dict[str, Any]]:
    """Return a validated next-tool guess, or None when confidence is low."""
    tool_names = sorted(_tool_name(tool) for tool in tools if _tool_name(tool))
    prompt = _prediction_prompt(history, tool_names, draft_model)
    raw = await _call_draft_provider(draft_provider, prompt, draft_model)
    parsed = _parse_prediction(raw)
    if parsed is None:
        return None
    if parsed.tool not in READ_ONLY_TOOL_WHITELIST:
        return None
    if parsed.confidence < MIN_CONFIDENCE:
        return None
    return parsed.to_dict()


async def warm_for_prediction(
    prediction: Mapping[str, Any] | None,
    tool_dispatcher: ToolDispatcher,
    *,
    cache: Any = None,
) -> WarmResult:
    """Pre-execute a predicted read-only tool call and mark cached output.

    The dispatcher is deliberately narrow: it receives only ``(tool, args)``.
    Tests and callers can wrap richer dispatchers such as ``dispatch_one``.
    """
    parsed = _coerce_prediction(prediction)
    if parsed is None:
        return WarmResult(False, reason="invalid_prediction")
    if parsed.confidence < MIN_CONFIDENCE:
        return WarmResult(False, parsed.tool, "low_confidence")
    if parsed.tool not in READ_ONLY_TOOL_WHITELIST:
        return WarmResult(False, parsed.tool, "not_whitelisted")
    value = await _maybe_await(tool_dispatcher(parsed.tool, parsed.args))
    result = _result_from_dispatch(value)
    result.metadata = {**(result.metadata or {}), "from_speculation": True}
    if cache is not None:
        put = getattr(cache, "put", None)
        if callable(put):
            put(parsed.tool, parsed.args, result, from_speculation=True)
    return WarmResult(True, parsed.tool, "warmed")


async def run_shadow_prediction(
    history: List[Mapping[str, Any]],
    tools: Iterable[str | Mapping[str, Any]],
    draft_provider: Any,
    draft_model: str,
    tool_dispatcher: ToolDispatcher,
    *,
    cache: Any = None,
) -> WarmResult:
    prediction = await predict_next_tool(history, tools, draft_provider, draft_model)
    return await warm_for_prediction(prediction, tool_dispatcher, cache=cache)


def speculation_enabled(config: Any = None, preferences: Any = None) -> bool:
    cfg = getattr(config, "speculative", None)
    if cfg is not None:
        return bool(getattr(cfg, "enabled", False))
    raw = getattr(preferences, "speculative", None)
    return isinstance(raw, dict) and bool(raw.get("enabled", False))


def _prediction_prompt(history: List[Mapping[str, Any]], tools: List[str], draft_model: str) -> str:
    recent = history[-6:]
    return json.dumps(
        {
            "task": "predict_next_read_only_tool",
            "draft_model": draft_model,
            "tools": tools,
            "history": list(recent),
            "schema": {"tool": "str", "args": "object", "confidence": "0..1"},
        },
        ensure_ascii=False,
        sort_keys=True,
    )


async def _call_draft_provider(draft_provider: Any, prompt: str, draft_model: str) -> Any:
    if callable(draft_provider) and not hasattr(draft_provider, "send_message"):
        return await _maybe_await(draft_provider(prompt, model=draft_model))
    predictor = getattr(draft_provider, "predict_next_tool", None)
    if callable(predictor):
        return await _maybe_await(predictor(prompt=prompt, model=draft_model))
    sender = getattr(draft_provider, "send_message", None)
    if callable(sender):
        try:
            return await _maybe_await(sender(prompt, model=draft_model))
        except TypeError:
            return await _maybe_await(sender(prompt))
    raise ValueError("draft_provider must be callable or expose send_message/predict_next_tool")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _parse_prediction(raw: Any) -> Optional[SpeculativePrediction]:
    if isinstance(raw, SpeculativePrediction):
        return raw
    if isinstance(raw, dict):
        payload = raw
    else:
        content = getattr(raw, "content", raw)
        if not isinstance(content, str):
            return None
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
    return _coerce_prediction(payload)


def _coerce_prediction(raw: Mapping[str, Any] | None) -> Optional[SpeculativePrediction]:
    if not isinstance(raw, Mapping):
        return None
    tool = str(raw.get("tool") or raw.get("name") or "").strip()
    args = raw.get("args") or raw.get("arguments") or {}
    if not tool or not isinstance(args, dict):
        return None
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return SpeculativePrediction(tool=tool, args=dict(args), confidence=confidence)


def _result_from_dispatch(value: Any) -> ToolResult:
    if isinstance(value, tuple) and value:
        value = value[0]
    return wrap_legacy_result(value)


def _tool_name(tool: str | Mapping[str, Any]) -> str:
    if isinstance(tool, str):
        return tool
    return str(tool.get("name") or "")
