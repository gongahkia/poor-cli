from __future__ import annotations

import argparse
import json
from contextlib import closing
from pathlib import Path
from typing import Any

from poor_cli.replay import replay_verify
from poor_cli.store import RunStore, StoreError

ROOT = Path(__file__).resolve().parents[1]
ANTHROPIC_SUMMARY = ROOT / "bench" / "swe_bench_lite" / "results" / "swe10-claude-20260614T105615Z" / "summary.json"
ALLOWED_PROVIDERS = {"ollama", "sglang", "vllm"}
TARGET_MODEL_MARKERS = ("qwen2.5-coder", "32b")
HEX64 = set("0123456789abcdef")


def benchmark_plan_payload() -> dict[str, Any]:
    run_id = "swe10-local-YYYYMMDDTHHMMSSZ"
    return {
        "schema_version": "poor-cli-phase3-local-benchmark-plan-v1",
        "target": {
            "agent": "local",
            "providers": sorted(ALLOWED_PROVIDERS),
            "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "quantized_model_examples": [
                "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
                "Qwen/Qwen2.5-Coder-32B-Instruct-GPTQ-Int4",
            ],
            "model_markers": list(TARGET_MODEL_MARKERS),
            "task_manifest": "tests/fixtures/swe-lite-10/manifest.json",
            "task_count": 10,
            "minimum_of_anthropic_pass_rate": 0.5,
            "requires_graph_mode": True,
            "requires_official_docker_eval": True,
            "requires_full_replay_verification": True,
            "requires_recorded_run_store_replay": True,
            "requires_environment_artifact": True,
            "requires_task_results_artifact": True,
            "requires_predictions_artifact": True,
            "requires_run_manifest": True,
            "run_manifest_required": [
                "docker image sha256 digest",
                "PYTHONHASHSEED",
                "temperature",
                "top_p",
                "source model",
                "served model",
                "quantization",
                "dtype",
                "context length",
                "model weight hash",
                "harness/library versions",
            ],
        },
        "commands": {
            "setup": ("scripts/setup-linux-cuda.sh --yes --engine vllm --model Qwen/Qwen2.5-Coder-32B-Instruct"),
            "setup_quantized": (
                "scripts/setup-linux-cuda.sh --yes --engine vllm "
                "--model Qwen/Qwen2.5-Coder-32B-Instruct-AWQ "
                "--served-model Qwen/Qwen2.5-Coder-32B-Instruct "
                "--quantization awq --max-model-len 8192 --gpu-memory-utilization 0.90"
            ),
            "launch_server": ".poor-cli/local-cuda-run.sh",
            "readiness": "uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json",
            "generate": (
                "set -a; source .poor-cli/local-cuda.env; set +a; "
                "uv run --locked --extra bench python bench/swe_bench_lite/run.py "
                '--graph --agent local --provider "$POOR_CLI_PROVIDER" --model "$POOR_CLI_MODEL" '
                '--local-base-url "$POOR_CLI_LOCAL_BASE_URL" '
                f"--no-evaluate --confirm-cost --timeout-seconds 1200 --run-id {run_id}"
            ),
            "evaluate": (
                "uv run --locked --extra bench python bench/swe_bench_lite/run.py "
                f"--evaluate-existing-run {run_id} --confirm-cost --eval-max-workers 1 --eval-namespace none"
            ),
            "verify": (
                f"uv run --locked python bench/phase3_local_benchmark.py --summary bench/swe_bench_lite/results/{run_id}/summary.json"
            ),
            "audit": "uv run --locked python bench/pivot_remaining.py --output bench/results/pivot-remaining.json",
        },
    }


