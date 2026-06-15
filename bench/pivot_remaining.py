from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from bench.phase3_acceptance import acceptance_payload as phase3_acceptance_payload
    from bench.phase3_local_benchmark import is_local_summary_candidate, target_payload, validate_local_summary
except ModuleNotFoundError:
    from phase3_acceptance import acceptance_payload as phase3_acceptance_payload
    from phase3_local_benchmark import is_local_summary_candidate, target_payload, validate_local_summary

ROOT = Path(__file__).resolve().parents[1]


def remaining_payload() -> dict[str, Any]:
    checks = {
        "phase2_fixed_swe_graph_mode": _phase2_fixed_swe_graph_mode(),
        "phase3_linux_cuda_readiness": _phase3_linux_cuda_readiness(),
        "phase3_local_mode_benchmark": _phase3_local_mode_benchmark(),
        "phase3_offline_graph_replay": _phase3_offline_graph_replay(),
        "phase3_local_gpu_screencast": _phase3_local_gpu_screencast(),
    }
    return {
        "schema_version": "poor-cli-pivot-remaining-v1",
        "complete": all(check["done"] for check in checks.values()),
        "checks": checks,
        "remaining": [name for name, check in checks.items() if not check["done"]],
    }


def _phase2_fixed_swe_graph_mode() -> dict[str, Any]:
    for summary_path in sorted((ROOT / "bench" / "swe_bench_lite" / "results").glob("*/summary.json")):
        payload = _read_json(summary_path)
        if payload.get("graph_mode") is not True or int(payload.get("task_count") or 0) < 10:
            continue
        official = payload.get("official_evaluation")
        if not isinstance(official, dict):
            continue
        results = official.get("results")
        if not isinstance(results, dict):
            continue
        total = int(results.get("total_instances") or results.get("submitted_instances") or 0)
        resolved = int(results.get("resolved_instances") or 0)
        if total >= 10:
            return {
                "done": True,
                "evidence": str(summary_path.relative_to(ROOT)),
                "resolved_instances": resolved,
                "total_instances": total,
            }
    return {
        "done": False,
        "evidence": "",
        "reason": "no checked-in fixed 10-task SWE-bench Lite graph-mode summary with official evaluation",
    }


def _phase3_linux_cuda_readiness() -> dict[str, Any]:
    path = ROOT / "bench" / "results" / "phase3-readiness.json"
    payload = _read_json(path)
    return {
        "done": bool(payload.get("ready")),
        "evidence": str(path.relative_to(ROOT)),
        "remaining": payload.get("remaining", []),
    }


def _phase3_local_mode_benchmark() -> dict[str, Any]:
    target = target_payload()
    best = {
        "pass_rate": 0.0,
        "evidence": "",
        "resolved_instances": 0,
        "total_instances": 0,
        "replay_verified_count": 0,
        "graph_mode": False,
        "target_rate": target["target_rate"],
    }
    for summary_path in sorted((ROOT / "bench" / "swe_bench_lite" / "results").glob("*/summary.json")):
        validation = validate_local_summary(summary_path.resolve())
        if not is_local_summary_candidate(validation):
            continue
        if validation["accepted"]:
            return {"done": True, **validation}
        if float(validation["pass_rate"]) > float(best["pass_rate"]):
            best = validation
    return {
        "done": False,
        "reason": "no checked-in 10-task local graph-mode SWE-bench summary meeting the Phase 3 target",
        **best,
    }


def _phase3_offline_graph_replay() -> dict[str, Any]:
    check = phase3_acceptance_payload()["checks"]["offline_graph_replay"]
    return {
        "done": bool(check["accepted"]),
        "evidence": check["evidence"],
        "missing_fragments": check["missing_fragments"],
    }


def _phase3_local_gpu_screencast() -> dict[str, Any]:
    check = phase3_acceptance_payload()["checks"]["local_gpu_screencast"]
    return {
        "done": bool(check["accepted"]),
        "evidence": check["evidence"],
        "duration_seconds": check["duration_seconds"],
        "model": check["model"],
        "video_path": check["video_path"],
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench/pivot_remaining.py")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = remaining_payload()
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if payload["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
