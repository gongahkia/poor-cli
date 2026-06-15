from __future__ import annotations

import pytest

from poor_cli.agents import AgentResult, AgentRunner, detect_agents
from poor_cli.models import AgentInfo, TaskSpec
from poor_cli.offline import OfflineModeError
from poor_cli.providers import ProviderResponse


def test_detect_agents_always_has_generic() -> None:
    agents = detect_agents()
    assert any(agent.name == "generic" for agent in agents)


def test_detect_agents_adds_local_provider_agent(monkeypatch) -> None:
    monkeypatch.setenv("POOR_CLI_PROVIDER", "vllm")
    monkeypatch.setenv("POOR_CLI_MODEL", "qwen")
    monkeypatch.setenv("POOR_CLI_LOCAL_BASE_URL", "http://vllm.test")

    local = next(agent for agent in detect_agents() if agent.name == "local")

    assert local.provider == "vllm"
    assert local.command == "http://vllm.test"
    assert local.default_model == "qwen"
    assert local.invocation_adapter == "local_provider"


def test_offline_mode_blocks_network_backed_agents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("POOR_CLI_OFFLINE", "1")
    agent = AgentInfo(agent_id="agent_remote", name="remote", command="remote", provider="anthropic", invocation_adapter="claude")
    runner = AgentRunner([agent])

    with pytest.raises(OfflineModeError):
        runner.run(agent, goal="goal", task=TaskSpec(task_id="task_1", title="Task", objective="obj"), context="", workdir=tmp_path)


def test_local_provider_agent_calls_provider(tmp_path, monkeypatch) -> None:
    seen = {}

    class FakeProvider:
        def call(self, request):
            seen["request"] = request
            return ProviderResponse(provider=request.provider, model=request.model, content="patch guidance")

    agent = AgentInfo(
        agent_id="agent_local",
        name="local",
        command="http://vllm.test",
        provider="vllm",
        default_model="qwen",
        invocation_adapter="local_provider",
    )
    monkeypatch.setattr("poor_cli.agents._provider_for_agent", lambda received: FakeProvider())

    result = AgentRunner([agent]).run(
        agent,
        goal="goal",
        task=TaskSpec(task_id="task_1", title="Task", objective="fix bug"),
        context="ctx",
        workdir=tmp_path,
    )

    assert isinstance(result, AgentResult)
    assert result.returncode == 0
    assert result.stdout == "patch guidance"
    assert result.command == ["local-provider", "vllm", "qwen", "http://vllm.test"]
    assert seen["request"].provider == "vllm"
    assert seen["request"].model == "qwen"
    assert "fix bug" in seen["request"].prompt
