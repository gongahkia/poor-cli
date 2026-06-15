from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ANTHROPIC_SUMMARY = ROOT / "bench" / "swe_bench_lite" / "results" / "swe10-claude-20260614T105615Z" / "summary.json"
ALLOWED_PROVIDERS = {"ollama", "sglang", "vllm"}


def benchmark_plan_payload() -> dict[str, Any]:
    run_id = "swe10-local-YYYYMMDDTHHMMSSZ"
    return {
        "schema_version": "poor-cli-phase3-local-benchmark-plan-v1",
        "target": {
            "agent": "local",
            "providers": sorted(ALLOWED_PROVIDERS),
            "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "task_count": 10,
            "minimum_of_anthropic_pass_rate": 0.5,
            "requires_graph_mode": True,
            "requires_full_replay_verification": True,
        },
        "commands": {
            "setup": ("scripts/setup-linux-cuda.sh --yes --engine vllm --model Qwen/Qwen2.5-Coder-32B-Instruct"),
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
    pass_rate = resolved / total if total else 0.0
    errors = _summary_errors(summary, target, task_count, replay_verified, official, total, pass_rate)
    return {
        "accepted": not errors,
        "evidence": _display_path(summary_path),
        "errors": errors,
        "provider": summary.get("provider", ""),
        "model": summary.get("model", ""),
        "agent": summary.get("agent", ""),
        "graph_mode": bool(summary.get("graph_mode")),
        "task_count": task_count,
        "replay_verified_count": replay_verified,
        "resolved_instances": resolved,
        "total_instances": total,
        "pass_rate": pass_rate,
        "target_rate": target["target_rate"],
    }


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
    pass_rate: float,
) -> list[str]:
    errors = []
    if target["target_rate"] <= 0:
        errors.append("missing Anthropic baseline target")
    if summary.get("provider") not in ALLOWED_PROVIDERS:
        errors.append("summary provider is not local")
    if summary.get("agent") != "local":
        errors.append("summary agent is not local")
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
    if pass_rate < float(target["target_rate"]):
        errors.append("local pass rate is below 50% of Anthropic pass rate")
    return errors


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


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
