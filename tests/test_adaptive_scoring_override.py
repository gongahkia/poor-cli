"""CB3: HistoryPruner.adaptive_tool_scoring_override tri-state (None/True/False)."""
from __future__ import annotations
import tempfile
from pathlib import Path

from poor_cli.history_pruning import HistoryPruner
from poor_cli.tool_success_tracker import ToolSuccessTracker


def test_auto_is_off_without_tracker() -> None:
    pruner = HistoryPruner()
    policy = pruner.policy_for(mode="balanced", economy_preset="balanced")
    assert policy.adaptive_tool_scoring is False


def test_auto_is_on_with_tracker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tracker = ToolSuccessTracker(Path(tmp))
        pruner = HistoryPruner(tool_success_tracker=tracker)
        policy = pruner.policy_for(mode="balanced", economy_preset="balanced")
        assert policy.adaptive_tool_scoring is True


def test_override_true_forces_on_even_without_tracker() -> None:
    pruner = HistoryPruner(adaptive_tool_scoring_override=True)
    policy = pruner.policy_for(mode="balanced", economy_preset="balanced")
    assert policy.adaptive_tool_scoring is True


def test_override_false_forces_off_with_tracker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tracker = ToolSuccessTracker(Path(tmp))
        pruner = HistoryPruner(
            tool_success_tracker=tracker,
            adaptive_tool_scoring_override=False,
        )
        policy = pruner.policy_for(mode="balanced", economy_preset="balanced")
        assert policy.adaptive_tool_scoring is False
