from __future__ import annotations

from types import SimpleNamespace

import pytest

from poor_cli.adaptive_budget import AdaptiveBudgetController
from poor_cli.server.handlers.budget_hud import BudgetHudHandlersMixin
from poor_cli.token_budget_controller import TokenBudgetAction, TokenBudgetState, TurnOutcome


class _Ctx(BudgetHudHandlersMixin):
    def __init__(self, core=None):
        self._core = core

    def _maybe_core(self):
        return self._core


@pytest.mark.asyncio
async def test_budget_hud_snapshot_returns_budget_state() -> None:
    adapt = AdaptiveBudgetController()
    adapt.observe(TokenBudgetState(), TokenBudgetAction(), TurnOutcome(task_succeeded=True))
    core = SimpleNamespace(
        _adaptive_budget=adapt,
        _last_budget_action=TokenBudgetAction(
            max_thinking_tokens=2048,
            max_output_tokens=1024,
            compression_ratio=0.25,
            model_tier="frugal",
        ),
        _last_turn_outcome=TurnOutcome(
            total_tokens_used=333,
            input_tokens=111,
            output_tokens=222,
            response_time_seconds=1.5,
        ),
        _task_cost_usd=0.00123,
    )

    payload = await _Ctx(core).handle_budget_hud_snapshot({})

    assert payload["lastAction"]["max_thinking_tokens"] == 2048
    assert payload["lastOutcome"]["input_tokens"] == 111
    assert payload["adaptation"]["windowSize"] == 1
    assert payload["projectedCostUsd"] == 0.00123
    assert payload["ts"]


@pytest.mark.asyncio
async def test_budget_hud_snapshot_missing_state_is_graceful() -> None:
    payload = await _Ctx().handle_budget_hud_snapshot({})

    assert payload["lastAction"] == {}
    assert payload["lastOutcome"] == {}
    assert payload["adaptation"] == {}
    assert payload["projectedCostUsd"] == 0.0
    assert payload["ts"]
