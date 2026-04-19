#!/usr/bin/env python3
"""Burn-in analytics for harness gate metrics."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _parse_iso(ts: str) -> Optional[datetime]:
    text = str(ts or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((max(0.0, min(100.0, pct)) / 100.0) * (len(ordered) - 1)))
    return float(ordered[idx])


def _mad(values: List[float]) -> float:
    if not values:
        return 0.0
    med = statistics.median(values)
    deviations = [abs(value - med) for value in values]
    return float(statistics.median(deviations))


def _load_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _metric_defs() -> List[Tuple[str, str, str]]:
    return [
        ("harness_quality", "taskSuccessRate", "min"),
        ("harness_quality", "avgToolPrecision", "min"),
        ("harness_quality", "avgToolRecall", "min"),
        ("harness_quality", "avgToolCalls", "max"),
        ("harness_quality", "avgExtraCalls", "max"),
        ("harness_quality", "p95TurnLatencyMs", "max"),
        ("turn_replay", "decisionDriftRate", "max"),
        ("turn_replay", "completionReasonDriftRate", "max"),
        ("turn_replay", "latencyDeltaAbsMs", "max"),
        ("turn_replay", "costDeltaAbsUsd", "max"),
        ("failure_matrix", "recoverySuccessRate", "min"),
        ("failure_matrix", "stuckCount", "max"),
        ("failure_matrix", "meanRecoveryLatencyMs", "max"),
        ("budget_retuning", "maxBudgetDeltaRatio", "max"),
    ]


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {
            "count": 0.0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "p05": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "mad": 0.0,
        }
    return {
        "count": float(len(values)),
        "min": min(values),
        "max": max(values),
        "mean": float(statistics.mean(values)),
        "p05": _percentile(values, 5.0),
        "p50": _percentile(values, 50.0),
        "p95": _percentile(values, 95.0),
        "mad": _mad(values),
    }


def _recommend_bound(direction: str, stats: Dict[str, float]) -> float:
    mad = float(stats.get("mad", 0.0) or 0.0)
    if direction == "min":
        return max(0.0, float(stats.get("p05", 0.0) or 0.0) - (2.0 * mad))
    return float(stats.get("p95", 0.0) or 0.0) + (2.0 * mad)


def _build_markdown(summary: Dict[str, Any]) -> str:
    rows = summary.get("metrics", [])
    lines = [
        "### Harness Gate Burn-in",
        "",
        "| Gate | Metric | Direction | Samples | Mean | P95 | MAD | Recommended |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {gate} | {metric} | {direction} | {samples} | {mean:.4f} | {p95:.4f} | {mad:.4f} | {recommended:.4f} |".format(
                gate=str(row.get("gate", "")),
                metric=str(row.get("metric", "")),
                direction=str(row.get("direction", "")),
                samples=int(row.get("samples", 0) or 0),
                mean=float(row.get("mean", 0.0) or 0.0),
                p95=float(row.get("p95", 0.0) or 0.0),
                mad=float(row.get("mad", 0.0) or 0.0),
                recommended=float(row.get("recommended", 0.0) or 0.0),
            )
        )
    lines.append("")
    lines.append(
        "Ready to tighten: **{ready}** (spanDays={span:.2f}, minSamplesPerMetric={min_samples})".format(
            ready="yes" if bool(summary.get("readyToTighten")) else "no",
            span=float(summary.get("windowSpanDays", 0.0) or 0.0),
            min_samples=int(summary.get("minSamplesPerMetric", 0) or 0),
        )
    )
    lines.append("")
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> Dict[str, Any]:
    input_path = Path(args.input).expanduser().resolve()
    rows = _load_rows(input_path)
    if not rows:
        return {
            "input": str(input_path),
            "totalRows": 0,
            "windowRows": 0,
            "windowSpanDays": 0.0,
            "minSamplesPerMetric": int(args.min_samples_per_metric),
            "readyToTighten": False,
            "metrics": [],
        }

    parsed_rows: List[Tuple[datetime, Dict[str, Any]]] = []
    for row in rows:
        ts = _parse_iso(row.get("at", ""))
        if ts is None:
            continue
        parsed_rows.append((ts, row))
    if not parsed_rows:
        return {
            "input": str(input_path),
            "totalRows": len(rows),
            "windowRows": 0,
            "windowSpanDays": 0.0,
            "minSamplesPerMetric": int(args.min_samples_per_metric),
            "readyToTighten": False,
            "metrics": [],
        }

    parsed_rows.sort(key=lambda item: item[0])
    newest = parsed_rows[-1][0]
    cutoff = newest - timedelta(days=max(1, int(args.window_days)))
    windowed = [(ts, row) for ts, row in parsed_rows if ts >= cutoff]
    oldest = windowed[0][0] if windowed else newest
    span_days = max(0.0, (newest - oldest).total_seconds() / 86400.0)

    metric_rows: List[Dict[str, Any]] = []
    for gate, metric, direction in _metric_defs():
        values: List[float] = []
        for _ts, row in windowed:
            if str(row.get("gate", "")) != gate:
                continue
            metrics = row.get("metrics", {})
            if not isinstance(metrics, dict):
                continue
            try:
                values.append(float(metrics.get(metric, 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
        summary = _stats(values)
        metric_rows.append(
            {
                "gate": gate,
                "metric": metric,
                "direction": direction,
                "samples": int(summary["count"]),
                "mean": summary["mean"],
                "p95": summary["p95"],
                "mad": summary["mad"],
                "recommended": _recommend_bound(direction, summary),
            }
        )

    min_samples = max(1, int(args.min_samples_per_metric))
    ready = span_days >= float(args.window_days) and all(
        int(row.get("samples", 0) or 0) >= min_samples for row in metric_rows
    )
    return {
        "input": str(input_path),
        "totalRows": len(rows),
        "windowRows": len(windowed),
        "windowSpanDays": span_days,
        "windowDays": int(args.window_days),
        "minSamplesPerMetric": min_samples,
        "readyToTighten": bool(ready),
        "metrics": metric_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/harness_gate_burnin.py")
    parser.add_argument("--input", type=str, default="bench-trend-history/harness-gates-history.jsonl")
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument("--min-samples-per-metric", type=int, default=10)
    parser.add_argument("--output-json", type=str, default="")
    parser.add_argument("--output-markdown", type=str, default="")
    args = parser.parse_args()
    payload = _run(args)
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output_json:
        out_json = Path(args.output_json).expanduser().resolve()
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(body + "\n", encoding="utf-8")
    markdown = _build_markdown(payload)
    if args.output_markdown:
        out_md = Path(args.output_markdown).expanduser().resolve()
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(markdown + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
