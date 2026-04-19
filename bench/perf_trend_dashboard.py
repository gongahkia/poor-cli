#!/usr/bin/env python3
"""build compact perf trend dashboard from jsonl history."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_METRICS = (
    "quick_quit_mean_ms",
    "quick_quit_p50_ms",
    "quick_quit_stall_p95_ms",
    "quick_quit_stall_ultrafast_p95_ms",
)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _mad(values: List[float]) -> float:
    if not values:
        return 0.0
    median = statistics.median(values)
    return statistics.median([abs(v - median) for v in values])


def _fmt(value: float) -> str:
    if value > 0:
        return f"+{value:.2f}"
    return f"{value:.2f}"


def _write(path: str, body: str) -> None:
    out_path = Path(path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/perf_trend_dashboard.py")
    parser.add_argument("--input", required=True, help="perf trend jsonl path")
    parser.add_argument("--window", type=int, default=40, help="number of head entries to use")
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS), help="comma-separated metrics")
    parser.add_argument("--output-json", default="", help="optional output json")
    parser.add_argument("--output-markdown", default="", help="optional output markdown")
    args = parser.parse_args()

    rows = _read_jsonl(Path(args.input).expanduser().resolve())
    head_rows = [row for row in rows if str(row.get("profile", "")).strip().lower() == "head"]
    window = max(1, int(args.window))
    recent = head_rows[-window:]
    metrics = [item.strip() for item in str(args.metrics or "").split(",") if item.strip()]

    metric_rows: List[Dict[str, Any]] = []
    for metric in metrics:
        samples = [
            _as_float((row.get("metrics") or {}).get(metric))
            for row in recent
            if isinstance(row.get("metrics"), dict) and metric in (row.get("metrics") or {})
        ]
        if not samples:
            continue
        latest = samples[-1]
        previous = samples[-2] if len(samples) >= 2 else latest
        delta = latest - previous
        median = statistics.median(samples)
        mad = _mad(samples)
        drift = abs(latest - median) > max(5.0, mad * 3.0)
        metric_rows.append(
            {
                "metric": metric,
                "count": len(samples),
                "latest_ms": round(latest, 6),
                "previous_ms": round(previous, 6),
                "delta_ms": round(delta, 6),
                "median_ms": round(median, 6),
                "mad_ms": round(mad, 6),
                "min_ms": round(min(samples), 6),
                "max_ms": round(max(samples), 6),
                "status": "drift" if drift else "stable",
            }
        )

    payload = {
        "input": str(args.input),
        "window": window,
        "total_rows": len(rows),
        "head_rows": len(head_rows),
        "used_rows": len(recent),
        "metrics": metric_rows,
    }
    encoded = json.dumps(payload, sort_keys=True)
    print(encoded)
    if str(args.output_json or "").strip():
        _write(str(args.output_json), encoded + "\n")

    if str(args.output_markdown or "").strip():
        lines = [
            "Window: {window} | Head rows: {head_rows} | Used: {used_rows}".format(
                window=window,
                head_rows=len(head_rows),
                used_rows=len(recent),
            ),
            "",
        ]
        if metric_rows:
            lines.append("| Metric | Latest (ms) | Prev (ms) | Delta (ms) | Median (ms) | MAD (ms) | Status |")
            lines.append("|---|---:|---:|---:|---:|---:|---|")
            for row in metric_rows:
                lines.append(
                    "| {metric} | {latest:.2f} | {previous:.2f} | {delta} | {median:.2f} | {mad:.2f} | {status} |".format(
                        metric=row["metric"],
                        latest=float(row["latest_ms"]),
                        previous=float(row["previous_ms"]),
                        delta=_fmt(float(row["delta_ms"])),
                        median=float(row["median_ms"]),
                        mad=float(row["mad_ms"]),
                        status=str(row["status"]).upper(),
                    )
                )
        else:
            lines.append("No head trend samples found.")
        _write(str(args.output_markdown), "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
