from __future__ import annotations

from poor_cli.agents import detect_agents


def test_detect_agents_always_has_generic() -> None:
    agents = detect_agents()
    assert any(agent.name == "generic" for agent in agents)
