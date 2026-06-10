from __future__ import annotations

from poor_cli.tui.textual_app import (
    summarize_budget_activity,
    summarize_compaction_activity,
    summarize_context_pressure,
    summarize_cost_update,
)


def test_budget_activity_includes_controller_and_retuning_state():
    detail = summarize_budget_activity(
        {
            "lastAction": {
                "max_thinking_tokens": 2048,
                "max_output_tokens": 1024,
                "compression_ratio": 0.25,
                "model_tier": "frugal",
            },
            "lastOutcome": {"input_tokens": 111, "output_tokens": 222},
            "adaptation": {"trend": -0.2},
            "retuning": {
                "available": True,
                "generatedAt": "2026-05-04T00:00:00+00:00",
                "estimatedSavingsPct": 18.5,
            },
            "projectedCostUsd": 0.00123,
        }
    )

    assert "in/out 111/222" in detail
    assert "caps think/out 2048/1024" in detail
    assert "comp 25%" in detail
    assert "retune 2026-05-04 18.5%" in detail


def test_compaction_activity_summarizes_done_and_queued_states():
    done = summarize_compaction_activity(
        {
            "state": "done",
            "strategy": "compact",
            "trigger": "auto",
            "tokens_before": 9000,
            "tokens_after": 4200,
            "removed_tokens": 4800,
            "pruned_turns": 3,
        }
    )
    queued = summarize_compaction_activity(
        {
            "state": "queued",
            "strategy": "compact",
            "trigger": "auto",
            "utilization_before_pct": 88.0,
            "target_utilization_pct": 40.0,
        }
    )

    assert done == "done compact (auto) 9000->4200 tok, removed 4800, pruned 3"
    assert queued == "queued compact (auto) 88.0% -> 40.0%"


def test_cost_and_context_notification_summaries_are_compact():
    cost = summarize_cost_update({"inputTokens": 10, "outputTokens": 20, "estimatedCostUsd": 0.0004})
    pressure = summarize_context_pressure({"totalTokens": 900, "maxTokens": 1000, "pressurePct": 90.0})

    assert cost == "in/out 10/20 cost $0.000400"
    assert pressure == "900/1000 tokens (90.0%)"
