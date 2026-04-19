#!/usr/bin/env python3
"""Offline token-budget retuning gate driven by budget_logs history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from poor_cli.budget_retuning import load_latest_tuning, run_retuning
from poor_cli.thinking_budget import TASK_TYPES


def _budget_delta_ratios(current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, float]:
    current_budgets = current.get("budgets", {})
    previous_budgets = previous.get("budgets", {})
    ratios: Dict[str, float] = {}
    for task_type in TASK_TYPES:
        cur = max(0, int(current_budgets.get(task_type, 0) or 0))
        prev = max(0, int(previous_budgets.get(task_type, 0) or 0))
        if prev <= 0:
            ratios[task_type] = 0.0
            continue
        ratios[task_type] = abs(float(cur - prev)) / float(prev)
    return ratios


def _run(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    base_dir = repo_root / ".poor-cli"
    prior = load_latest_tuning(base_dir) or {}
    retune = run_retuning(base_dir)
    latest = load_latest_tuning(base_dir) or {}
    delta_ratios = _budget_delta_ratios(latest, prior if isinstance(prior, dict) else {})
    max_delta = max(delta_ratios.values()) if delta_ratios else 0.0
    records = int(retune.get("records", 0) or 0)
    savings_pct = float(retune.get("savings_pct", 0.0) or 0.0)
    regressions: List[str] = []
    if records < int(args.min_records):
        regressions.append(f"records {records} < min {int(args.min_records)}")
    if max_delta > float(args.max_budget_delta_ratio):
        regressions.append(f"maxBudgetDeltaRatio {max_delta:.3f} > max {float(args.max_budget_delta_ratio):.3f}")
    if savings_pct < float(args.min_estimated_savings_pct):
        regressions.append(
            f"estimatedSavingsPct {savings_pct:.2f} < min {float(args.min_estimated_savings_pct):.2f}"
        )
    return {
        "repoRoot": str(repo_root),
        "retuning": retune,
        "latestTuning": latest,
        "priorTuning": prior,
        "budgetDeltaRatios": delta_ratios,
        "maxBudgetDeltaRatio": max_delta,
        "regressions": regressions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/token_budget_retuning_gate.py")
    parser.add_argument("--repo-root", type=str, default=".")
    parser.add_argument("--min-records", type=int, default=0)
    parser.add_argument("--max-budget-delta-ratio", type=float, default=0.8)
    parser.add_argument("--min-estimated-savings-pct", type=float, default=-100.0)
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
            print(f"[token-budget-retuning] {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
