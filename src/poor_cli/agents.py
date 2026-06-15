from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ConfigError, load_config
from .models import AgentInfo, TaskSpec
from .offline import require_online
from .provider_adapters import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAICompatibleChatProvider,
    OpenAIProvider,
    SGLangProvider,
    VLLMProvider,
)
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
    agents.extend(_configured_provider_agents())
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
        for name in ("codex", "claude", "local"):
            if name in self.agents:
                return self.agents[name]
        for agent in self.agents_by_id.values():
            if agent.invocation_adapter == "provider":
                return agent
        if "generic" in self.agents:
            return self.agents["generic"]
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
        store: Any | None = None,
        run_id: str | None = None,
        hooks: Any | None = None,
        replay_only: bool = False,
        cancel: Any | None = None,
    ) -> AgentResult:
        prompt = build_agent_prompt(goal, task, context)
        if agent.provider != "local":
            require_online(f"agent {agent.name}")
        if agent.invocation_adapter == "claude":
            command = [agent.command, "-p", "--permission-mode", "acceptEdits", "--output-format", "text"]
            if budget_usd is not None:
                command.extend(["--max-budget-usd", str(budget_usd)])
            command.append(prompt)
            return _run(agent.agent_id, command, workdir, self.timeout_seconds, cancel)
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
            return _run(agent.agent_id, command, workdir, self.timeout_seconds, cancel)
        if agent.invocation_adapter in {"local_provider", "provider"}:
            route = task.metadata.get("route_config") if isinstance(task.metadata.get("route_config"), dict) else {}
            if store is not None and run_id is not None and "tools" in agent.capabilities:
                from .native_runner import ProviderBackedAgentRunner, native_params

                system = "You are a poor-cli native coding agent. Use tools for repo I/O and return concise final validation."
                native = ProviderBackedAgentRunner(_provider_for_agent(agent), store, run_id, workdir, hooks=hooks, replay_only=replay_only)
                try:
                    result = native.run(
                        provider_name=agent.provider,
                        model=agent.default_model or "",
                        prompt=prompt,
                        system_prompt=system,
                        task_id=task.task_id,
                        params=native_params(agent.provider, system, prompt, route),
                    )
                except Exception as exc:
                    fallback = self._kimi_fallback(agent, route, store, run_id, task.task_id, exc)
                    if fallback is None:
                        raise
                    return self.run(
                        fallback,
                        goal=goal,
                        task=task,
                        context=context,
                        workdir=workdir,
                        budget_usd=budget_usd,
                        store=store,
                        run_id=run_id,
                        hooks=hooks,
                        replay_only=replay_only,
                        cancel=cancel,
                    )
                label = "local-provider" if agent.invocation_adapter == "local_provider" else "provider-native"
                return AgentResult(
                    agent.agent_id,
                    [label, agent.provider, agent.default_model or "", agent.command],
                    result.returncode,
                    result.stdout,
                    result.stderr,
                )
            try:
                response = _provider_for_agent(agent).call(
                    ProviderRequest(
                        provider=agent.provider,
                        model=agent.default_model or "",
                        prompt=prompt,
                        system_prompt="You are a local coding model delegated by poor-cli. Return concise implementation guidance.",
                    )
                )
            except Exception as exc:
                fallback = self._kimi_fallback(agent, route, store, run_id, task.task_id, exc)
                if fallback is None:
                    raise
                return self.run(
                    fallback,
                    goal=goal,
                    task=task,
                    context=context,
                    workdir=workdir,
                    budget_usd=budget_usd,
                    store=store,
                    run_id=run_id,
                    hooks=hooks,
                    replay_only=replay_only,
                    cancel=cancel,
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
            return _run(agent.agent_id, command, workdir, self.timeout_seconds, cancel)
        stdout = f"generic shell adapter recorded task without executing commands: {task.title}\n"
        return AgentResult(agent.agent_id, [agent.command, "-lc", "<no command>"], 0, stdout, "")

    def _kimi_fallback(
        self,
        agent: AgentInfo,
        route: dict[str, Any],
        store: Any | None,
        run_id: str | None,
        task_id: str,
        exc: Exception,
    ) -> AgentInfo | None:
        if agent.provider != "kimi":
            return None
        fallback_id = str(route.get("fallback_profile") or route.get("fallback_agent") or "")
        fallback = self.agents.get(fallback_id) or self.agents_by_id.get(fallback_id)
        if fallback is None or fallback.agent_id == agent.agent_id:
            return None
        if store is not None and run_id is not None:
            store.append_event(
                run_id,
                "kimi.fallback",
                {"from": agent.name, "to": fallback.name, "reason": f"{type(exc).__name__}: {exc}"},
                task_id,
            )
        return fallback


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
        capabilities=["noninteractive", "local_model", "implementation", "tools"],
        default_model=model,
        invocation_adapter="local_provider",
    )


