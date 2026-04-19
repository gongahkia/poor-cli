#!/usr/bin/env python3
# ruff: noqa: E402
"""Offline model-router calibration from run history outcomes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poor_cli.model_router import (
    ModelRouter,
    RouterCalibrationSample,
    TaskComplexity,
    recommend_complexity_bias,
)
from poor_cli.run_history import RunHistoryManager


def _complexity_from_run(metadata: Dict[str, Any]) -> TaskComplexity:
    transitions = metadata.get("turnTransitions", [])
    orchestration = metadata.get("turnOrchestration", [])
    transition_count = len(transitions) if isinstance(transitions, list) else 0
    call_count = 0
    if isinstance(orchestration, list):
        for row in orchestration:
            if not isinstance(row, dict):
                continue
            call_count += max(0, int(row.get("callCount", 0) or 0))
    if transition_count <= 1 and call_count <= 0:
        return TaskComplexity.TRIVIAL
    if transition_count <= 2 and call_count <= 1:
        return TaskComplexity.SIMPLE
    if transition_count <= 4 and call_count <= 4:
        return TaskComplexity.MODERATE
    return TaskComplexity.COMPLEX


def _collect_samples(manager: RunHistoryManager, *, limit: int, provider_filter: str = "") -> Dict[str, List[RouterCalibrationSample]]:
    records = manager.list_runs(limit=max(1, int(limit)))
    provider_key = str(provider_filter or "").strip().lower()
    by_provider: Dict[str, List[RouterCalibrationSample]] = {}
    for record in records:
        provider = str(record.provider_summary.get("name", "") or "").strip().lower()
        if provider_key and provider != provider_key:
            continue
        if not provider:
            continue
        metadata = record.metadata
        complexity = _complexity_from_run(metadata if isinstance(metadata, dict) else {})
        succeeded = str(record.status or "").strip().lower() == "completed"
        user_retried = bool(metadata.get("retryOfRunId")) if isinstance(metadata, dict) else False
        cost = float(record.cost_summary.get("estimated_cost_usd", 0.0) or 0.0)
        by_provider.setdefault(provider, []).append(
            RouterCalibrationSample(
                complexity=complexity,
                success=succeeded,
                user_retried=user_retried,
                estimated_cost_usd=cost,
            )
        )
    return by_provider


def _apply_bias(complexity: TaskComplexity, bias: int) -> TaskComplexity:
    order = [TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE, TaskComplexity.MODERATE, TaskComplexity.COMPLEX]
    idx = order.index(complexity)
    next_idx = max(0, min(len(order) - 1, idx + int(bias)))
    return order[next_idx]


def _provider_recommendation(
    provider: str,
    samples: List[RouterCalibrationSample],
    *,
    failure_target: float,
    min_samples: int,
    cost_high_watermark: float,
) -> Dict[str, Any]:
    router = ModelRouter()
    table = router.get_routing_table(provider)
    bias = recommend_complexity_bias(
        samples,
        failure_target=failure_target,
        min_samples=min_samples,
        cost_high_watermark=cost_high_watermark,
    )
    complexity_stats: Dict[str, Any] = {}
    for complexity in TaskComplexity:
        rows = [sample for sample in samples if sample.complexity == complexity]
        total = len(rows)
        failures = sum(1 for row in rows if (not row.success) or row.user_retried)
        avg_cost = (sum(row.estimated_cost_usd for row in rows) / float(total)) if total else 0.0
        complexity_stats[complexity.value] = {
            "count": total,
            "failureRate": (failures / float(total)) if total else 0.0,
            "avgCostUsd": avg_cost,
            "bias": int(bias.get(complexity, 0)),
        }
    routing: Dict[str, str] = {}
    for complexity in TaskComplexity:
        target_complexity = _apply_bias(complexity, int(bias.get(complexity, 0)))
        model_name = table.get(target_complexity, table.get(complexity, ""))
        routing[complexity.value] = str(model_name or "")
    global_total = len(samples)
    global_failures = sum(1 for row in samples if (not row.success) or row.user_retried)
    return {
        "provider": provider,
        "sampleCount": global_total,
        "globalFailureRate": (global_failures / float(global_total)) if global_total else 0.0,
        "recommendedRouting": routing,
        "complexityStats": complexity_stats,
    }


def _run(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    manager = RunHistoryManager(repo_root=repo_root)
    samples = _collect_samples(
        manager,
        limit=int(args.limit),
        provider_filter=str(args.provider or ""),
    )
    providers = sorted(samples.keys())
    calibrations = [
        _provider_recommendation(
            provider,
            samples[provider],
            failure_target=float(args.failure_target),
            min_samples=int(args.min_samples),
            cost_high_watermark=float(args.cost_high_watermark_usd),
        )
        for provider in providers
    ]
    regressions: List[str] = []
    for row in calibrations:
        if float(row.get("globalFailureRate", 0.0) or 0.0) > float(args.max_global_failure_rate):
            regressions.append(
                f"{row.get('provider', '')}: globalFailureRate {float(row.get('globalFailureRate', 0.0)):.3f} > "
                f"max {float(args.max_global_failure_rate):.3f}"
            )
    return {
        "repoRoot": str(repo_root),
        "providers": calibrations,
        "regressions": regressions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/model_router_calibration.py")
    parser.add_argument("--repo-root", type=str, default=".")
    parser.add_argument("--provider", type=str, default="")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--failure-target", type=float, default=0.15)
    parser.add_argument("--min-samples", type=int, default=8)
    parser.add_argument("--cost-high-watermark-usd", type=float, default=0.01)
    parser.add_argument("--max-global-failure-rate", type=float, default=1.0)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
    payload = _run(args)
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body + "\n", encoding="utf-8")
    regressions = payload.get("regressions", [])
    if isinstance(regressions, list) and regressions:
        for item in regressions:
            print(f"[model-router-calibration] {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
