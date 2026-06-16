from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from bench.claims_gate import scan_claims
from bench.dogfood_report import audit as dogfood_audit
from bench.graph_vs_grep import graph_vs_grep_payload
from bench.harness_report import evaluation_fixture_payload, reduce_report, swe_smoke_audit
from bench.local_fixture_bugs import compact_payload, run_fixture_suite
from bench.phase1_acceptance import acceptance_payload
from bench.phase1_readiness import readiness_payload
from bench.phase3_acceptance import acceptance_payload as phase3_acceptance_payload
from bench.phase3_closeout import closeout_payload
from bench.phase3_demo import demo_evidence_template, demo_plan_payload, validate_demo_evidence
from bench.phase3_demo import main as phase3_demo_main
from bench.phase3_local_benchmark import benchmark_plan_payload, is_local_summary_candidate, validate_local_summary
from bench.phase3_readiness import _linux_cuda_host, _ollama_binary, _python_deps, _selected_engine_supported, _setup_python
from bench.phase3_readiness import readiness_payload as phase3_readiness_payload
from bench.pivot_remaining import remaining_payload
from bench.release_gate import CUTS
from bench.release_gate import audit as release_audit
from bench.run_diff_acceptance import acceptance_payload as run_diff_acceptance_payload
from bench.swe_bench_lite import run as swe_run
from poor_cli.store import RunStore


def _demo_probe_evidence() -> dict[str, object]:
    return {
        "network_probe": {
            "command": "curl --fail --silent --show-error --max-time 5 https://example.com",
            "exit_code": 6,
        },
        "gpu_probe": {
            "command": "nvidia-smi --query-gpu=name --format=csv,noheader",
            "exit_code": 0,
            "output": "NVIDIA GeForce RTX 4090\n",
        },
    }


