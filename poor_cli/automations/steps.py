"""Unified automation steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Literal, Optional, Union


@dataclass(frozen=True)
class PromptStep:
    prompt: str
    type: Literal["prompt"] = "prompt"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "prompt": self.prompt}


@dataclass(frozen=True)
class ToolCallStep:
    tool: str
    params: Dict[str, Any]
    type: Literal["tool_call"] = "tool_call"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "tool": self.tool, "params": dict(self.params)}


@dataclass(frozen=True)
class ShellStep:
    command: str
    cwd: Optional[str] = None
    type: Literal["shell"] = "shell"

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"type": self.type, "command": self.command}
        if self.cwd:
            payload["cwd"] = self.cwd
        return payload


Step = Union[PromptStep, ToolCallStep, ShellStep]


def step_from_dict(raw: Dict[str, Any]) -> Step:
    kind = str(raw.get("type") or raw.get("kind") or "").strip().lower()
    if kind == "prompt":
        return PromptStep(prompt=str(raw.get("prompt") or raw.get("template") or "").strip())
    if kind == "tool_call":
        params = raw.get("params")
        return ToolCallStep(
            tool=str(raw.get("tool") or "").strip(),
            params=dict(params) if isinstance(params, dict) else {},
        )
    if kind == "shell":
        cwd = raw.get("cwd")
        return ShellStep(
            command=str(raw.get("command") or "").strip(),
            cwd=str(cwd).strip() if cwd else None,
        )
    raise ValueError(f"Unknown step type: {kind}")


def execute_step(
    step: Step,
    *,
    prompt_runner: Callable[[str], Any],
    tool_runner: Callable[[str, Dict[str, Any]], Any],
    shell_runner: Callable[[str, Optional[str]], Any],
) -> Any:
    if isinstance(step, PromptStep):
        return prompt_runner(step.prompt)
    if isinstance(step, ToolCallStep):
        return tool_runner(step.tool, dict(step.params))
    if isinstance(step, ShellStep):
        return shell_runner(step.command, step.cwd)
    raise TypeError(f"Unknown step: {step!r}")
