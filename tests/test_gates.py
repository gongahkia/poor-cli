from __future__ import annotations

from poor_cli.planner import SYSTEM_PROMPT


def test_system_prompt_under_1000_token_ceiling() -> None:
    assert len(SYSTEM_PROMPT.encode("utf-8")) <= 1000
