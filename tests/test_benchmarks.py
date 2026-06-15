from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from bench.graph_vs_grep import graph_vs_grep_payload
from bench.local_fixture_bugs import compact_payload, run_fixture_suite
from bench.phase1_acceptance import acceptance_payload
from bench.phase1_readiness import readiness_payload
from bench.phase3_acceptance import acceptance_payload as phase3_acceptance_payload
from bench.phase3_demo import demo_plan_payload, validate_demo_evidence
from bench.phase3_local_benchmark import benchmark_plan_payload, validate_local_summary
from bench.phase3_readiness import readiness_payload as phase3_readiness_payload
from bench.pivot_remaining import remaining_payload
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
    payload = run_fixture_suite(agent="generic", fixtures=["bug-1"], work_root=tmp_path, budget_usd=0.25)
    compact = compact_payload(payload)

    assert compact["schema_version"] == "poor-cli-local-fixture-bugs-result-v1"
    assert compact["budget_usd"] == 0.25
    assert compact["fixture_count"] == 1
    assert compact["completed_count"] == 1
    assert compact["tests_passed_count"] == 1
    assert compact["replay_verified_count"] == 1
    assert compact["results"][0]["fixture"] == "bug-1"
    assert compact["results"][0]["run_id"]
    assert len(compact["results"][0]["trace_sha256"]) == 64


def test_live_fixture_bug_benchmark_requires_cost_confirmation(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        run_fixture_suite(agent="claude", fixtures=["bug-1"], work_root=tmp_path, budget_usd=0.25)


def test_checked_in_local_fixture_bug_result_rows() -> None:
    root = Path(__file__).resolve().parents[1] / "bench" / "results"
    rows = {
        "generic": json.loads((root / "local-fixture-bugs-generic.json").read_text(encoding="utf-8")),
        "claude": json.loads((root / "local-fixture-bugs-claude.json").read_text(encoding="utf-8")),
    }

    assert rows["generic"]["budget_usd"] is None
    assert rows["claude"]["budget_usd"] == 1.0
    for agent, payload in rows.items():
        assert payload["schema_version"] == "poor-cli-local-fixture-bugs-result-v1"
        assert payload["mode"] == "poor-cli"
        assert payload["agent"] == agent
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
    assert payload["checks"]["live_anthropic_fixture_prereqs"]["ready"] is True
    assert payload["checks"]["live_anthropic_fixture_prereqs"]["cli_auth"]["ready"] is True
    assert payload["checks"]["live_codex_fixture_prereqs"]["ready"] is True
    assert payload["checks"]["live_codex_fixture_prereqs"]["cli_auth"]["ready"] is True
    assert payload["ready"] is True
    assert payload["remaining"] == []
    redacted = json.dumps(payload)
    assert "email" not in redacted
    assert "orgId" not in redacted
    assert "orgName" not in redacted
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["ready"]}


def test_phase1_acceptance_payload_schema() -> None:
    payload = acceptance_payload()

    assert payload["schema_version"] == "poor-cli-phase1-acceptance-v1"
    assert set(payload["checks"]) == {
        "anthropic_fixture_bugs",
        "offline_replay_determinism",
        "source_loc",
        "system_prompt_budget",
        "swe_lite_10",
    }
    assert payload["checks"]["anthropic_fixture_bugs"]["tests_passed_count"] == 3
    assert payload["checks"]["offline_replay_determinism"]["missing_fragments"] == []
    assert payload["checks"]["source_loc"]["total"] <= 5000
    assert payload["checks"]["system_prompt_budget"]["bytes"] <= 1000
    assert payload["checks"]["swe_lite_10"]["pass_rate"] >= 0.30
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["accepted"]}


