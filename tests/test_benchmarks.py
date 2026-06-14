from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from bench.local_fixture_bugs import compact_payload, run_fixture_suite
from bench.phase1_readiness import readiness_payload
from bench.swe_bench_lite import run as swe_run


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


def test_bench_extra_matches_swe_lite_requirements() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"
    requirements = root / "bench" / "swe_bench_lite" / "requirements.txt"
    payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    bench_extra = payload["project"]["optional-dependencies"]["bench"]
    requirement_lines = [line.strip() for line in requirements.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert sorted(bench_extra) == sorted(requirement_lines)


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


def test_local_fixture_bug_compact_result_schema(tmp_path: Path) -> None:
    payload = run_fixture_suite(agent="generic", fixtures=["bug-1"], work_root=tmp_path)
    compact = compact_payload(payload)

    assert compact["schema_version"] == "poor-cli-local-fixture-bugs-result-v1"
    assert compact["fixture_count"] == 1
    assert compact["completed_count"] == 1
    assert compact["tests_passed_count"] == 1
    assert compact["replay_verified_count"] == 1
    assert compact["results"][0]["fixture"] == "bug-1"
    assert compact["results"][0]["run_id"]
    assert len(compact["results"][0]["trace_sha256"]) == 64


def test_checked_in_local_fixture_bug_result_row() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "local-fixture-bugs-generic.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-local-fixture-bugs-result-v1"
    assert payload["mode"] == "poor-cli"
    assert payload["agent"] == "generic"
    assert payload["fixture_count"] == 3
    assert payload["completed_count"] == 3
    assert payload["tests_passed_count"] == 3
    assert payload["replay_verified_count"] == 3
    assert {result["fixture"] for result in payload["results"]} == {"bug-1", "bug-2", "bug-3"}
    assert all(result["run_id"].startswith("run_") for result in payload["results"])
    assert all(len(result["trace_sha256"]) == 64 for result in payload["results"])


def test_phase1_readiness_payload_schema() -> None:
    payload = readiness_payload()

    assert payload["schema_version"] == "poor-cli-phase1-readiness-v1"
    assert isinstance(payload["ready"], bool)
    assert set(payload["checks"]) == {
        "local_fixture_generic_result",
        "live_anthropic_fixture_prereqs",
        "live_codex_fixture_prereqs",
        "swe_lite_manifest",
        "swe_lite_python_deps",
        "docker",
    }
    assert payload["checks"]["local_fixture_generic_result"]["ready"] is True
    assert payload["checks"]["swe_lite_manifest"]["instance_count"] == 10
    assert payload["checks"]["swe_lite_python_deps"]["install"] == "python -m pip install -e '.[bench]'"
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["ready"]}


def test_checked_in_phase1_readiness_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase1-readiness.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-phase1-readiness-v1"
    assert isinstance(payload["ready"], bool)
    assert set(payload["checks"]) == {
        "local_fixture_generic_result",
        "live_anthropic_fixture_prereqs",
        "live_codex_fixture_prereqs",
        "swe_lite_manifest",
        "swe_lite_python_deps",
        "docker",
    }
    assert payload["checks"]["local_fixture_generic_result"]["ready"] is True
    assert payload["checks"]["swe_lite_manifest"]["ready"] is True
    assert payload["checks"]["swe_lite_python_deps"]["install"] == "python -m pip install -e '.[bench]'"
    assert payload["checks"]["swe_lite_python_deps"]["ready"] is True
    assert payload["checks"]["swe_lite_python_deps"]["modules"] == {"datasets": True, "swebench": True}
    assert payload["checks"]["docker"]["ready"] is True
    assert payload["checks"]["docker"]["daemon"] is True
    assert payload["checks"]["docker"]["version"]
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["ready"]}


def test_swe_lite_runner_applies_manifest_order_and_validates_pin() -> None:
    manifest = {
        "instances": [
            {"instance_id": "repo__proj-2", "repo": "repo/proj", "base_commit": "b" * 40},
            {"instance_id": "repo__proj-1", "repo": "repo/proj", "base_commit": "a" * 40},
        ]
    }
    tasks = [
        {"instance_id": "repo__proj-1", "repo": "repo/proj", "base_commit": "a" * 40},
        {"instance_id": "repo__proj-2", "repo": "repo/proj", "base_commit": "b" * 40},
        {"instance_id": "repo__proj-extra", "repo": "repo/proj", "base_commit": "c" * 40},
    ]

    selected = swe_run.apply_manifest(tasks, manifest)

    assert [task["instance_id"] for task in selected] == ["repo__proj-2", "repo__proj-1"]
    with pytest.raises(SystemExit):
        swe_run.apply_manifest(tasks, {"instances": [{"instance_id": "repo__proj-1", "repo": "repo/proj", "base_commit": "d" * 40}]})


def test_swe_lite_runner_uses_v6_run_and_planner_payload(tmp_path: Path) -> None:
    args = swe_run.parse_args(["--confirm-cost", "--no-evaluate", "--limit", "1", "--agent", "claude"])
    task = {"instance_id": "repo__proj-1", "problem_statement": "Fix the bug", "repo": "repo/proj"}

    command = swe_run.poor_cli_run_command(args, tmp_path / "store", "Fix the bug")
    payload = swe_run.planner_payload(task, "claude")

    assert "exec" not in command
    assert command[-3:] == ["run", "Fix the bug", "--yes"]
    assert payload["tasks"][0]["suggested_agent"] == "claude"
    assert payload["tasks"][0]["objective"] == "Fix the bug"
    assert swe_run.extract_run_id("run_id: run_123\n1. task -> claude\n") == "run_123"
