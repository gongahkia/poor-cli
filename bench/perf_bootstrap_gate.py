#!/usr/bin/env python3
"""bootstrap-based perf regression gate across repeated profile runs."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path
from typing import Dict, List, Sequence


DEFAULT_METRICS = (
    "quick_quit_mean_ms",
    "quick_quit_p50_ms",
    "quick_quit_stall_p95_ms",
    "quick_quit_stall_ultrafast_p95_ms",
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


def _parse_paths(raw: str) -> List[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (max(0.0, min(100.0, pct)) / 100.0) * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    w = idx - lo
    return ordered[lo] * (1.0 - w) + ordered[hi] * w


def _bootstrap_delta_distribution(
    baseline_values: Sequence[float],
    candidate_values: Sequence[float],
    *,
    samples: int,
    rng: random.Random,
) -> List[float]:
    base = list(float(v) for v in baseline_values)
    head = list(float(v) for v in candidate_values)
    if not base or not head:
        return [0.0]
    out: List[float] = []
    for _ in range(max(1, samples)):
        sampled_base = [base[rng.randrange(len(base))] for _ in range(len(base))]
        sampled_head = [head[rng.randrange(len(head))] for _ in range(len(head))]
        out.append(statistics.mean(sampled_head) - statistics.mean(sampled_base))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/perf_bootstrap_gate.py")
    parser.add_argument("--baseline-list", required=True, help="comma-separated baseline profile json paths")
    parser.add_argument("--candidate-list", required=True, help="comma-separated candidate profile json paths")
    parser.add_argument(
        "--metrics",
        default=",".join(DEFAULT_METRICS),
        help="comma-separated latency metrics (higher is worse)",
    )
    parser.add_argument("--relative-threshold", type=float, default=0.10)
    parser.add_argument("--absolute-threshold-ms", type=float, default=5.0)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report-path", default="")
    args = parser.parse_args()

    baseline_paths = _parse_paths(args.baseline_list)
    candidate_paths = _parse_paths(args.candidate_list)
    if not baseline_paths or not candidate_paths:
        raise RuntimeError("baseline/candidate path lists must be non-empty")

    baseline_payloads = [_load_json(path) for path in baseline_paths]
    candidate_payloads = [_load_json(path) for path in candidate_paths]
    metrics = [metric.strip() for metric in str(args.metrics).split(",") if metric.strip()]
    rel = max(0.0, float(args.relative_threshold))
    abs_ms = max(0.0, float(args.absolute_threshold_ms))
    confidence = max(0.50, min(0.999, float(args.confidence)))
    bootstrap_samples = max(200, int(args.bootstrap_samples))
    rng = random.Random(int(args.seed))

    failures: List[str] = []
    comparisons: List[Dict[str, float | bool | str | int]] = []
    tail_pct = (1.0 - confidence) * 100.0
    low_pct = tail_pct / 2.0
    high_pct = 100.0 - low_pct
    for metric in metrics:
        baseline_values = [_as_float(payload, metric) for payload in baseline_payloads]
        candidate_values = [_as_float(payload, metric) for payload in candidate_payloads]
        baseline_mean = statistics.mean(baseline_values) if baseline_values else 0.0
        candidate_mean = statistics.mean(candidate_values) if candidate_values else 0.0
        delta = candidate_mean - baseline_mean
        noise_floor = max(
            statistics.pstdev(baseline_values) if len(baseline_values) > 1 else 0.0,
            statistics.pstdev(candidate_values) if len(candidate_values) > 1 else 0.0,
        ) * 2.5
        allowed_delta = max(abs_ms, baseline_mean * rel, noise_floor)
        boot = _bootstrap_delta_distribution(
            baseline_values,
            candidate_values,
            samples=bootstrap_samples,
            rng=rng,
        )
        ci_low = _percentile(boot, low_pct)
        ci_high = _percentile(boot, high_pct)
        regressed = ci_low > allowed_delta
        comparisons.append(
            {
                "metric": metric,
                "baselineMeanMs": round(baseline_mean, 6),
                "candidateMeanMs": round(candidate_mean, 6),
                "deltaMeanMs": round(delta, 6),
                "deltaCiLowMs": round(ci_low, 6),
                "deltaCiHighMs": round(ci_high, 6),
                "allowedDeltaMs": round(allowed_delta, 6),
                "bootstrapSamples": int(bootstrap_samples),
                "baselineRuns": int(len(baseline_values)),
                "candidateRuns": int(len(candidate_values)),
                "regressed": bool(regressed),
            }
        )
        if regressed:
            failures.append(
                (
                    f"{metric}: delta_ci_low={ci_low:.2f}ms > allowed={allowed_delta:.2f}ms "
                    f"(base_mean={baseline_mean:.2f}, head_mean={candidate_mean:.2f})"
                )
            )

    report = {
        "baseline_profiles": baseline_paths,
        "candidate_profiles": candidate_paths,
        "metrics_checked": metrics,
        "relative_threshold": rel,
        "absolute_threshold_ms": abs_ms,
        "confidence": confidence,
        "bootstrap_samples": bootstrap_samples,
        "seed": int(args.seed),
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
            print(f"[perf-bootstrap-gate] {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
