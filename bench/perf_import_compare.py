#!/usr/bin/env python3
"""Compare import-time profile reports for regression checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_METRICS = ("wall_p50_ms", "import_total_p50_ms")


def _load_json(path: str) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected object at {path}")
    return payload


def _scenario_map(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in scenarios:
        if not isinstance(row, dict):
            continue
        name = str(row.get("scenario", "")).strip()
        if name:
            out[name] = row
    return out


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/perf_import_compare.py")
    parser.add_argument("--baseline", required=True, help="baseline import profile json")
    parser.add_argument("--candidate", required=True, help="candidate import profile json")
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS), help="comma-separated scenario metrics")
    parser.add_argument("--relative-threshold", type=float, default=0.15)
    parser.add_argument("--absolute-threshold-ms", type=float, default=20.0)
    parser.add_argument("--report-path", default="", help="optional output path")
    args = parser.parse_args()

    baseline = _load_json(args.baseline)
    candidate = _load_json(args.candidate)
    baseline_scenarios = _scenario_map(baseline)
    candidate_scenarios = _scenario_map(candidate)
    metrics = [item.strip() for item in str(args.metrics or "").split(",") if item.strip()]
    rel = max(0.0, float(args.relative_threshold))
    abs_ms = max(0.0, float(args.absolute_threshold_ms))

    failures: List[str] = []
    comparisons: List[Dict[str, Any]] = []
    common = sorted(set(baseline_scenarios.keys()) & set(candidate_scenarios.keys()))
    for scenario in common:
        base_row = baseline_scenarios[scenario]
        head_row = candidate_scenarios[scenario]
        for metric in metrics:
            base_value = float(base_row.get(metric, 0.0) or 0.0)
            head_value = float(head_row.get(metric, 0.0) or 0.0)
            delta = head_value - base_value
            allowed = max(abs_ms, base_value * rel)
            regressed = delta > allowed
            comparisons.append(
                {
                    "scenario": scenario,
                    "metric": metric,
                    "baselineMs": round(base_value, 6),
                    "candidateMs": round(head_value, 6),
                    "deltaMs": round(delta, 6),
                    "allowedDeltaMs": round(allowed, 6),
                    "regressed": bool(regressed),
                }
            )
            if regressed:
                failures.append(
                    f"{scenario}.{metric}: delta={delta:.2f}ms > allowed={allowed:.2f}ms (base={base_value:.2f}, head={head_value:.2f})"
                )

    payload = {
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "metrics_checked": metrics,
        "relative_threshold": rel,
        "absolute_threshold_ms": abs_ms,
        "comparisons": comparisons,
        "regressions": failures,
    }
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if str(args.report_path or "").strip():
        out_path = Path(str(args.report_path)).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body + "\n", encoding="utf-8")
    if failures:
        for line in failures:
            print(f"[perf-import-compare] {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
