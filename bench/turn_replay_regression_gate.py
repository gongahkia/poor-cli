#!/usr/bin/env python3
# ruff: noqa: E402
"""Deterministic turn replay regression gate for harness planner decisions."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.harness_quality_gate import DEFAULT_FIXTURE, _run_suite


def _suite_namespace(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        fixture=str(args.fixture),
        mode=str(args.mode),
        max_autonomous_calls=int(args.max_autonomous_calls),
        min_success_rate=float(args.min_success_rate),
        max_avg_tool_calls=float(args.max_avg_tool_calls),
        min_avg_tool_precision=float(args.min_avg_tool_precision),
        min_avg_tool_recall=float(args.min_avg_tool_recall),
        max_avg_extra_calls=float(args.max_avg_extra_calls),
        max_p95_turn_latency_ms=float(args.max_p95_turn_latency_ms),
        max_total_cost_usd=float(args.max_total_cost_usd),
    )


def _row_index(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        return {}
    indexed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "") or "").strip()
        if not name:
            continue
        indexed[name] = row
    return indexed


def _calc_drift(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    baseline_rows = _row_index(baseline)
    candidate_rows = _row_index(candidate)
    scenario_names = sorted(set(baseline_rows.keys()) | set(candidate_rows.keys()))
    decision_drifts = 0
    completion_drifts = 0
    details: List[Dict[str, Any]] = []

    for name in scenario_names:
        base_row = baseline_rows.get(name, {})
        cand_row = candidate_rows.get(name, {})
        base_tools = list(base_row.get("calledTools", [])) if isinstance(base_row, dict) else []
        cand_tools = list(cand_row.get("calledTools", [])) if isinstance(cand_row, dict) else []
        base_reason = str(base_row.get("reason", "") or "") if isinstance(base_row, dict) else ""
        cand_reason = str(cand_row.get("reason", "") or "") if isinstance(cand_row, dict) else ""
        base_success = bool(base_row.get("success")) if isinstance(base_row, dict) else False
        cand_success = bool(cand_row.get("success")) if isinstance(cand_row, dict) else False
        decision_diff = base_tools != cand_tools
        completion_diff = (base_reason != cand_reason) or (base_success != cand_success)
        if decision_diff:
            decision_drifts += 1
        if completion_diff:
            completion_drifts += 1
        details.append(
            {
                "name": name,
                "decisionDrift": decision_diff,
                "completionDrift": completion_diff,
                "baselineTools": base_tools,
                "candidateTools": cand_tools,
                "baselineReason": base_reason,
                "candidateReason": cand_reason,
                "baselineSuccess": base_success,
                "candidateSuccess": cand_success,
            }
        )

    denominator = float(len(scenario_names) or 1)
    baseline_cost = float(baseline.get("estimatedCostUsdTotal", 0.0) or 0.0)
    candidate_cost = float(candidate.get("estimatedCostUsdTotal", 0.0) or 0.0)
    baseline_latency = float(baseline.get("p95TurnLatencyMs", 0.0) or 0.0)
    candidate_latency = float(candidate.get("p95TurnLatencyMs", 0.0) or 0.0)
    return {
        "scenarioCount": len(scenario_names),
        "decisionDriftCount": decision_drifts,
        "decisionDriftRate": decision_drifts / denominator,
        "completionReasonDriftCount": completion_drifts,
        "completionReasonDriftRate": completion_drifts / denominator,
        "costDeltaUsd": candidate_cost - baseline_cost,
        "costDeltaAbsUsd": abs(candidate_cost - baseline_cost),
        "latencyDeltaMs": candidate_latency - baseline_latency,
        "latencyDeltaAbsMs": abs(candidate_latency - baseline_latency),
        "rows": details,
    }


def _load_baseline(path: str) -> Dict[str, Any]:
    text = Path(path).expanduser().resolve().read_text(encoding="utf-8")
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else {}


def _run(args: argparse.Namespace) -> Dict[str, Any]:
    suite_args = _suite_namespace(args)
    candidate = asyncio.run(_run_suite(suite_args))
    baseline: Dict[str, Any]
    baseline_path = str(args.baseline_report or "").strip()
    if baseline_path:
        baseline = _load_baseline(baseline_path)
    else:
        baseline = asyncio.run(_run_suite(suite_args))

    drift = _calc_drift(baseline, candidate)
    regressions: List[str] = []
    if drift["decisionDriftRate"] > float(args.max_decision_drift_rate):
        regressions.append(
            f"decisionDriftRate {drift['decisionDriftRate']:.3f} > max {float(args.max_decision_drift_rate):.3f}"
        )
    if drift["completionReasonDriftRate"] > float(args.max_completion_reason_drift_rate):
        regressions.append(
            "completionReasonDriftRate "
            f"{drift['completionReasonDriftRate']:.3f} > max {float(args.max_completion_reason_drift_rate):.3f}"
        )
    if drift["latencyDeltaAbsMs"] > float(args.max_latency_delta_ms):
        regressions.append(
            f"latencyDeltaAbsMs {drift['latencyDeltaAbsMs']:.3f} > max {float(args.max_latency_delta_ms):.3f}"
        )
    if drift["costDeltaAbsUsd"] > float(args.max_cost_delta_usd):
        regressions.append(
            f"costDeltaAbsUsd {drift['costDeltaAbsUsd']:.6f} > max {float(args.max_cost_delta_usd):.6f}"
        )
    payload = {
        "mode": str(args.mode),
        "baselineSource": baseline_path or "fresh_replay",
        "baseline": baseline,
        "candidate": candidate,
        "comparison": drift,
        "regressions": regressions,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/turn_replay_regression_gate.py")
    parser.add_argument("--fixture", type=str, default=str(DEFAULT_FIXTURE))
    parser.add_argument("--mode", type=str, default="autonomous", choices=("scripted", "autonomous"))
    parser.add_argument("--max-autonomous-calls", type=int, default=2)
    parser.add_argument("--min-success-rate", type=float, default=1.0)
    parser.add_argument("--max-avg-tool-calls", type=float, default=3.0)
    parser.add_argument("--min-avg-tool-precision", type=float, default=0.5)
    parser.add_argument("--min-avg-tool-recall", type=float, default=1.0)
    parser.add_argument("--max-avg-extra-calls", type=float, default=2.0)
    parser.add_argument("--max-p95-turn-latency-ms", type=float, default=1200.0)
    parser.add_argument("--max-total-cost-usd", type=float, default=0.05)
    parser.add_argument("--baseline-report", type=str, default="")
    parser.add_argument("--max-decision-drift-rate", type=float, default=0.0)
    parser.add_argument("--max-completion-reason-drift-rate", type=float, default=0.0)
    parser.add_argument("--max-latency-delta-ms", type=float, default=400.0)
    parser.add_argument("--max-cost-delta-usd", type=float, default=0.05)
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
            print(f"[turn-replay-gate] {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
