#!/usr/bin/env python3
"""Build poor-cli benchmark matrix and cost-per-pass reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "evaluation_tasks.json"


def evaluation_fixture_payload(path: Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or len(tasks) < 6:
        raise RuntimeError("evaluation fixture must contain at least six tasks")
    categories = {str(task.get("category") or "") for task in tasks if isinstance(task, dict)}
    required = {"simple_edit", "multi_file_refactor", "bug_fix", "ambiguous_design", "graph_lookup", "web_research"}
    if not required <= categories:
        raise RuntimeError(f"evaluation fixture missing categories: {sorted(required - categories)}")
    return payload


def reduce_report(rows: list[dict[str, Any]], *, task_set: str = "poor-cli-evaluation") -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_mode.setdefault(str(row.get("mode") or "unknown"), []).append(row)
    modes = {}
    for mode, mode_rows in sorted(by_mode.items()):
        passed = sum(1 for row in mode_rows if bool(row.get("passed")))
        durations = sorted(float(row.get("duration_seconds") or 0.0) for row in mode_rows)
        costs = [float(row.get("cost_usd") or 0.0) for row in mode_rows]
        failures: dict[str, int] = {}
        for row in mode_rows:
            if bool(row.get("passed")):
                continue
            category = str(row.get("failure_category") or "unknown")
            failures[category] = failures.get(category, 0) + 1
        modes[mode] = {
            "tasks": len(mode_rows),
            "passed": passed,
            "pass_rate": round(passed / len(mode_rows), 4) if mode_rows else 0.0,
            "total_cost_usd": round(sum(costs), 6),
            "mean_cost_usd": round(sum(costs) / len(costs), 6) if costs else 0.0,
            "mean_time_seconds": round(sum(durations) / len(durations), 3) if durations else 0.0,
            "p95_time_seconds": round(_p95(durations), 3),
            "cost_per_passed_task_usd": round(sum(costs) / passed, 6) if passed else None,
            "failure_categories": failures,
        }
    return {"schema_version": "poor-cli-benchmark-report-v1", "task_set": task_set, "modes": modes}


def swe_smoke_audit(root: Path) -> dict[str, Any]:
    summaries = sorted((root / "bench" / "swe_bench_lite" / "results").glob("smoke-*/summary.json"))
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in summaries]
    valid = [
        row
        for row in rows
        if int(row.get("task_count") or 0) >= 1
        and "mean_cost_usd" in row
        and "mean_wall_time_seconds" in row
        and int(row.get("replay_verified_count") or 0) >= 1
    ]
    return {
        "schema_version": "poor-cli-swe-smoke-audit-v1",
        "accepted": bool(valid),
        "summary_count": len(rows),
        "accepted_summary_count": len(valid),
    }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, int(round((len(values) - 1) * 0.95)))
    return values[index]


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/harness_report.py")
    parser.add_argument("--rows", help="JSON file containing benchmark rows")
    parser.add_argument("--output", help="optional report path")
    parser.add_argument("--audit-swe-smoke", action="store_true")
    args = parser.parse_args()
    if args.audit_swe_smoke:
        payload = swe_smoke_audit(Path.cwd())
    else:
        data = json.loads(Path(args.rows).read_text(encoding="utf-8")) if args.rows else {"rows": []}
        rows = data.get("rows") if isinstance(data, dict) else []
        payload = reduce_report(rows if isinstance(rows, list) else [])
    body = json.dumps(payload, indent=2, sort_keys=True)
    print(body)
    if args.output:
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    return 0 if not args.audit_swe_smoke or payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
