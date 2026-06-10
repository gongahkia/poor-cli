from __future__ import annotations

from poor_cli.adaptive_budget import AdaptiveBudgetController
from poor_cli.prompt_optimizer import PromptOptimizer
from poor_cli.skill_surfacer import detect_relevant_skills
from poor_cli.token_budget_controller import TokenBudgetAction, TokenBudgetState, TurnOutcome


def _optimizer_with_rewards(rewards: list[float]) -> PromptOptimizer:
    ctl = AdaptiveBudgetController()
    ctl._rewards.extend(rewards)
    ctl.decide(TokenBudgetState(task_complexity=0.2))
    return PromptOptimizer(ctl)


def test_prompt_optimizer_minimal_branch() -> None:
    optimizer = _optimizer_with_rewards([0.9, 0.8, 0.9, 0.8])

    decision = optimizer.choose({"core", "economy", "readonly", "review"}, 0.2)

    assert decision.system_prompt_level == "minimal"
    assert decision.skill_whitelist == ["core", "economy", "readonly"]


def test_prompt_optimizer_trim_branch() -> None:
    optimizer = _optimizer_with_rewards([0.5, 0.6, 0.5, 0.6])

    decision = optimizer.choose({"core", "deployment", "review", "testing"}, 0.5)

    assert decision.system_prompt_level == "trim"
    assert decision.skill_whitelist == ["core", "testing"]


def test_prompt_optimizer_full_branch_for_complex_tasks() -> None:
    optimizer = _optimizer_with_rewards([0.9, 0.9, 0.9, 0.9])

    decision = optimizer.choose({"core", "review"}, 0.9)

    assert decision.system_prompt_level == "full"
    assert decision.skill_whitelist == ["core", "review"]


def test_prompt_optimizer_empty_skills() -> None:
    optimizer = _optimizer_with_rewards([1.0, 1.0, 1.0, 1.0])

    decision = optimizer.choose(set(), 0.1)

    assert decision.system_prompt_level == "minimal"
    assert decision.skill_whitelist == []


def test_skill_surfacer_respects_whitelist() -> None:
    matched = detect_relevant_skills(
        "review and test this change",
        ["review", "test"],
        whitelist=["test"],
    )

    assert matched == ["test"]


def test_adaptive_budget_public_recent_metrics() -> None:
    ctl = AdaptiveBudgetController()
    state = TokenBudgetState(task_complexity=0.25)
    action = TokenBudgetAction()
    ctl.observe(state, action, TurnOutcome(task_succeeded=True))
    ctl.observe(TokenBudgetState(task_complexity=0.75), action, TurnOutcome(task_succeeded=False))

    assert ctl.recent_complexity_estimate() == 0.5
    assert ctl.recent_success_rate(2) == 0.5
