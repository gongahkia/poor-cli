#!/usr/bin/env python3
"""compare baseline/head perf profiles with abs+relative regression guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


DEFAULT_METRICS = (
    "first_tick_mean_ms",
    "first_tick_p95_ms",
    "warm_setup_return_p95_ms",
    "warm_setup_return_p99_ms",
    "warm_setup_complete_p95_ms",
    "warm_setup_complete_p99_ms",
    "quick_quit_mean_ms",
    "quick_quit_p50_ms",
)


def _load_json(path: str) -> Dict[str, float]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected object at {path}")
    return payload


def _as_float(payload: Dict[str, float], key: str) -> float:
    value = payload.get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _metric_prefix(metric: str) -> str:
    for suffix in ("_mean_ms", "_p50_ms", "_p95_ms", "_p99_ms"):
        if metric.endswith(suffix):
            return metric[: -len(suffix)]
    return metric


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/perf_compare.py")
    parser.add_argument("--baseline", required=True, help="baseline profile json path")
    parser.add_argument("--candidate", required=True, help="candidate profile json path")
    parser.add_argument(
        "--metrics",
        default=",".join(DEFAULT_METRICS),
        help="comma-separated latency metrics (higher is worse)",
    )
    parser.add_argument(
        "--relative-threshold",
        type=float,
        default=0.15,
        help="relative regression threshold (fractional, default 0.15 = 15%%)",
    )
    parser.add_argument(
        "--absolute-threshold-ms",
        type=float,
        default=8.0,
        help="minimum absolute regression threshold in ms",
    )
    parser.add_argument(
        "--report-path",
        default="",
        help="optional output path for machine-readable comparison report",
    )
    args = parser.parse_args()

    baseline = _load_json(args.baseline)
    candidate = _load_json(args.candidate)
    metrics = [metric.strip() for metric in str(args.metrics).split(",") if metric.strip()]
    rel = max(0.0, float(args.relative_threshold))
    abs_ms = max(0.0, float(args.absolute_threshold_ms))

    failures: List[str] = []
    comparisons: List[Dict[str, float | bool | str]] = []
    for metric in metrics:
        base_value = _as_float(baseline, metric)
        candidate_value = _as_float(candidate, metric)
        prefix = _metric_prefix(metric)
        std_key = f"{prefix}_std_ms"
        base_std = _as_float(baseline, std_key)
        candidate_std = _as_float(candidate, std_key)
        noise_floor = max(base_std, candidate_std) * 2.5
        allowed_delta = max(abs_ms, base_value * rel, noise_floor)
        delta = candidate_value - base_value
        regressed = delta > allowed_delta
        comparisons.append(
            {
                "metric": metric,
                "baselineMs": round(base_value, 6),
                "candidateMs": round(candidate_value, 6),
                "deltaMs": round(delta, 6),
                "allowedDeltaMs": round(allowed_delta, 6),
                "regressed": bool(regressed),
            }
        )
        if regressed:
            failures.append(
                (
                    f"{metric}: base={base_value:.2f}ms head={candidate_value:.2f}ms "
                    f"delta={delta:.2f}ms > allowed={allowed_delta:.2f}ms"
                )
            )

    report = {
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "metrics_checked": metrics,
        "relative_threshold": rel,
        "absolute_threshold_ms": abs_ms,
        "regressions": failures,
        "comparisons": comparisons,
    }
    encoded = json.dumps(report, sort_keys=True)
    print(encoded)
    if str(args.report_path or "").strip():
        out_path = Path(str(args.report_path)).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(encoded + "\n", encoding="utf-8")
    if failures:
        for line in failures:
            print(f"[perf-compare] {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
