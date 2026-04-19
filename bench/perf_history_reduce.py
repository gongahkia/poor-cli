#!/usr/bin/env python3
"""compute rolling median + MAD summary for quick-quit perf history."""

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
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _mad(values: List[float]) -> float:
    if not values:
        return 0.0
    median = statistics.median(values)
    return statistics.median([abs(v - median) for v in values])


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/perf_history_reduce.py")
    parser.add_argument("--input", required=True, help="trend jsonl path")
    parser.add_argument("--window", type=int, default=40, help="rolling window size")
    parser.add_argument("--metrics", default=",".join(DEFAULT_METRICS))
    parser.add_argument("--output", default="", help="optional output json path")
    args = parser.parse_args()

    rows = _read_jsonl(Path(args.input).expanduser().resolve())
    metrics = [item.strip() for item in str(args.metrics or "").split(",") if item.strip()]
    window = max(1, int(args.window))
    filtered = [row for row in rows if str(row.get("profile", "")).strip().lower() == "head"]
    recent = filtered[-window:]
    metric_rows: List[Dict[str, Any]] = []
    for metric in metrics:
        samples = [
            _as_float((row.get("metrics") or {}).get(metric))
            for row in recent
            if isinstance(row.get("metrics"), dict)
        ]
        if not samples:
            continue
        metric_rows.append(
            {
                "metric": metric,
                "count": len(samples),
                "median_ms": round(statistics.median(samples), 6),
                "mad_ms": round(_mad(samples), 6),
                "min_ms": round(min(samples), 6),
                "max_ms": round(max(samples), 6),
            }
        )

    payload = {
        "input": str(args.input),
        "window": window,
        "total_rows": len(rows),
        "head_rows": len(filtered),
        "used_rows": len(recent),
        "metrics": metric_rows,
    }
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if str(args.output or "").strip():
        out_path = Path(str(args.output)).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
