from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import AgentInfo, TaskSpec
from .offline import require_online
from .provider_adapters import OllamaProvider, SGLangProvider, VLLMProvider
from .providers import Provider, ProviderRequest

LOCAL_PROVIDERS = {"ollama", "sglang", "vllm"}


@dataclass(frozen=True)
class AgentResult:
    agent_id: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def detect_agents() -> list[AgentInfo]:
    agents = [_generic_shell()]
    local_agent = _local_provider_agent()
    if local_agent is not None:
        agents.append(local_agent)
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
        if agent.invocation_adapter == "local_provider":
            response = _provider_for_agent(agent).call(
                ProviderRequest(
                    provider=agent.provider,
                    model=agent.default_model or "",
                    prompt=prompt,
                    system_prompt="You are a local coding model delegated by poor-cli. Return concise implementation guidance.",
                )
            )
            return AgentResult(
                agent.agent_id,
                ["local-provider", agent.provider, agent.default_model or "", agent.command],
                0,
                response.content,
                "",
            )
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


def _local_provider_agent() -> AgentInfo | None:
    provider = os.environ.get("POOR_CLI_PROVIDER") or os.environ.get("POOR_CLI_LOCAL_ENGINE") or ""
    provider = provider.strip().lower()
    model = (os.environ.get("POOR_CLI_MODEL") or os.environ.get("POOR_CLI_LOCAL_MODEL") or "").strip()
    if provider not in LOCAL_PROVIDERS or not model:
        return None
    base_url = _local_base_url(provider)
    return AgentInfo(
        agent_id="agent_local",
        name="local",
        command=base_url,
        version=f"{provider}:{model}",
        provider=provider,
        capabilities=["noninteractive", "local_model", "implementation"],
        default_model=model,
        invocation_adapter="local_provider",
    )


def _local_base_url(provider: str) -> str:
    explicit = os.environ.get("POOR_CLI_LOCAL_BASE_URL")
    if explicit:
        return explicit
    if provider == "ollama":
        return "http://localhost:11434"
    if provider == "sglang":
        return "http://localhost:30000"
    return "http://localhost:8000"


def _provider_for_agent(agent: AgentInfo) -> Provider:
    if agent.provider == "ollama":
        return OllamaProvider(agent.command)
    if agent.provider == "sglang":
        return SGLangProvider(agent.command)
    if agent.provider == "vllm":
        return VLLMProvider(agent.command)
    raise RuntimeError(f"unsupported local provider: {agent.provider}")


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
