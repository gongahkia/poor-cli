from __future__ import annotations

from datetime import datetime, timedelta, timezone

from poor_cli.economy import SavingsHistoryStore, build_savings_summary


def test_savings_breakdown_by_source() -> None:
    economy = {
        "tokens_saved_by_distillation": 100,
        "tokens_saved_by_dedup": 50,
        "tokens_saved_by_truncation": 25,
        "tokens_saved_by_failure_amnesia": 25,
        "tokens_saved_by_shell_filter": 300,
        "tokens_saved_by_downshift": 40,
        "estimated_money_saved_usd": 0.02,
        "tokens_saved_by_safe_pretokenization": 80,
    }
    session = {
        "cache_read_input_tokens": 500,
        "estimated_cache_savings_usd": 0.01,
        "total_tokens": 2000,
        "block_cache": {"by_block": [{"path": "a.py", "hits": 2, "tokens": 200}]},
    }
    semantic = {"estimated_tokens_saved": 120, "estimated_cost_saved_usd": 0.003}

    summary = build_savings_summary(
        economy,
        session,
        semantic_cache_stats=semantic,
        token_usd_estimator=lambda tokens: tokens / 1000 * 0.002,
    )

    by_source = {item["source"]: item for item in summary["by_source"]}
    assert [item["source"] for item in summary["by_source"]] == [
        "prompt_caching",
        "semantic_cache",
        "compaction",
        "rtk",
        "model_downshift",
        "safe_pretokenization",
    ]
    assert by_source["prompt_caching"]["tokens_saved"] == 500
    assert by_source["compaction"]["tokens_saved"] == 200
    assert by_source["rtk"]["tokens_saved"] == 300
    assert by_source["model_downshift"]["usd_saved"] == 0.02
    assert summary["session_delta"]["tokens_before"] == 3240
    assert "methodology" in by_source["safe_pretokenization"]


def test_savings_history_rollup_correctness(tmp_path) -> None:
    store = SavingsHistoryStore(tmp_path / "savings.db")
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=40)
    store.record_snapshot(
        {"all_sources": [{"source": "rtk", "tokens_saved": 100, "usd_saved": 0.1}]},
        timestamp=old.isoformat(),
    )
    store.record_snapshot(
        {"all_sources": [
            {"source": "rtk", "tokens_saved": 100, "usd_saved": 0.2},
            {"source": "semantic_cache", "tokens_saved": 50, "usd_saved": 0.4},
        ]},
        timestamp=(now - timedelta(days=1)).isoformat(),
    )
    store.record_snapshot(
        {"all_sources": [{"source": "prompt_caching", "tokens_saved": 70, "usd_saved": 0.3}]},
        timestamp=now.isoformat(),
    )

    history = store.history(days=30)

    assert len(history["daily"]) == 2
    assert round(sum(history["daily"].values()), 6) == 0.9
    assert all(day >= (now - timedelta(days=29)).date().isoformat() for day in history["daily"])
    assert history["top_contributors_by_week"]
    top_sources = {
        item["source"]
        for week in history["top_contributors_by_week"]
        for item in week["top"]
    }
    assert "semantic_cache" in top_sources
