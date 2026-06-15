from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def remaining_payload() -> dict[str, Any]:
    checks = {
        "phase2_fixed_swe_graph_mode": _phase2_fixed_swe_graph_mode(),
        "phase3_linux_cuda_readiness": _phase3_linux_cuda_readiness(),
        "phase3_local_mode_benchmark": _phase3_local_mode_benchmark(),
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
    anthropic = _read_json(ROOT / "bench" / "swe_bench_lite" / "results" / "swe10-claude-20260614T105615Z" / "summary.json")
    anthropic_results = anthropic.get("official_evaluation", {}).get("results", {})
    anthropic_total = int(anthropic_results.get("total_instances") or 0)
    anthropic_resolved = int(anthropic_results.get("resolved_instances") or 0)
    target_rate = (anthropic_resolved / anthropic_total) * 0.5 if anthropic_total else 0.0
    best = {"pass_rate": 0.0, "evidence": "", "resolved_instances": 0, "total_instances": 0}
    for summary_path in sorted((ROOT / "bench" / "swe_bench_lite" / "results").glob("*/summary.json")):
        payload = _read_json(summary_path)
        if payload.get("provider") not in {"ollama", "sglang", "vllm"}:
            continue
        results = payload.get("official_evaluation", {}).get("results", {})
        total = int(results.get("total_instances") or 0)
        resolved = int(results.get("resolved_instances") or 0)
        pass_rate = resolved / total if total else 0.0
        if pass_rate > float(best["pass_rate"]):
            best = {
                "pass_rate": pass_rate,
                "evidence": str(summary_path.relative_to(ROOT)),
                "resolved_instances": resolved,
                "total_instances": total,
            }
    return {
        "done": float(best["pass_rate"]) >= target_rate and target_rate > 0,
        "target_rate": target_rate,
        **best,
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
