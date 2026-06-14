from __future__ import annotations

import pytest

from poor_cli.agents import AgentRunner, detect_agents
from poor_cli.models import AgentInfo, TaskSpec
from poor_cli.offline import OfflineModeError


def test_detect_agents_always_has_generic() -> None:
    agents = detect_agents()
    assert any(agent.name == "generic" for agent in agents)


def test_offline_mode_blocks_network_backed_agents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("POOR_CLI_OFFLINE", "1")
    agent = AgentInfo(agent_id="agent_remote", name="remote", command="remote", provider="anthropic", invocation_adapter="claude")
    runner = AgentRunner([agent])

    with pytest.raises(OfflineModeError):
        runner.run(agent, goal="goal", task=TaskSpec(task_id="task_1", title="Task", objective="obj"), context="", workdir=tmp_path)