def test_checked_in_phase1_acceptance_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase1-acceptance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-phase1-acceptance-v1"
    assert payload["accepted"] is True
    assert payload["remaining"] == []
    assert payload["checks"]["anthropic_fixture_bugs"]["completed_count"] == 3
    assert payload["checks"]["anthropic_fixture_bugs"]["tests_passed_count"] == 3
    assert payload["checks"]["anthropic_fixture_bugs"]["replay_verified_count"] == 3
    assert payload["checks"]["offline_replay_determinism"]["accepted"] is True
    assert payload["checks"]["source_loc"]["total"] <= 5000
    assert payload["checks"]["system_prompt_budget"]["bytes"] <= 1000
    assert payload["checks"]["swe_lite_10"]["total_instances"] == 10
    assert payload["checks"]["swe_lite_10"]["resolved_instances"] == 9
    assert payload["checks"]["swe_lite_10"]["unresolved_ids"] == ["astropy__astropy-14182"]


def test_phase3_readiness_payload_schema() -> None:
    payload = phase3_readiness_payload()

    assert payload["schema_version"] == "poor-cli-phase3-readiness-v1"
    assert isinstance(payload["ready"], bool)
    assert set(payload["checks"]) == {
        "setup_script",
        "provider_adapters",
        "linux_cuda_host",
        "engine_python_deps",
        "ollama_binary",
        "local_agent_path",
    }
    assert payload["checks"]["setup_script"]["ready"] is True
    assert payload["checks"]["provider_adapters"]["providers"] == ["ollama", "sglang", "vllm"]
    assert payload["checks"]["local_agent_path"]["ready"] is True
    assert payload["checks"]["engine_python_deps"]["requirement"] == "one of vllm or sglang"
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["ready"]}


def test_checked_in_phase3_readiness_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase3-readiness.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-phase3-readiness-v1"
    assert isinstance(payload["ready"], bool)
    assert payload["checks"]["setup_script"]["ready"] is True
    assert payload["checks"]["setup_script"]["bash_syntax"] is True
    assert payload["checks"]["provider_adapters"]["ready"] is True
    assert payload["checks"]["provider_adapters"]["providers"] == ["ollama", "sglang", "vllm"]
    assert payload["checks"]["local_agent_path"]["ready"] is True
    assert payload["checks"]["local_agent_path"]["swe_runner_agent"] == "local"
    assert payload["checks"]["engine_python_deps"]["requirement"] == "one of vllm or sglang"
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["ready"]}


def test_phase3_acceptance_payload_schema() -> None:
    payload = phase3_acceptance_payload()

    assert payload["schema_version"] == "poor-cli-phase3-acceptance-v1"
    assert set(payload["checks"]) == {
        "linux_cuda_readiness",
        "local_swe_lite_10",
        "offline_graph_replay",
        "offline_network_guards",
        "local_gpu_screencast",
    }
    assert payload["checks"]["offline_graph_replay"]["accepted"] is True
    assert payload["checks"]["offline_network_guards"]["accepted"] is True
    assert "errors" in payload["checks"]["local_gpu_screencast"]
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["accepted"]}


def test_checked_in_phase3_acceptance_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase3-acceptance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-phase3-acceptance-v1"
    assert payload["accepted"] is False
    assert payload["checks"]["offline_graph_replay"]["accepted"] is True
    assert payload["checks"]["offline_network_guards"]["accepted"] is True
    assert payload["checks"]["linux_cuda_readiness"]["accepted"] is False
    assert payload["checks"]["local_swe_lite_10"]["accepted"] is False
    assert payload["checks"]["local_gpu_screencast"]["accepted"] is False
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["accepted"]}


def test_phase3_demo_plan_schema() -> None:
    payload = demo_plan_payload()

    assert payload["schema_version"] == "poor-cli-phase3-demo-plan-v1"
    assert payload["target"]["requires_linux_cuda"] is True
    assert payload["target"]["requires_internet_disabled"] is True
    assert "--agents local" in payload["commands"]["run_demo"]
    assert "--offline replay" in payload["commands"]["replay"]


def test_checked_in_phase3_demo_plan() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase3-demo-plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["plan"] == demo_plan_payload()
    assert payload["validation"]["accepted"] is False