def _write_phase3_local_artifacts(
    run_dir: Path,
    *,
    provider: str = "vllm",
    model: str = "Qwen/Qwen2.5-Coder-32B-Instruct",
    agent: str = "local",
    graph_mode: bool = True,
    task_count: int = 10,
    local_base_url: str = "http://localhost:8000",
    local_model_source: str = "",
    local_served_model: str = "",
    local_quantization: str = "",
    local_dtype: str = "",
    local_max_model_len: str = "",
    local_tensor_parallel_size: str = "",
    local_gpu_memory_utilization: str = "",
    write_manifest: bool = True,
) -> None:
    local_metadata = {
        "local_model_source": local_model_source,
        "local_served_model": local_served_model,
        "local_quantization": local_quantization,
        "local_dtype": local_dtype,
        "local_max_model_len": local_max_model_len,
        "local_tensor_parallel_size": local_tensor_parallel_size,
        "local_gpu_memory_utilization": local_gpu_memory_utilization,
    }
    environment = {
        "provider": provider,
        "model": model,
        "agent": agent,
        "graph_mode": graph_mode,
        "local_base_url": local_base_url,
        **local_metadata,
    }
    (run_dir / "environment.json").write_text(json.dumps(environment), encoding="utf-8")
    task_lines = []
    prediction_lines = []
    for index in range(task_count):
        instance_id = f"repo__proj-{index}"
        task_lines.append(
            json.dumps(
                {
                    "instance_id": instance_id,
                    "provider": provider,
                    "model": model,
                    "agent": agent,
                    "graph_mode": graph_mode,
                    "replay_verified": True,
                    "poor_cli_run_id": f"run-{index}",
                    "poor_cli_store_dir": f"store/{index}",
                    **local_metadata,
                },
                sort_keys=True,
            )
        )
        prediction_lines.append(
            json.dumps(
                {"instance_id": instance_id, "model_patch": "diff --git a/file.py b/file.py\n"},
                sort_keys=True,
            )
        )
    (run_dir / "task_results.jsonl").write_text("\n".join(task_lines) + "\n", encoding="utf-8")
    (run_dir / "predictions.jsonl").write_text("\n".join(prediction_lines) + "\n", encoding="utf-8")
    if write_manifest:
        source = local_model_source or model
        quantization = local_quantization or "none"
        dtype = local_dtype or "bfloat16"
        context = local_max_model_len or "32768"
        manifest = {
            "schema_version": "poor-cli-phase3-run-manifest-v1",
            "docker_images": {
                "swebench_eval": "swebench/swe-bench@sha256:" + ("a" * 64),
                "sandbox_base": "swebench/swe-eval@sha256:" + ("b" * 64),
            },
            "runtime": {"PYTHONHASHSEED": "0"},
            "generation": {"temperature": 0, "top_p": 1.0},
            "model": {
                "source": source,
                "served": model,
                "quantization": quantization,
                "dtype": dtype,
                "context_length": context,
                "weight_hash": "sha256:" + ("c" * 64),
            },
            "harness_versions": {"swebench": "4.1.0", "datasets": "4.8.4", "poor_cli": "6.0.0a1"},
        }
        (run_dir / "run_manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


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


def test_evaluation_fixture_covers_required_categories() -> None:
    payload = evaluation_fixture_payload()

    assert payload["schema_version"] == "poor-cli-evaluation-tasks-v1"
    assert {task["category"] for task in payload["tasks"]} >= {
        "simple_edit",
        "multi_file_refactor",
        "bug_fix",
        "ambiguous_design",
        "graph_lookup",
        "web_research",
    }
    assert "swarm" in payload["modes"]
    assert "second_model_review" in payload["modes"]


def test_review_rubric_covers_quality_dimensions() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "fixtures" / "review_rubric.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids = {row["id"] for row in payload["checklist"]}

    assert payload["schema_version"] == "poor-cli-review-rubric-v1"
    assert ids == {
        "correctness",
        "minimal_diff",
        "tests",
        "security",
        "maintainability",
        "assumptions",
        "contrary_evidence",
        "claim_discipline",
    }


def test_harness_report_reduces_cost_per_passed_task() -> None:
    payload = reduce_report(
        [
            {"mode": "direct", "passed": True, "cost_usd": 0.2, "duration_seconds": 10},
            {"mode": "direct", "passed": False, "cost_usd": 0.1, "duration_seconds": 30, "failure_category": "tests"},
            {"mode": "swarm", "passed": True, "cost_usd": 0.6, "duration_seconds": 20},
        ]
    )

    assert payload["modes"]["direct"]["pass_rate"] == 0.5
    assert payload["modes"]["direct"]["cost_per_passed_task_usd"] == 0.3
    assert payload["modes"]["direct"]["failure_categories"] == {"tests": 1}
    assert payload["modes"]["swarm"]["p95_time_seconds"] == 20


def test_fusion_eval_fixture_compares_single_and_fusion() -> None:
    payload = json.loads((Path(__file__).resolve().parents[1] / "bench" / "results" / "fusion-eval-fixture.json").read_text())

    assert {"single_planner", "fusion_planner"} <= set(payload["modes"])
    assert payload["task_set"] == "poor-cli-evaluation-ambiguous-design"


def test_dogfood_report_requires_all_scenarios(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    try:
        for index, kinds in enumerate(
            [
                ["agent.result", "handoff.packet"],
                ["artifact.review", "artifact.verify"],
                ["swarm.merge_plan"],
                ["web.search", "web.fetch", "web.citation"],
                ["budget.ledger"],
                [],
                ["benchmark.report"],
            ]
        ):
            run_id = store.create_run(user_goal=f"dogfood {index}", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
            for kind in kinds:
                store.put_artifact(run_id=run_id, kind=kind, data={"ok": True})
            if index == 5:
                store.append_event(run_id, "artifacts.cleanup", {"removed": ["worktrees"]})
        payload = dogfood_audit(tmp_path / "store")
    finally:
        store.close()

    assert payload["accepted"] is True
    assert payload["checks"]["failure_cleanup"]["done"] is True


def test_release_cut_matrix_names_expected_surfaces() -> None:
    assert "Fusion" in CUTS["v6.3"]
    assert "prompt packs" in CUTS["v6.4"]
    payload = json.loads((Path(__file__).resolve().parents[1] / "bench" / "results" / "dogfood-report.json").read_text())
    assert payload["accepted"] is True


def test_release_gate_tracks_todo_strategy_doc() -> None:
    payload = release_audit(Path(__file__).resolve().parents[1])

    assert payload["checks"]["strategy_doc"] is True
    assert payload["checks"]["strategy_refs"] is True


def test_swe_smoke_audit_accepts_checked_in_runner_outputs() -> None:
    payload = swe_smoke_audit(Path(__file__).resolve().parents[1])

    assert payload["accepted"] is True
    assert payload["accepted_summary_count"] >= 1


def test_claims_gate_requires_reproducibility_context(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    bad = tmp_path / "bad.md"
    good.write_text("pass rate 8/10 on 2026-06-15 config bench/results/x.json\n", encoding="utf-8")
    bad.write_text("pass rate is 80%\n", encoding="utf-8")

    accepted = scan_claims([good])
    rejected = scan_claims([bad])

    assert accepted["accepted"] is True
    assert rejected["accepted"] is False
    assert rejected["violations"][0]["line"] == 1


def test_claims_gate_rejects_disallowed_superiority_claim(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text("poor-cli is the best replay CLI\n", encoding="utf-8")

    rejected = scan_claims([bad])

    assert rejected["accepted"] is False
    assert rejected["violations"][0]["kind"] == "disallowed_claim"


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
    assert payload["checks"]["source_loc"]["total"] <= 8200
    assert payload["checks"]["source_loc"]["max_total"] == 8200
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
    assert payload["checks"]["source_loc"]["total"] <= 8200
    assert payload["checks"]["source_loc"]["max_total"] == 8200
    assert payload["checks"]["system_prompt_budget"]["bytes"] <= 1000
    assert payload["checks"]["swe_lite_10"]["total_instances"] == 10
    assert payload["checks"]["swe_lite_10"]["resolved_instances"] == 9
    assert payload["checks"]["swe_lite_10"]["unresolved_ids"] == ["astropy__astropy-14182"]


def test_checked_in_replay_verify_acceptance_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "replay-verify-acceptance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["accepted"] is True
    assert payload["first"] == payload["second"]
    assert payload["first"]["schema_version"] == "poor-cli-replay-verify-v1"
    assert payload["first"]["record_schema_version"] == "poor-cli-record-v1"
    assert payload["first"]["network"] == {"asserted": True, "attempts": 0}
    assert payload["first"]["verified"] is True


def test_run_diff_acceptance_payload_schema() -> None:
    payload = run_diff_acceptance_payload()

    assert payload["schema_version"] == "poor-cli-run-diff-acceptance-v1"
    assert payload["accepted"] is True
    assert payload["checks"] == {
        "artifact_change": True,
        "fail_on_change": True,
        "fork_record": True,
        "repo_delta_change": True,
        "route_change": True,
    }


def test_checked_in_run_diff_acceptance_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "run-diff-acceptance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-run-diff-acceptance-v1"
    assert payload["accepted"] is True
    assert payload["diff_schema_version"] == "poor-cli-run-diff-v1"
    assert payload["fork_schema_version"] == "poor-cli-run-fork-v1"


def test_phase3_readiness_payload_schema() -> None:
    payload = phase3_readiness_payload()

    assert payload["schema_version"] == "poor-cli-phase3-readiness-v1"
    assert payload["selected_engine"] == "vllm"
    assert isinstance(payload["ready"], bool)
    assert set(payload["checks"]) == {
        "setup_script",
        "setup_python",
        "provider_adapters",
        "selected_engine",
        "linux_cuda_host",
        "docker",
        "engine_python_deps",
        "ollama_binary",
        "local_agent_path",
    }
    assert payload["checks"]["setup_script"]["ready"] is True
    assert payload["checks"]["setup_python"]["ready"] is True
    assert payload["checks"]["setup_python"]["requirement"] == ">=3.11,<3.15"
    assert payload["checks"]["linux_cuda_host"]["requirement"] == "Linux with nvidia-smi returning at least one GPU"
    assert "query_exit_code" in payload["checks"]["linux_cuda_host"]
    assert "gpu_memory_total_mb" in payload["checks"]["linux_cuda_host"]
    assert "stderr" in payload["checks"]["linux_cuda_host"]
    assert payload["checks"]["provider_adapters"]["providers"] == ["ollama", "sglang", "vllm"]
    assert payload["checks"]["selected_engine"]["ready"] is True
    assert payload["checks"]["selected_engine"]["engine"] == "vllm"
    assert payload["checks"]["docker"]["requirement"] == "Docker daemon for SWE-bench eval"
    assert payload["checks"]["local_agent_path"]["ready"] is True
    assert payload["checks"]["engine_python_deps"]["requirement"] == "selected engine module: vllm"
    assert payload["checks"]["engine_python_deps"]["selected_engine"] == "vllm"
    assert payload["checks"]["engine_python_deps"]["required"] is True
    assert payload["checks"]["engine_python_deps"]["install"] == "scripts/setup-linux-cuda.sh --yes --engine vllm"
    assert payload["checks"]["ollama_binary"]["required"] is False
    assert set(payload["checks"]["engine_python_deps"]["modules"]) == {"vllm", "sglang"}
    assert set(payload["checks"]["engine_python_deps"]["current_modules"]) == {"vllm", "sglang"}
    assert set(payload["checks"]["engine_python_deps"]["venv_modules"]) == {"vllm", "sglang"}
    assert payload["checks"]["engine_python_deps"]["venv_python"].endswith(".poor-cli/local-cuda-venv/bin/python")
    assert set(payload["remaining"]) == {name for name, check in payload["checks"].items() if not check["ready"]}


def test_phase3_readiness_requires_successful_nvidia_smi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bench.phase3_readiness.platform.system", lambda: "Linux")
    monkeypatch.setattr("bench.phase3_readiness.shutil.which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)

    def failed_query(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["nvidia-smi"], 9, "", "driver not loaded")

    monkeypatch.setattr("bench.phase3_readiness.subprocess.run", failed_query)

    payload = _linux_cuda_host()

    assert payload["ready"] is False
    assert payload["nvidia_smi"] is True
    assert payload["query_exit_code"] == 9
    assert payload["gpu_names"] == []
    assert payload["gpu_memory_total_mb"] == []
    assert payload["stderr"] == "driver not loaded"


def test_phase3_readiness_accepts_successful_gpu_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bench.phase3_readiness.platform.system", lambda: "Linux")
    monkeypatch.setattr("bench.phase3_readiness.shutil.which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)

    def successful_query(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["nvidia-smi"], 0, "NVIDIA GeForce RTX 4090, 24576\n", "")

    monkeypatch.setattr("bench.phase3_readiness.subprocess.run", successful_query)

    payload = _linux_cuda_host()

    assert payload["ready"] is True
    assert payload["query_exit_code"] == 0
    assert payload["gpu_names"] == ["NVIDIA GeForce RTX 4090"]
    assert payload["gpu_memory_total_mb"] == [24576]


def test_phase3_readiness_detects_engine_deps_from_local_cuda_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    venv = tmp_path / "local-cuda-venv"
    python = venv / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(
        '#!/usr/bin/env bash\nif [[ "${3:-}" == "vllm" ]]; then\n  exit 0\nfi\nexit 1\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    monkeypatch.setenv("POOR_CLI_LOCAL_VENV", str(venv))

    payload = _python_deps("vllm", "sglang")

    assert payload["ready"] is True
    assert payload["modules"]["vllm"] is True
    assert payload["venv_modules"] == {"vllm": True, "sglang": False}
    assert payload["venv_python"] == str(python)
    assert payload["venv_python_exists"] is True


def test_phase3_readiness_requires_selected_python_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    venv = tmp_path / "local-cuda-venv"
    python = venv / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(
        '#!/usr/bin/env bash\nif [[ "${3:-}" == "vllm" ]]; then\n  exit 0\nfi\nexit 1\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    monkeypatch.setenv("POOR_CLI_LOCAL_VENV", str(venv))

    payload = _python_deps("vllm", "sglang", selected_engine="sglang")

    assert payload["ready"] is False
    assert payload["modules"]["vllm"] is True
    assert payload["modules"]["sglang"] is False
    assert payload["requirement"] == "selected engine module: sglang"
    assert payload["install"] == "scripts/setup-linux-cuda.sh --yes --engine sglang"


def test_phase3_readiness_rejects_unsupported_selected_engine() -> None:
    payload = _selected_engine_supported("anthropic")

    assert payload["ready"] is False
    assert payload["engine"] == "anthropic"
    assert payload["supported"] == ["ollama", "sglang", "vllm"]


def test_phase3_readiness_reports_setup_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_python = tmp_path / "python3"
    fake_python.write_text("#!/usr/bin/env bash\nprintf '3.10.9\\n'\n", encoding="utf-8")
    fake_python.chmod(0o755)
    monkeypatch.setenv("POOR_CLI_LOCAL_PYTHON", str(fake_python))

    payload = _setup_python()

    assert payload["ready"] is False
    assert payload["executable"] == str(fake_python)
    assert payload["path"] == str(fake_python)
    assert payload["version"] == "3.10.9"
    assert payload["requirement"] == ">=3.11,<3.15"


def test_phase3_readiness_requires_ollama_binary_only_for_ollama(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    assert _ollama_binary("vllm")["ready"] is True
    assert _ollama_binary("vllm")["required"] is False
    assert _ollama_binary("ollama")["ready"] is False
    assert _ollama_binary("ollama")["required"] is True


def test_checked_in_phase3_readiness_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase3-readiness.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-phase3-readiness-v1"
    assert payload["selected_engine"] == "vllm"
    assert isinstance(payload["ready"], bool)
    assert payload["checks"]["setup_script"]["ready"] is True
    assert payload["checks"]["setup_script"]["bash_syntax"] is True
    assert payload["checks"]["setup_python"]["ready"] is True
    assert payload["checks"]["setup_python"]["requirement"] == ">=3.11,<3.15"
    assert payload["checks"]["provider_adapters"]["ready"] is True
    assert payload["checks"]["provider_adapters"]["providers"] == ["ollama", "sglang", "vllm"]
    assert payload["checks"]["selected_engine"]["ready"] is True
    assert payload["checks"]["selected_engine"]["engine"] == "vllm"
    assert isinstance(payload["checks"]["docker"]["ready"], bool)
    assert isinstance(payload["checks"]["docker"]["daemon"], bool)
    assert payload["checks"]["docker"]["requirement"] == "Docker daemon for SWE-bench eval"
    assert payload["checks"]["local_agent_path"]["ready"] is True
    assert payload["checks"]["local_agent_path"]["swe_runner_agent"] == "local"
    assert payload["checks"]["engine_python_deps"]["requirement"] == "selected engine module: vllm"
    assert payload["checks"]["engine_python_deps"]["required"] is True
    assert payload["checks"]["engine_python_deps"]["install"] == "scripts/setup-linux-cuda.sh --yes --engine vllm"
    assert payload["checks"]["ollama_binary"]["required"] is False
    assert set(payload["checks"]["engine_python_deps"]["modules"]) == {"vllm", "sglang"}
    assert set(payload["checks"]["engine_python_deps"]["current_modules"]) == {"vllm", "sglang"}
    assert set(payload["checks"]["engine_python_deps"]["venv_modules"]) == {"vllm", "sglang"}
    assert "venv_python_exists" in payload["checks"]["engine_python_deps"]
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
    assert payload["target"]["requires_network_disabled_probe"] is True
    assert payload["target"]["requires_gpu_probe"] is True
    assert payload["target"]["model_markers"] == ["qwen2.5-coder", "32b"]
    assert "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ" in payload["target"]["quantized_model_examples"]
    assert "setup_quantized" in payload["commands"]
    assert "--agents local" in payload["commands"]["run_demo"]
    assert "--offline --store-dir <poor_cli_store_dir> replay <poor_cli_run_id> --verify" in payload["commands"]["replay"]
    assert "--write-template" in payload["commands"]["write_evidence"]
    assert "--store-dir <poor_cli_store_dir>" in payload["commands"]["write_evidence"]
    assert "--source-model <loaded-model-id>" in payload["commands"]["write_evidence"]


def test_checked_in_phase3_demo_plan() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase3-demo-plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["plan"] == demo_plan_payload()
    assert payload["validation"]["accepted"] is False


def test_phase3_closeout_payload_schema() -> None:
    payload = closeout_payload()

    assert payload["schema_version"] == "poor-cli-phase3-closeout-v1"
    assert payload["accepted"] is False
    assert set(payload["checks"]) == {"phase3_acceptance", "pivot_remaining"}
    assert "--start-server" in payload["target_host_commands"]["run_all"]
    assert "--write-demo-evidence" in payload["target_host_commands"]["run_all"]
    assert "--demo-offline-replay-verified" in payload["target_host_commands"]["run_all"]
    assert "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ" in payload["target_host_commands"]["setup_quantized"]
    assert "--agent local" in payload["target_host_commands"]["generate_local_swe"]
    assert "--source-model <loaded-model-id>" in payload["target_host_commands"]["write_demo_evidence"]
    assert "phase3_demo.py --write-template" in payload["target_host_commands"]["write_demo_evidence"]
    assert "phase3_demo.py --evidence" in payload["target_host_commands"]["verify_demo"]
    assert set(payload["remaining"]) == set(payload["checks"]["phase3_acceptance"]["remaining"]) | set(
        payload["checks"]["pivot_remaining"]["remaining"]
    )


def test_checked_in_phase3_closeout_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "phase3-closeout.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-phase3-closeout-v1"
    assert payload["accepted"] is False
    assert payload["target_host_commands"] == closeout_payload()["target_host_commands"]
    assert "--start-server" in payload["target_host_commands"]["run_all"]
    assert set(payload["remaining"]) == set(payload["checks"]["phase3_acceptance"]["remaining"]) | set(
        payload["checks"]["pivot_remaining"]["remaining"]
    )


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
                "store_dir": str(tmp_path / "store"),
                "video_path": str(video),
                **_demo_probe_evidence(),
                "commands": [
                    'poor-cli run "fix bug" --graph --agents local --yes',
                    f"poor-cli --offline --store-dir {tmp_path / 'store'} replay run_demo --verify",
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = validate_demo_evidence(evidence)

    assert payload["accepted"] is True
    assert payload["errors"] == []
    assert payload["store_dir"] == str(tmp_path / "store")


def test_phase3_demo_validator_accepts_quantized_32b_evidence(tmp_path: Path) -> None:
    video = tmp_path / "phase3-demo.mp4"
    video.write_bytes(b"demo")
    evidence = tmp_path / "phase3-demo.json"
    evidence.write_text(
        json.dumps(
            {
                "duration_seconds": 60,
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "source_model": "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
                "served_model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "quantization": "awq",
                "dtype": "auto",
                "max_model_len": "8192",
                "internet_disabled": True,
                "local_gpu": True,
                "graph_tools_visible": True,
                "offline_replay_verified": True,
                "run_id": "run_demo",
                "video_path": str(video),
                **_demo_probe_evidence(),
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
    assert payload["source_model"] == "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
    assert payload["quantization"] == "awq"


def test_phase3_demo_validator_resolves_video_relative_to_evidence(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "results"
    evidence_dir.mkdir()
    video = evidence_dir / "phase3-demo.mp4"
    video.write_bytes(b"demo")
    evidence = evidence_dir / "phase3-demo.json"
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
                "video_path": "phase3-demo.mp4",
                **_demo_probe_evidence(),
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


def test_phase3_demo_validator_requires_replay_of_same_run_id(tmp_path: Path) -> None:
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
                    "poor-cli --offline replay other_run --verify",
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = validate_demo_evidence(evidence)

    assert payload["accepted"] is False
    assert "commands must replay the recorded run_id offline" in payload["errors"]


def test_phase3_demo_validator_requires_target_model_size(tmp_path: Path) -> None:
    video = tmp_path / "phase3-demo.mp4"
    video.write_bytes(b"demo")
    evidence = tmp_path / "phase3-demo.json"
    evidence.write_text(
        json.dumps(
            {
                "duration_seconds": 60,
                "model": "Qwen/Qwen2.5-Coder-7B-Instruct",
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

    assert payload["accepted"] is False
    assert "model must be qwen2.5-coder-32b" in payload["errors"]


def test_phase3_demo_validator_requires_source_model_for_quantized_evidence(tmp_path: Path) -> None:
    video = tmp_path / "phase3-demo.mp4"
    video.write_bytes(b"demo")
    evidence = tmp_path / "phase3-demo.json"
    evidence.write_text(
        json.dumps(
            {
                "duration_seconds": 60,
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "quantization": "awq",
                "internet_disabled": True,
                "local_gpu": True,
                "graph_tools_visible": True,
                "offline_replay_verified": True,
                "run_id": "run_demo",
                "video_path": str(video),
                **_demo_probe_evidence(),
                "commands": [
                    'poor-cli run "fix bug" --graph --agents local --yes',
                    "poor-cli --offline replay run_demo --verify",
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = validate_demo_evidence(evidence)

    assert payload["accepted"] is False
    assert "source_model is required for quantized demo evidence" in payload["errors"]


def test_phase3_demo_validator_requires_probe_evidence(tmp_path: Path) -> None:
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

    assert payload["accepted"] is False
    assert "network_probe must show internet request failed" in payload["errors"]
    assert "gpu_probe must show nvidia-smi detected a GPU" in payload["errors"]


def test_phase3_demo_validator_requires_recorded_store_dir(tmp_path: Path) -> None:
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
                "store_dir": str(tmp_path / "store"),
                "video_path": str(video),
                "commands": [
                    'poor-cli run "fix bug" --graph --agents local --yes',
                    "poor-cli --offline --store-dir other-store replay run_demo --verify",
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = validate_demo_evidence(evidence)

    assert payload["accepted"] is False
    assert "commands must replay from the recorded store_dir" in payload["errors"]


def test_phase3_demo_validator_rejects_empty_video(tmp_path: Path) -> None:
    video = tmp_path / "phase3-demo.mp4"
    video.write_bytes(b"")
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

    assert payload["accepted"] is False
    assert "video_path must be non-empty" in payload["errors"]


def test_phase3_demo_template_writer_outputs_valid_schema(tmp_path: Path) -> None:
    video = tmp_path / "phase3-demo.mp4"
    video.write_bytes(b"demo")
    evidence = tmp_path / "phase3-demo.json"

    code = phase3_demo_main(
        [
            "--write-template",
            str(evidence),
            "--run-id",
            "run_demo",
            "--store-dir",
            str(tmp_path / "store"),
            "--video-path",
            str(video),
            "--duration-seconds",
            "60",
            "--model",
            "Qwen/Qwen2.5-Coder-32B-Instruct",
            "--source-model",
            "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
            "--served-model",
            "Qwen/Qwen2.5-Coder-32B-Instruct",
            "--quantization",
            "awq",
            "--dtype",
            "auto",
            "--max-model-len",
            "8192",
            "--internet-disabled",
            "--network-probe-exit-code",
            "6",
            "--local-gpu",
            "--gpu-probe-exit-code",
            "0",
            "--gpu-probe-output",
            "NVIDIA GeForce RTX 4090",
            "--graph-tools-visible",
            "--offline-replay-verified",
        ]
    )
    payload = validate_demo_evidence(evidence)

    assert code == 0
    assert payload["accepted"] is True
    assert payload["missing_command_fragments"] == []
    assert payload["store_dir"] == str(tmp_path / "store")
    assert payload["source_model"] == "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
    assert payload["served_model"] == "Qwen/Qwen2.5-Coder-32B-Instruct"
    assert payload["quantization"] == "awq"


def test_phase3_demo_template_requires_explicit_evidence_flags(tmp_path: Path) -> None:
    video = tmp_path / "phase3-demo.mp4"
    video.write_bytes(b"demo")
    evidence = tmp_path / "phase3-demo.json"
    evidence.write_text(
        json.dumps(
            demo_evidence_template(
                run_id="run_demo",
                video_path=str(video),
                model="Qwen/Qwen2.5-Coder-32B-Instruct",
                duration_seconds=60,
                internet_disabled=False,
                local_gpu=False,
                graph_tools_visible=False,
                offline_replay_verified=False,
                store_dir="store",
            )
        ),
        encoding="utf-8",
    )

    payload = validate_demo_evidence(evidence)

    assert payload["accepted"] is False
    assert {"internet_disabled must be true", "local_gpu must be true"} <= set(payload["errors"])


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
    assert payload["target"]["model_markers"] == ["qwen2.5-coder", "32b"]
    assert payload["target"]["task_manifest"] == "tests/fixtures/swe-lite-10/manifest.json"
    assert "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ" in payload["target"]["quantized_model_examples"]
    assert payload["target"]["minimum_of_anthropic_pass_rate"] == 0.5
    assert payload["target"]["requires_graph_mode"] is True
    assert payload["target"]["requires_official_docker_eval"] is True
    assert payload["target"]["requires_environment_artifact"] is True
    assert payload["target"]["requires_task_results_artifact"] is True
    assert payload["target"]["requires_predictions_artifact"] is True
    assert payload["target"]["requires_run_manifest"] is True
    assert "model weight hash" in payload["target"]["run_manifest_required"]
    assert "--graph --agent local" in payload["commands"]["generate"]
    assert "phase3_local_benchmark.py --summary" in payload["commands"]["verify"]
    assert "setup_quantized" in payload["commands"]


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
                "local_base_url": "http://localhost:8000",
                "graph_mode": True,
                "task_count": 10,
                "replay_verified_count": 10,
                "official_evaluation": {
                    "exit_code": 0,
                    "results": {
                        "completed_instances": 10,
                        "error_instances": 0,
                        "total_instances": 10,
                        "resolved_instances": 5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _write_phase3_local_artifacts(tmp_path)

    payload = validate_local_summary(summary)

    assert payload["accepted"] is True
    assert payload["pass_rate"] == 0.5
    assert payload["target_rate"] == 0.45
    assert payload["artifacts"]["task_results_count"] == 10
    assert payload["artifacts"]["predictions_count"] == 10
    assert payload["manifest"]["errors"] == []
    assert payload["errors"] == []


def test_phase3_local_benchmark_accepts_quantized_32b_summary(tmp_path: Path) -> None:
    local_metadata = {
        "local_model_source": "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
        "local_served_model": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "local_quantization": "awq",
        "local_dtype": "auto",
        "local_max_model_len": "8192",
        "local_tensor_parallel_size": "1",
        "local_gpu_memory_utilization": "0.90",
    }
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "provider": "vllm",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "agent": "local",
                "local_base_url": "http://localhost:8000",
                "graph_mode": True,
                "task_count": 10,
                "replay_verified_count": 10,
                **local_metadata,
                "official_evaluation": {
                    "exit_code": 0,
                    "results": {
                        "completed_instances": 10,
                        "error_instances": 0,
                        "total_instances": 10,
                        "resolved_instances": 5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _write_phase3_local_artifacts(tmp_path, **local_metadata)

    payload = validate_local_summary(summary)

    assert payload["accepted"] is True
    assert payload["local_model_source"] == "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
    assert payload["local_quantization"] == "awq"


def test_phase3_local_benchmark_rejects_summary_without_run_artifacts(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "provider": "vllm",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "agent": "local",
                "local_base_url": "http://localhost:8000",
                "graph_mode": True,
                "task_count": 10,
                "replay_verified_count": 10,
                "official_evaluation": {
                    "exit_code": 0,
                    "results": {
                        "completed_instances": 10,
                        "error_instances": 0,
                        "total_instances": 10,
                        "resolved_instances": 5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = validate_local_summary(summary)

    assert payload["accepted"] is False
    assert "environment.json is required" in payload["errors"]
    assert "run_manifest.json is required" in payload["errors"]
    assert "task_results.jsonl count must match task_count" in payload["errors"]
    assert "predictions.jsonl count must match task_count" in payload["errors"]


def test_phase3_local_benchmark_rejects_unpinned_manifest(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "provider": "vllm",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "agent": "local",
                "local_base_url": "http://localhost:8000",
                "graph_mode": True,
                "task_count": 10,
                "replay_verified_count": 10,
                "official_evaluation": {
                    "exit_code": 0,
                    "results": {
                        "completed_instances": 10,
                        "error_instances": 0,
                        "total_instances": 10,
                        "resolved_instances": 5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    _write_phase3_local_artifacts(tmp_path)
    (tmp_path / "run_manifest.json").write_text(
        json.dumps(
            {
                "docker_images": {"swebench_eval": "swebench/swe-bench:latest"},
                "runtime": {},
                "generation": {"temperature": 0.2, "top_p": 0.9},
                "model": {
                    "source": "Qwen/Qwen2.5-Coder-32B-Instruct",
                    "served": "Qwen/Qwen2.5-Coder-32B-Instruct",
                    "quantization": "none",
                    "dtype": "bfloat16",
                    "context_length": "32768",
                    "weight_hash": "sha256:not-a-hash",
                },
                "harness_versions": {"swebench": ""},
            }
        ),
        encoding="utf-8",
    )

    payload = validate_local_summary(summary)

    assert payload["accepted"] is False
    assert "docker image swebench_eval must be pinned by sha256 digest" in payload["errors"]
    assert "run_manifest PYTHONHASHSEED is required" in payload["errors"]
    assert "run_manifest temperature must be 0" in payload["errors"]
    assert "run_manifest top_p must be 1.0" in payload["errors"]
    assert "run_manifest model.weight_hash must be md5:<hex> or sha256:<hex>" in payload["errors"]
    assert "run_manifest harness_versions.swebench is required" in payload["errors"]
    assert "run_manifest harness_versions.datasets is required" in payload["errors"]
    assert "run_manifest harness_versions.poor_cli is required" in payload["errors"]


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
                        "completed_instances": 10,
                        "error_instances": 0,
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


def test_phase3_local_benchmark_rejects_eval_errors(tmp_path: Path) -> None:
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
                        "completed_instances": 9,
                        "error_instances": 1,
                        "total_instances": 10,
                        "resolved_instances": 5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = validate_local_summary(summary)

    assert payload["accepted"] is False
    assert "official SWE-bench evaluation did not complete every submitted instance" in payload["errors"]
    assert "official SWE-bench evaluation reported errors" in payload["errors"]


def test_phase3_local_benchmark_rejects_wrong_model(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "provider": "vllm",
                "model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "agent": "local",
                "graph_mode": True,
                "task_count": 10,
                "replay_verified_count": 10,
                "official_evaluation": {
                    "exit_code": 0,
                    "results": {
                        "completed_instances": 10,
                        "error_instances": 0,
                        "total_instances": 10,
                        "resolved_instances": 5,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = validate_local_summary(summary)

    assert payload["accepted"] is False
    assert "summary model is not qwen2.5-coder-32b" in payload["errors"]


def test_phase3_local_benchmark_candidate_requires_local_agent_and_provider() -> None:
    assert is_local_summary_candidate({"provider": "vllm", "agent": "local"}) is True
    assert is_local_summary_candidate({"provider": "vllm", "agent": "claude"}) is False
    assert is_local_summary_candidate({"provider": "anthropic", "agent": "local"}) is False


def test_graph_vs_grep_payload_schema() -> None:
    payload = graph_vs_grep_payload(modules=12, filler_lines=4, min_loc=0)

    assert payload["schema_version"] == "poor-cli-graph-vs-grep-v1"
    assert payload["accepted"] is True
    assert payload["modes"]["grep"]["correct"] is True
    assert payload["modes"]["graph"]["correct"] is True
    assert payload["modes"]["graph"]["input_tokens"] < payload["modes"]["grep"]["input_tokens"]
    assert payload["modes"]["graph"]["latency_seconds"] >= 0
    assert payload["modes"]["graph"]["recall_proxy"] == 1.0
    assert payload["modes"]["graph"]["token_count_proxy"] == payload["modes"]["graph"]["input_tokens"]
    assert payload["token_reduction"] >= 0.30


def test_checked_in_graph_vs_grep_snapshot() -> None:
    path = Path(__file__).resolve().parents[1] / "bench" / "results" / "graph-vs-grep-synthetic.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "poor-cli-graph-vs-grep-v1"
    assert payload["accepted"] is True
    assert payload["fixture"]["line_count"] >= 50_000
    assert payload["modes"]["grep"]["correct"] is True
    assert payload["modes"]["graph"]["correct"] is True
    assert "latency_seconds" in payload["modes"]["graph"]
    assert payload["modes"]["graph"]["recall_proxy"] == 1.0
    assert payload["modes"]["graph"]["token_count_proxy"] == payload["modes"]["graph"]["input_tokens"]
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


def test_swe_lite_runner_records_local_runtime_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
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
            "Qwen/Qwen2.5-Coder-32B-Instruct",
        ]
    )
    monkeypatch.setenv("POOR_CLI_LOCAL_MODEL_SOURCE", "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ")
    monkeypatch.setenv("POOR_CLI_LOCAL_SERVED_MODEL", "Qwen/Qwen2.5-Coder-32B-Instruct")
    monkeypatch.setenv("POOR_CLI_LOCAL_QUANTIZATION", "awq")
    monkeypatch.setenv("POOR_CLI_LOCAL_MAX_MODEL_LEN", "8192")

    summary = swe_run.summarize([], args, "run-local")

    assert summary["local_model_source"] == "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
    assert summary["local_served_model"] == "Qwen/Qwen2.5-Coder-32B-Instruct"
    assert summary["local_quantization"] == "awq"
    assert summary["local_max_model_len"] == "8192"


def test_swe_lite_runner_records_default_local_base_url() -> None:
    args = swe_run.parse_args(
        [
            "--confirm-cost",
            "--no-evaluate",
            "--limit",
            "1",
            "--agent",
            "local",
            "--provider",
            "sglang",
            "--model",
            "qwen",
        ]
    )

    env = swe_run.poor_cli_env(args)
    summary = swe_run.summarize([], args, "run-local")

    assert env["POOR_CLI_LOCAL_BASE_URL"] == "http://localhost:30000"
    assert summary["local_base_url"] == "http://localhost:30000"


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
