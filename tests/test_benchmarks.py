from __future__ import annotations

import json
from pathlib import Path

from bench.local_fixture_bugs import run_fixture_suite


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


def test_swe_lite_10_manifest_schema() -> None:
    path = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "swe-lite-10" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    instances = payload["instances"]

    assert payload["schema_version"] == "swe-lite-10-v1"
    assert payload["dataset"] == "SWE-bench/SWE-bench_Lite"
    assert payload["split"] == "test"
    assert payload["selection"] == {"offset": 0, "length": 10}
    assert len(instances) == 10
    assert len({item["instance_id"] for item in instances}) == 10
    for item in instances:
        assert "__" in item["instance_id"]
        assert "/" in item["repo"]
        assert len(item["base_commit"]) == 40
        assert item["fail_to_pass_count"] >= 1
        assert item["pass_to_pass_count"] >= 0


def test_local_fixture_bug_benchmark_runs_poor_cli_generic(tmp_path: Path) -> None:
    payload = run_fixture_suite(agent="generic", work_root=tmp_path)

    assert payload["schema_version"] == "poor-cli-local-fixture-bugs-v1"
    assert payload["mode"] == "poor-cli"
    assert payload["agent"] == "generic"
    assert payload["fixture_count"] == 3
    for result in payload["results"]:
        assert result["completed"] is True
        assert result["tests_passed"] is True
        assert result["replay_verified"] is True
        assert result["run_id"]