def _configured_provider_agents() -> list[AgentInfo]:
    try:
        config = load_config(Path.cwd())
    except ConfigError:
        return []
    agents = []
    for profile_id, profile in sorted(config.get("providers", {}).items()):
        if not isinstance(profile, dict):
            continue
        models = profile.get("models")
        model = str(models[0]) if isinstance(models, list) and models else ""
        if not model:
            continue
        raw_caps = profile.get("capabilities")
        caps = raw_caps if isinstance(raw_caps, dict) else {}
        capabilities = ["noninteractive", "implementation", *(key for key, enabled in caps.items() if enabled)]
        raw_auth = profile.get("auth")
        auth = raw_auth if isinstance(raw_auth, dict) else {}
        agents.append(
            AgentInfo(
                agent_id=f"agent_provider_{profile_id}",
                name=profile_id,
                command=str(profile.get("base_url") or profile.get("kind") or ""),
                version=f"{profile.get('kind')}:{model}",
                provider=str(profile.get("kind") or ""),
                capabilities=capabilities,
                default_model=model,
                context_window_hint=_context_window(caps),
                cost_profile={"auth_env": str(auth.get("env") or "")},
                invocation_adapter="provider",
            )
        )
    return agents


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
    if agent.provider == "openai":
        return OpenAIProvider()
    if agent.provider == "anthropic":
        return AnthropicProvider()
    if agent.provider == "gemini":
        return GeminiProvider()
    if agent.provider in {"openai-compatible", "openrouter", "kimi"}:
        return OpenAICompatibleChatProvider(agent.command, headers=_auth_headers(agent))
    if agent.provider == "ollama":
        return OllamaProvider(agent.command)
    if agent.provider == "sglang":
        return SGLangProvider(agent.command)
    if agent.provider == "vllm":
        return VLLMProvider(agent.command)
    raise RuntimeError(f"unsupported local provider: {agent.provider}")


def _auth_headers(agent: AgentInfo) -> dict[str, str]:
    env_name = str(agent.cost_profile.get("auth_env") or "")
    token = os.environ.get(env_name) if env_name else ""
    return {"Authorization": f"Bearer {token}"} if token else {}


def _context_window(caps: dict[str, Any]) -> int | None:
    value = caps.get("max_context_tokens") or caps.get("max_context")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _run(agent_id: str, command: list[str], workdir: Path, timeout_seconds: int, cancel: Any | None = None) -> AgentResult:
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=workdir, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    while process.poll() is None:
        if cancel is not None and cancel.is_set():
            _stop(process)
            out, err = process.communicate()
            return AgentResult(agent_id, [shlex.quote(part) for part in command], 130, out, err + "\ncancelled\n")
        if time.monotonic() - started > timeout_seconds:
            _stop(process)
            out, err = process.communicate()
            return AgentResult(agent_id, [shlex.quote(part) for part in command], 124, out, err + "\ntimeout\n")
        time.sleep(0.05)
    out, err = process.communicate()
    return AgentResult(agent_id, [shlex.quote(part) for part in command], int(process.returncode or 0), out, err)


def _stop(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except Exception:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            process.kill()