def test_phase3_demo_validator_accepts_real_evidence(tmp_path: Path) -> None:
    video = tmp_path / "phase3-demo.mp4"
    video.write_bytes(b"demo")
    evidence = tmp_path / "phase3-demo.json"
    evidence.write_text(
        json.dumps(
            {
                "duration_seconds": 60,
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "internet_disabled": True,
                "local_gpu": True,
                "graph_tools_visible": True,
                "offline_replay_verified": True,
                "run_id": "run_demo",
                "video_path": str(video),
                "commands": [
                    'poor-cli run "fix bug" --graph --agents local --yes',
                    "poor-cli --offline replay run_demo --verify",
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = validate_demo_evidence(evidence)

    assert payload["accepted"] is True
    assert payload["errors"] == []


def test_phase3_demo_validator_rejects_missing_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "phase3-demo.json"
    evidence.write_text("{}", encoding="utf-8")

    payload = validate_demo_evidence(evidence)

    assert payload["accepted"] is False
    assert "duration_seconds must be between 45 and 75" in payload["errors"]
    assert "video_path must exist" in payload["errors"]


def test_pivot_remaining_payload_schema() -> None:
    payload = remaining_payload()

    assert payload["schema_version"] == "poor-cli-pivot-remaining-v1"
    assert set(payload["checks"]) == {
        "phase2_fixed_swe_graph_mode",
        "phase3_linux_cuda_readiness",
        "phase3_local_mode_benchmark",
        "phase3_offline_graph_replay",
        "phase3_local_gpu_screencast",
    }
    assert payload["complete"] is False
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["done"]}


def test_checked_in_pivot_remaining_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "pivot-remaining.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-pivot-remaining-v1"
    assert payload["complete"] is False
    assert payload["checks"]["phase2_fixed_swe_graph_mode"]["done"] is True
    assert payload["checks"]["phase2_fixed_swe_graph_mode"]["resolved_instances"] == 8
    assert payload["checks"]["phase2_fixed_swe_graph_mode"]["total_instances"] == 10
    assert payload["checks"]["phase3_linux_cuda_readiness"]["done"] is False
    assert payload["checks"]["phase3_local_mode_benchmark"]["done"] is False
    assert payload["checks"]["phase3_offline_graph_replay"]["done"] is True
    assert payload["checks"]["phase3_local_gpu_screencast"]["done"] is False
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["done"]}


def test_phase3_local_benchmark_plan_schema() -> None:
    payload = benchmark_plan_payload()

    assert payload["schema_version"] == "poor-cli-phase3-local-benchmark-plan-v1"
    assert payload["target"]["agent"] == "local"
    assert payload["target"]["providers"] == ["ollama", "sglang", "vllm"]
    assert payload["target"]["minimum_of_anthropic_pass_rate"] == 0.5
    assert payload["target"]["requires_graph_mode"] is True
    assert "--graph --agent local" in payload["commands"]["generate"]
    assert "phase3_local_benchmark.py --summary" in payload["commands"]["verify"]


def test_checked_in_phase3_local_benchmark_plan() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase3-local-benchmark-plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["plan"] == benchmark_plan_payload()


def test_phase3_local_benchmark_accepts_target_summary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "provider": "vllm",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "agent": "local",
                "graph_mode": True,
                "task_count": 10,
                "replay_verified_count": 10,
                "official_evaluation": {
                    "exit_code": 0,
                    "results": {
                        "total_instances": 10,
                        "resolved_instances": 5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = validate_local_summary(summary)

    assert payload["accepted"] is True
    assert payload["pass_rate"] == 0.5
    assert payload["target_rate"] == 0.45
    assert payload["errors"] == []


def test_phase3_local_benchmark_rejects_missing_graph_or_low_pass(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "provider": "vllm",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "agent": "local",
                "graph_mode": False,
                "task_count": 10,
                "replay_verified_count": 9,
                "official_evaluation": {
                    "exit_code": 0,
                    "results": {
                        "total_instances": 10,
                        "resolved_instances": 4,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = validate_local_summary(summary)

    assert payload["accepted"] is False
    assert "summary was not run in graph mode" in payload["errors"]
    assert "offline replay did not verify every task" in payload["errors"]
    assert "local pass rate is below 50% of Anthropic pass rate" in payload["errors"]


def test_graph_vs_grep_payload_schema() -> None:
    payload = graph_vs_grep_payload(modules=12, filler_lines=4, min_loc=0)

    assert payload["schema_version"] == "poor-cli-graph-vs-grep-v1"
    assert payload["accepted"] is True
    assert payload["modes"]["grep"]["correct"] is True
    assert payload["modes"]["graph"]["correct"] is True
    assert payload["modes"]["graph"]["input_tokens"] < payload["modes"]["grep"]["input_tokens"]
    assert payload["token_reduction"] >= 0.30


def test_checked_in_graph_vs_grep_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "graph-vs-grep-synthetic.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-graph-vs-grep-v1"
    assert payload["accepted"] is True
    assert payload["fixture"]["line_count"] >= 50_000
    assert payload["modes"]["grep"]["correct"] is True
    assert payload["modes"]["graph"]["correct"] is True
    assert payload["token_reduction"] >= 0.30


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
    args = swe_run.parse_args(["--confirm-cost", "--no-evaluate", "--limit", "1", "--agent", "claude", "--budget-usd", "2.5"])
    task = {"instance_id": "repo__proj-1", "problem_statement": "Fix the bug", "repo": "repo/proj"}

    command = swe_run.poor_cli_run_command(args, tmp_path / "store", "Fix the bug")
    payload = swe_run.planner_payload(task, "claude")
    planner = swe_run.write_planner(tmp_path / "result" / "planner.py", task, "claude")
    env = swe_run.poor_cli_env(args, planner)

    assert "exec" not in command
    assert command[-5:] == ["run", "Fix the bug", "--yes", "--budget", "2.5"]
    assert str(planner.resolve()) in env["POOR_CLI_PLANNER_COMMAND"]
    assert payload["tasks"][0]["suggested_agent"] == "claude"
    assert payload["tasks"][0]["objective"] == "Fix the bug"
    assert swe_run.extract_run_id("run_id: run_123\n1. task -> claude\n") == "run_123"


def test_swe_lite_runner_supports_graph_mode(tmp_path: Path) -> None:
    args = swe_run.parse_args(["--confirm-cost", "--no-evaluate", "--limit", "1", "--agent", "claude", "--graph"])
    task = {"instance_id": "repo__proj-1", "problem_statement": "Fix the bug", "repo": "repo/proj"}

    command = swe_run.poor_cli_run_command(args, tmp_path / "store", "Fix the bug")
    payload = swe_run.planner_payload(task, "claude", graph=True)
    summary = swe_run.summarize([], args, "run-graph")

    assert command[-2:] == ["--graph", "--yes"]
    assert "graph-mode" in payload["assumptions"][0]
    assert "find_symbol" in payload["assumptions"][0]
    assert summary["graph_mode"] is True


def test_swe_lite_runner_supports_local_agent(tmp_path: Path) -> None:
    args = swe_run.parse_args(
        [
            "--confirm-cost",
            "--no-evaluate",
            "--limit",
            "1",
            "--agent",
            "local",
            "--provider",
            "vllm",
            "--model",
            "qwen",
            "--local-base-url",
            "http://vllm.test",
        ]
    )
    task = {"instance_id": "repo__proj-1", "problem_statement": "Fix the bug", "repo": "repo/proj"}

    command = swe_run.poor_cli_run_command(args, tmp_path / "store", "Fix the bug")
    env = swe_run.poor_cli_env(args)
    payload = swe_run.planner_payload(task, "local")
    summary = swe_run.summarize([], args, "run-local")

    assert command[-1] == "--yes"
    assert env["POOR_CLI_PROVIDER"] == "vllm"
    assert env["POOR_CLI_MODEL"] == "qwen"
    assert env["POOR_CLI_LOCAL_BASE_URL"] == "http://vllm.test"
    assert payload["tasks"][0]["suggested_agent"] == "local"
    assert summary["agent"] == "local"
    assert summary["provider"] == "vllm"
    assert summary["model"] == "qwen"
    assert summary["local_base_url"] == "http://vllm.test"


def test_swe_lite_runner_evaluates_existing_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "results" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "predictions.jsonl").write_text('{"instance_id":"repo__proj-1","model_patch":""}\n', encoding="utf-8")
    (run_dir / "summary.json").write_text('{"run_id":"run-1","official_evaluation":{}}\n', encoding="utf-8")
    calls = {}

    def fake_evaluation(args: object, received_run_dir: Path, run_id: str) -> dict[str, object]:
        calls["run_dir"] = received_run_dir
        calls["run_id"] = run_id
        return {"exit_code": 0, "wall_time_seconds": 1.0, "results": {"resolved": []}}

    monkeypatch.setattr(swe_run, "run_official_evaluation", fake_evaluation)

    code = swe_run.main(["--results-dir", str(tmp_path / "results"), "--evaluate-existing-run", "run-1", "--confirm-cost"])
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert code == 0
    assert calls == {"run_dir": run_dir, "run_id": "run-1"}
    assert summary["official_evaluation"]["exit_code"] == 0
    assert summary["official_evaluation"]["results"] == {"resolved": []}


def test_swe_lite_official_eval_uses_prediction_ids_and_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = swe_run.parse_args(
        [
            "--confirm-cost",
            "--eval-max-workers",
            "1",
            "--eval-timeout",
            "7",
            "--eval-namespace",
            "none",
            "--eval-force-rebuild",
            "--eval-cache-level",
            "none",
            "--eval-clean",
            "--store-root",
            str(tmp_path / "stores"),
        ]
    )
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    (run_dir / "predictions.jsonl").write_text(
        '{"instance_id":"repo__proj-1","model_patch":""}\n{"instance_id":"repo__proj-2","model_patch":""}\n',
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **_kwargs: object) -> swe_run.subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["env"] = _kwargs["env"]
        (run_dir / "model.run-1.json").write_text('{"resolved_ids":["repo__proj-1"]}\n', encoding="utf-8")
        return swe_run.subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(swe_run, "run_command", fake_run)

    result = swe_run.run_official_evaluation(args, run_dir, "run-1")
    command = captured["command"]
    env = captured["env"]

    assert isinstance(command, list)
    assert isinstance(env, dict)
    assert command[command.index("--instance_ids") + 1 :] == ["repo__proj-1", "repo__proj-2"]
    assert command[command.index("--namespace") + 1] == "none"
    assert command[command.index("--force_rebuild") + 1] == "True"
    assert command[command.index("--cache_level") + 1] == "none"
    assert command[command.index("--clean") + 1] == "True"
    assert command[command.index("--timeout") + 1] == "7"
    docker_config = (Path(args.store_root).resolve().parent / "docker-config" / run_dir.name).resolve()
    assert env["DOCKER_CONFIG"] == str(docker_config)
    assert json.loads((docker_config / "config.json").read_text(encoding="utf-8")) == {"auths": {}}
    assert result["results_json"].endswith("model.run-1.json")
    assert result["results"] == {"resolved_ids": ["repo__proj-1"]}


def test_checked_in_swe_lite_smoke_result() -> None:
    run_dir = Path(__file__).resolve().parents[1] / "bench" / "swe_bench_lite" / "results" / "smoke-claude-20260614T035359Z"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "astropy__astropy-12907" / "result.json").read_text(encoding="utf-8"))

    assert summary["task_count"] == 1
    assert summary["completed_exec_count"] == 1
    assert summary["replay_verified_count"] == 1
    assert summary["budget_usd"] == 1.0
    official = summary["official_evaluation"]
    assert official["exit_code"] == 0
    assert official["results_json"].endswith("claude-sonnet-4-20250514.smoke-claude-20260614T035359Z.json")
    assert official["results"]["total_instances"] == 1
    assert official["results"]["submitted_ids"] == ["astropy__astropy-12907"]
    assert official["results"]["completed_ids"] == ["astropy__astropy-12907"]
    assert official["results"]["resolved_ids"] == ["astropy__astropy-12907"]
    assert official["results"]["error_ids"] == []
    assert result["instance_id"] == "astropy__astropy-12907"
    assert result["exit_code"] == 0
    assert result["replay_verified"] is True
    assert result["patch_bytes"] == 506
    assert len(result["replay_trace_sha256"]) == 64


def test_checked_in_swe_lite_10_result() -> None:
    run_dir = Path(__file__).resolve().parents[1] / "bench" / "swe_bench_lite" / "results" / "swe10-claude-20260614T105615Z"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (run_dir / "task_results.jsonl").read_text(encoding="utf-8").splitlines()]
    official_report = json.loads((run_dir / "claude-sonnet-4-20250514.swe10-claude-20260614T105615Z.json").read_text(encoding="utf-8"))

    assert summary["task_count"] == 10
    assert summary["completed_exec_count"] == 7
    assert summary["replay_verified_count"] == 10
    assert summary["budget_usd"] == 1.0
    official = summary["official_evaluation"]
    assert official["exit_code"] == 0
    assert official["results_json"].endswith("claude-sonnet-4-20250514.swe10-claude-20260614T105615Z.json")
    assert official["results"]["submitted_instances"] == 10
    assert official["results"]["completed_instances"] == 10
    assert official["results"]["resolved_instances"] == 9
    assert official["results"]["unresolved_instances"] == 1
    assert official["results"]["error_instances"] == 0
    assert official["results"]["unresolved_ids"] == ["astropy__astropy-14182"]
    assert official_report["resolved_instances"] == 9
    assert official_report["unresolved_ids"] == ["astropy__astropy-14182"]
    assert len(rows) == 10
    assert sum(1 for row in rows if row["exit_code"] == 0) == 7
    assert all(row["replay_verified"] is True for row in rows)
    assert all(row["patch_bytes"] > 0 for row in rows)
    assert all(len(row["replay_trace_sha256"]) == 64 for row in rows)


def test_checked_in_swe_lite_10_graph_result() -> None:
    run_dir = Path(__file__).resolve().parents[1] / "bench" / "swe_bench_lite" / "results" / "swe10-graph-20260615T020703Z"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (run_dir / "task_results.jsonl").read_text(encoding="utf-8").splitlines()]
    official_report = json.loads((run_dir / "claude-sonnet-4-20250514.swe10-graph-20260615T020703Z.json").read_text(encoding="utf-8"))

    assert summary["graph_mode"] is True
    assert summary["task_count"] == 10
    assert summary["completed_exec_count"] == 9
    assert summary["replay_verified_count"] == 10
    assert summary["budget_usd"] == 1.0
    official = summary["official_evaluation"]
    assert official["exit_code"] == 0
    assert official["results_json"].endswith("claude-sonnet-4-20250514.swe10-graph-20260615T020703Z.json")
    assert official["results"]["submitted_instances"] == 10
    assert official["results"]["completed_instances"] == 10
    assert official["results"]["resolved_instances"] == 8
    assert official["results"]["unresolved_instances"] == 2
    assert official["results"]["error_instances"] == 0
    assert official["results"]["unresolved_ids"] == ["astropy__astropy-14182", "django__django-11019"]
    assert official_report["resolved_instances"] == 8
    assert official_report["unresolved_ids"] == ["astropy__astropy-14182", "django__django-11019"]
    assert len(rows) == 10
    assert sum(1 for row in rows if row["exit_code"] == 0) == 9
    assert all(row["graph_mode"] is True for row in rows)
    assert all(row["replay_verified"] is True for row in rows)
    assert all(row["patch_bytes"] > 0 for row in rows)
    assert all(len(row["replay_trace_sha256"]) == 64 for row in rows)