def validate_local_summary(summary_path: Path, *, anthropic_summary: Path = ANTHROPIC_SUMMARY) -> dict[str, Any]:
    summary = _read_json(summary_path)
    target = target_payload(anthropic_summary)
    task_count = int(summary.get("task_count") or 0)
    replay_verified = int(summary.get("replay_verified_count") or 0)
    official = summary.get("official_evaluation") if isinstance(summary.get("official_evaluation"), dict) else {}
    results = official.get("results") if isinstance(official.get("results"), dict) else {}
    total = int(results.get("total_instances") or results.get("submitted_instances") or 0)
    resolved = int(results.get("resolved_instances") or len(results.get("resolved_ids") or []))
    completed = int(results.get("completed_instances") or len(results.get("completed_ids") or []))
    error_count = int(results.get("error_instances") or len(results.get("error_ids") or []))
    pass_rate = resolved / total if total else 0.0
    artifacts = _artifact_validation(summary_path, summary, task_count)
    manifest = _manifest_validation(summary_path, summary)
    errors = _summary_errors(summary, target, task_count, replay_verified, official, total, completed, error_count, pass_rate)
    errors.extend(artifacts["errors"])
    errors.extend(manifest["errors"])
    return {
        "accepted": not errors,
        "evidence": _display_path(summary_path),
        "errors": errors,
        "provider": summary.get("provider", ""),
        "model": summary.get("model", ""),
        "local_model_source": summary.get("local_model_source", ""),
        "local_served_model": summary.get("local_served_model", ""),
        "local_quantization": summary.get("local_quantization", ""),
        "agent": summary.get("agent", ""),
        "graph_mode": bool(summary.get("graph_mode")),
        "task_count": task_count,
        "replay_verified_count": replay_verified,
        "completed_instances": completed,
        "error_instances": error_count,
        "resolved_instances": resolved,
        "total_instances": total,
        "pass_rate": pass_rate,
        "target_rate": target["target_rate"],
        "local_base_url": summary.get("local_base_url", ""),
        "artifacts": artifacts,
        "manifest": manifest,
    }


def is_local_summary_candidate(validation: dict[str, Any]) -> bool:
    return validation.get("provider") in ALLOWED_PROVIDERS and validation.get("agent") == "local"


def target_payload(anthropic_summary: Path = ANTHROPIC_SUMMARY) -> dict[str, Any]:
    summary = _read_json(anthropic_summary)
    results = summary.get("official_evaluation", {}).get("results", {})
    total = int(results.get("total_instances") or 0)
    resolved = int(results.get("resolved_instances") or 0)
    pass_rate = resolved / total if total else 0.0
    return {
        "anthropic_summary": _display_path(anthropic_summary),
        "anthropic_pass_rate": pass_rate,
        "target_rate": pass_rate * 0.5,
        "total_instances": total,
        "resolved_instances": resolved,
    }


def _summary_errors(
    summary: dict[str, Any],
    target: dict[str, Any],
    task_count: int,
    replay_verified: int,
    official: dict[str, Any],
    total: int,
    completed: int,
    error_count: int,
    pass_rate: float,
) -> list[str]:
    errors = []
    if target["target_rate"] <= 0:
        errors.append("missing Anthropic baseline target")
    if summary.get("provider") not in ALLOWED_PROVIDERS:
        errors.append("summary provider is not local")
    if summary.get("agent") != "local":
        errors.append("summary agent is not local")
    if not _target_model_markers_present(summary):
        errors.append("summary model is not qwen2.5-coder-32b")
    if summary.get("local_quantization") and not summary.get("local_model_source"):
        errors.append("summary local_model_source is required for quantized runs")
    if not _is_local_endpoint(str(summary.get("local_base_url") or "")):
        errors.append("summary local_base_url is not local")
    if summary.get("graph_mode") is not True:
        errors.append("summary was not run in graph mode")
    if task_count < 10:
        errors.append("summary has fewer than 10 tasks")
    if replay_verified < task_count or task_count == 0:
        errors.append("offline replay did not verify every task")
    exit_code = official.get("exit_code")
    if int(exit_code if exit_code is not None else 1) != 0:
        errors.append("official SWE-bench evaluation did not exit cleanly")
    if total < 10:
        errors.append("official SWE-bench evaluation has fewer than 10 submitted instances")
    if completed < total or total == 0:
        errors.append("official SWE-bench evaluation did not complete every submitted instance")
    if error_count:
        errors.append("official SWE-bench evaluation reported errors")
    if pass_rate < float(target["target_rate"]):
        errors.append("local pass rate is below 50% of Anthropic pass rate")
    return errors


