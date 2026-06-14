from __future__ import annotations

import json
from pathlib import Path


def test_v6_baseline_task_fixture_schema() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "fixtures" / "v6_baseline_tasks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload["tasks"]

    assert payload["schema_version"] == "v6-bench-task-1"
    assert payload["modes"] == ["claude-only", "codex-only", "poor-cli"]
    assert {"completed", "tests_passed", "interventions", "cost_usd", "duration_seconds", "replay_useful", "run_id"} <= set(
        payload["metrics"]
    )
    assert len(tasks) >= 10
    assert len({task["id"] for task in tasks}) == len(tasks)
    assert len({task["issue"] for task in tasks}) == len(tasks)
    for task in tasks:
        assert task["source"] == "github-issue"
        assert task["phase"].startswith("phase-")
        assert task["prompt"].strip()
        assert task["success_criteria"]
