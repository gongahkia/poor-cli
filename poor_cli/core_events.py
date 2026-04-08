"""Structured events emitted by the PoorCLICore agentic loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from .repo_config import RepoConfig


@dataclass
class CoreEvent:
    """Structured event emitted by the agentic loop."""
    type: str # text_chunk | thinking_chunk | tool_call_start | tool_result | permission_request | cost_update | progress | done
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def text_chunk(chunk: str, request_id: str = "") -> "CoreEvent":
        return CoreEvent(type="text_chunk", data={"chunk": chunk, "requestId": request_id})

    @staticmethod
    def thinking_chunk(chunk: str, request_id: str = "") -> "CoreEvent":
        return CoreEvent(type="thinking_chunk", data={"chunk": chunk, "requestId": request_id})

    @staticmethod
    def tool_call_start(
        tool_name: str,
        tool_args: Dict[str, Any],
        call_id: str = "",
        iteration: int = 0,
        cap: int = 25,
        paths: Optional[List[str]] = None,
    ) -> "CoreEvent":
        return CoreEvent(type="tool_call_start", data={
            "toolName": tool_name, "toolArgs": tool_args, "callId": call_id,
            "iterationIndex": iteration, "iterationCap": cap,
            "paths": paths or [],
        })

    @staticmethod
    def tool_result(
        tool_name: str,
        result: str,
        call_id: str = "",
        iteration: int = 0,
        cap: int = 25,
        diff: str = "",
        paths: Optional[List[str]] = None,
        checkpoint_id: Optional[str] = None,
        changed: Optional[bool] = None,
        message: str = "",
    ) -> "CoreEvent":
        return CoreEvent(type="tool_result", data={
            "toolName": tool_name, "toolResult": result, "callId": call_id,
            "iterationIndex": iteration, "iterationCap": cap,
            "diff": diff,
            "paths": paths or [],
            "checkpointId": checkpoint_id,
            "changed": changed,
            "message": message,
        })

    @staticmethod
    def permission_request(
        tool_name: str,
        tool_args: Dict[str, Any],
        prompt_id: str = "",
        preview: Optional[Dict[str, Any]] = None,
    ) -> "CoreEvent":
        return CoreEvent(type="permission_request", data={
            "toolName": tool_name, "toolArgs": tool_args, "promptId": prompt_id,
            "preview": preview or {},
        })

    @staticmethod
    def plan_request(
        summary: str,
        steps: List[str],
        original_request: str,
        prompt_id: str = "",
        request_id: str = "",
    ) -> "CoreEvent":
        return CoreEvent(
            type="plan_request",
            data={
                "summary": summary,
                "steps": steps,
                "originalRequest": original_request,
                "promptId": prompt_id,
                "requestId": request_id,
            },
        )

    @staticmethod
    def cost_update(input_tokens: int = 0, output_tokens: int = 0, estimated_cost: float = 0.0,
                    cache_creation_input_tokens: int = 0, cache_read_input_tokens: int = 0,
                    is_estimate: bool = False,
                    cumulative_input_tokens: int = 0, cumulative_output_tokens: int = 0,
                    system_tokens: int = 0, history_tokens: int = 0,
                    tool_result_tokens: int = 0) -> "CoreEvent":
        data = {"inputTokens": input_tokens, "outputTokens": output_tokens, "estimatedCost": estimated_cost}
        if cache_creation_input_tokens:
            data["cacheCreationInputTokens"] = cache_creation_input_tokens
        if cache_read_input_tokens:
            data["cacheReadInputTokens"] = cache_read_input_tokens
        if is_estimate:
            data["isEstimate"] = True
        if cumulative_input_tokens or cumulative_output_tokens:
            data["cumulativeInputTokens"] = cumulative_input_tokens
            data["cumulativeOutputTokens"] = cumulative_output_tokens
        if system_tokens:
            data["systemTokens"] = system_tokens
        if history_tokens:
            data["historyTokens"] = history_tokens
        if tool_result_tokens:
            data["toolResultTokens"] = tool_result_tokens
        return CoreEvent(type="cost_update", data=data)

    @staticmethod
    def context_pressure(used_tokens: int, max_tokens: int, pressure_pct: float) -> "CoreEvent":
        return CoreEvent(type="context_pressure", data={
            "usedTokens": used_tokens, "maxTokens": max_tokens, "pressurePct": pressure_pct,
        })

    @staticmethod
    def economy_turn_report(report: Dict[str, Any]) -> "CoreEvent":
        return CoreEvent(type="economy_turn_report", data=report)

    @staticmethod
    def progress(phase: str, message: str, iteration: int = 0, cap: int = 25) -> "CoreEvent":
        return CoreEvent(type="progress", data={
            "phase": phase, "message": message, "iterationIndex": iteration, "iterationCap": cap,
        })

    @staticmethod
    def todo_update(todos: list, completed: int = 0, total: int = 0) -> "CoreEvent":
        return CoreEvent(type="todo_update", data={"todos": todos, "completed": completed, "total": total})

    @staticmethod
    def economy_savings(savings: Dict[str, Any]) -> "CoreEvent":
        return CoreEvent(type="economy_savings", data=savings)

    @staticmethod
    def done(reason: str = "complete") -> "CoreEvent":
        return CoreEvent(type="done", data={"reason": reason})


class HistoryAdapter(Protocol):
    """History backend contract used by PoorCLICore."""

    def start_session(self, model: str) -> None: ...

    def add_message(self, role: str, content: str) -> None: ...

    def clear_history(self) -> None: ...


class RepoHistoryAdapter:
    """Repository-scoped history adapter backed by RepoConfig."""

    def __init__(self, repo_config: RepoConfig):
        self._repo_config = repo_config

    def start_session(self, model: str) -> None:
        self._repo_config.start_session(model=model)

    def add_message(self, role: str, content: str) -> None:
        self._repo_config.add_message(role=role, content=content)

    def clear_history(self) -> None:
        self._repo_config.clear_history()