def _artifact_validation(summary_path: Path, summary: dict[str, Any], task_count: int) -> dict[str, Any]:
    run_dir = summary_path.parent
    environment_path = run_dir / "environment.json"
    task_results_path = run_dir / "task_results.jsonl"
    predictions_path = run_dir / "predictions.jsonl"
    environment = _read_json(environment_path)
    task_results = _read_jsonl(task_results_path)
    predictions = _read_jsonl(predictions_path)
    errors: list[str] = []
    if not environment:
        errors.append("environment.json is required")
    else:
        _extend_mismatch_errors(errors, "environment", environment, summary)
        if not _is_local_endpoint(str(environment.get("local_base_url") or "")):
            errors.append("environment local_base_url is not local")
    if len(task_results) != task_count or task_count == 0:
        errors.append("task_results.jsonl count must match task_count")
    task_ids = []
    replay_checks = []
    for record in task_results:
        task_ids.append(str(record.get("instance_id") or ""))
        _extend_mismatch_errors(errors, "task_results", record, summary)
        if record.get("replay_verified") is not True:
            errors.append("task_results.jsonl must replay-verify every task")
        if not record.get("poor_cli_run_id") or not record.get("poor_cli_store_dir"):
            errors.append("task_results.jsonl must record run ids and store dirs")
        check = _verify_recorded_replay(summary_path, record)
        replay_checks.append(check)
        if not check["verified"]:
            errors.append(f"task_results replay store verification failed: {check['instance_id']}")
    prediction_ids = [str(record.get("instance_id") or "") for record in predictions]
    if len(predictions) != task_count or task_count == 0:
        errors.append("predictions.jsonl count must match task_count")
    if task_ids and prediction_ids and set(task_ids) != set(prediction_ids):
        errors.append("predictions.jsonl instance ids must match task_results.jsonl")
    return {
        "environment": _display_path(environment_path),
        "task_results": _display_path(task_results_path),
        "predictions": _display_path(predictions_path),
        "task_results_count": len(task_results),
        "predictions_count": len(predictions),
        "replay_store_checks": replay_checks,
        "errors": sorted(set(errors)),
    }


def _verify_recorded_replay(summary_path: Path, record: dict[str, Any]) -> dict[str, Any]:
    instance_id = str(record.get("instance_id") or "")
    run_id = str(record.get("poor_cli_run_id") or "")
    raw_store_dir = str(record.get("poor_cli_store_dir") or "")
    path = Path(raw_store_dir).expanduser()
    if raw_store_dir and not path.is_absolute():
        path = (summary_path.parent / path).resolve()
    payload: dict[str, Any] = {"instance_id": instance_id, "run_id": run_id, "store_dir": str(path), "verified": False}
    if not run_id or not raw_store_dir:
        payload["error"] = "missing run id or store dir"
        return payload
    if not (path / "runs.sqlite3").exists():
        payload["error"] = "missing runs.sqlite3"
        return payload
    try:
        with closing(RunStore(path)) as store:
            verification = replay_verify(store, run_id)
    except (RuntimeError, StoreError, OSError) as exc:
        payload["error"] = str(exc)
        return payload
    payload["verified"] = bool(verification.get("verified"))
    payload["trace_sha256"] = verification.get("trace_sha256", "")
    payload["network"] = verification.get("network", {})
    return payload


