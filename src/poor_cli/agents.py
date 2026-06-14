from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import AgentInfo, TaskSpec
from .offline import require_online


@dataclass(frozen=True)
class AgentResult:
    agent_id: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def detect_agents() -> list[AgentInfo]:
    agents = [_generic_shell()]
    for name, adapter, provider, capabilities in (
        ("claude", "claude", "anthropic", ["noninteractive", "file_edits", "planning", "review", "tests"]),
        ("codex", "codex", "openai", ["noninteractive", "file_edits", "implementation", "tests", "review"]),
    ):
        command = shutil.which(name)
        if not command:
            continue
        agents.append(
            AgentInfo(
                agent_id=f"agent_{name}",
                name=name,
                command=command,
                version=_version([command, "--version"]),
                provider=provider,
                capabilities=capabilities,
                default_model="auto",
                invocation_adapter=adapter,
            )
        )
    return agents


class AgentRunner:
    def __init__(self, agents: list[AgentInfo], timeout_seconds: int = 1800):
        self.agents = {agent.name: agent for agent in agents}
        self.agents_by_id = {agent.agent_id: agent for agent in agents}
        self.timeout_seconds = timeout_seconds

    def choose(self, suggested: str | None) -> AgentInfo:
        if suggested and suggested in self.agents:
            return self.agents[suggested]
        for name in ("codex", "claude", "generic"):
            if name in self.agents:
                return self.agents[name]
        return next(iter(self.agents_by_id.values()))

    def run(
        self,
        agent: AgentInfo,
        *,
        goal: str,
        task: TaskSpec,
        context: str,
        workdir: Path,
        budget_usd: float | None = None,
    ) -> AgentResult:
        prompt = build_agent_prompt(goal, task, context)
        if agent.provider != "local":
            require_online(f"agent {agent.name}")
        if agent.invocation_adapter == "claude":
            command = [agent.command, "-p", "--permission-mode", "acceptEdits", "--output-format", "text"]
            if budget_usd is not None:
                command.extend(["--max-budget-usd", str(budget_usd)])
            command.append(prompt)
            return _run(agent.agent_id, command, workdir, self.timeout_seconds)
        if agent.invocation_adapter == "codex":
            command = [
                agent.command,
                "exec",
                "--cd",
                str(workdir),
                "--sandbox",
                "workspace-write",
                "--ask-for-approval",
                "never",
                prompt,
            ]
            return _run(agent.agent_id, command, workdir, self.timeout_seconds)
        command_text = task.metadata.get("command") if isinstance(task.metadata, dict) else None
        if command_text:
            command = [agent.command, "-lc", str(command_text)]
            return _run(agent.agent_id, command, workdir, self.timeout_seconds)
        stdout = f"generic shell adapter recorded task without executing commands: {task.title}\n"
        return AgentResult(agent.agent_id, [agent.command, "-lc", "<no command>"], 0, stdout, "")


def _generic_shell() -> AgentInfo:
    shell = os.environ.get("SHELL") or shutil.which("sh") or "/bin/sh"
    return AgentInfo(
        agent_id="agent_generic",
        name="generic",
        command=shell,
        version=_version([shell, "--version"]),
        provider="local",
        capabilities=["noninteractive", "command_execution"],
        default_model=None,
        invocation_adapter="generic",
    )


def _version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=3, check=False)
    except Exception:
        return "unknown"
    text = (result.stdout or result.stderr).strip().splitlines()
    return text[0][:160] if text else "unknown"


def build_agent_prompt(goal: str, task: TaskSpec, context: str) -> str:
    return "\n".join(
        [
            "You are running as a delegated coding agent under poor-cli.",
            f"Parent goal: {goal}",
            f"Task: {task.title}",
            f"Objective: {task.objective}",
            f"Type: {task.task_type}; complexity: {task.complexity}; risk: {task.risk}",
            "Use the provided context, make the smallest correct change, and report validation.",
            "",
            context,
        ]
    )


def _run(agent_id: str, command: list[str], workdir: Path, timeout_seconds: int) -> AgentResult:
    result = subprocess.run(command, cwd=workdir, text=True, capture_output=True, timeout=timeout_seconds, check=False)
    return AgentResult(agent_id, [shlex.quote(part) for part in command], result.returncode, result.stdout, result.stderr)