def _manifest_validation(summary_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    path = summary_path.parent / "run_manifest.json"
    manifest = _read_json(path)
    errors: list[str] = []
    if not manifest:
        errors.append("run_manifest.json is required")
        return {"path": _display_path(path), "errors": errors}
    docker_images = manifest.get("docker_images")
    if not isinstance(docker_images, dict) or not docker_images:
        errors.append("run_manifest docker_images is required")
    else:
        for name, image in docker_images.items():
            if not _pinned_image(str(image)):
                errors.append(f"docker image {name} must be pinned by sha256 digest")
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    if str(runtime.get("PYTHONHASHSEED") or "") == "":
        errors.append("run_manifest PYTHONHASHSEED is required")
    generation = manifest.get("generation") if isinstance(manifest.get("generation"), dict) else {}
    if _number(generation.get("temperature"), 1) != 0:
        errors.append("run_manifest temperature must be 0")
    if _number(generation.get("top_p"), 0) != 1.0:
        errors.append("run_manifest top_p must be 1.0")
    model = manifest.get("model") if isinstance(manifest.get("model"), dict) else {}
    _extend_model_manifest_errors(errors, model, summary)
    if not _hash_value(str(model.get("weight_hash") or "")):
        errors.append("run_manifest model.weight_hash must be md5:<hex> or sha256:<hex>")
    versions = manifest.get("harness_versions") if isinstance(manifest.get("harness_versions"), dict) else {}
    for key in ("swebench", "datasets", "poor_cli"):
        if not str(versions.get(key) or "").strip():
            errors.append(f"run_manifest harness_versions.{key} is required")
    return {"path": _display_path(path), "errors": sorted(set(errors))}


def _extend_model_manifest_errors(errors: list[str], model: dict[str, Any], summary: dict[str, Any]) -> None:
    source = str(model.get("source") or "")
    served = str(model.get("served") or "")
    quantization = str(model.get("quantization") or "")
    dtype = str(model.get("dtype") or "")
    context = str(model.get("context_length") or "")
    if not source:
        errors.append("run_manifest model.source is required")
    if not served:
        errors.append("run_manifest model.served is required")
    if not quantization:
        errors.append("run_manifest model.quantization is required")
    if not dtype:
        errors.append("run_manifest model.dtype is required")
    if not context or context == "0":
        errors.append("run_manifest model.context_length is required")
    if source and not all(marker in source.lower() for marker in TARGET_MODEL_MARKERS):
        errors.append("run_manifest model.source is not qwen2.5-coder-32b")
    if served and served != str(summary.get("model") or ""):
        errors.append("run_manifest model.served does not match summary model")
    if summary.get("local_model_source") and source != summary.get("local_model_source"):
        errors.append("run_manifest model.source does not match summary local_model_source")
    if summary.get("local_quantization") and quantization != summary.get("local_quantization"):
        errors.append("run_manifest model.quantization does not match summary local_quantization")
    if summary.get("local_dtype") and dtype != summary.get("local_dtype"):
        errors.append("run_manifest model.dtype does not match summary local_dtype")
    if summary.get("local_max_model_len") and context != str(summary.get("local_max_model_len")):
        errors.append("run_manifest model.context_length does not match summary local_max_model_len")


def _extend_mismatch_errors(errors: list[str], label: str, record: dict[str, Any], summary: dict[str, Any]) -> None:
    for key in ("provider", "model", "agent", "graph_mode"):
        if record.get(key) != summary.get(key):
            errors.append(f"{label} {key} does not match summary")
    for key in (
        "local_model_source",
        "local_served_model",
        "local_quantization",
        "local_dtype",
        "local_max_model_len",
        "local_tensor_parallel_size",
        "local_gpu_memory_utilization",
    ):
        if (record.get(key) or summary.get(key)) and record.get(key) != summary.get(key):
            errors.append(f"{label} {key} does not match summary")


def _target_model_markers_present(summary: dict[str, Any]) -> bool:
    source = str(summary.get("local_model_source") or "")
    model = source or str(summary.get("model") or "")
    return all(marker in model.lower() for marker in TARGET_MODEL_MARKERS)


def _is_local_endpoint(value: str) -> bool:
    return value.startswith(("http://localhost", "http://127.0.0.1", "http://[::1]"))


def _pinned_image(value: str) -> bool:
    if "@sha256:" not in value:
        return False
    digest = value.rsplit("@sha256:", 1)[-1].lower()
    return len(digest) == 64 and set(digest) <= HEX64


def _hash_value(value: str) -> bool:
    if value.startswith("sha256:"):
        digest = value.removeprefix("sha256:").lower()
        return len(digest) == 64 and set(digest) <= HEX64
    if value.startswith("md5:"):
        digest = value.removeprefix("md5:").lower()
        return len(digest) == 32 and set(digest) <= HEX64
    return False


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _display_path(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_absolute() and path.is_relative_to(ROOT) else str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench/phase3_local_benchmark.py")
    parser.add_argument("--summary", type=Path, help="Validate a local SWE-bench summary.json artifact.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload: dict[str, Any] = {"plan": benchmark_plan_payload()}
    if args.summary:
        payload["validation"] = validate_local_summary(args.summary.resolve())
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    validation = payload.get("validation")
    return 0 if not isinstance(validation, dict) or validation["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
