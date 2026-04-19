#!/usr/bin/env python3
"""reduce multiple startup-profile runs into a single median+mad profile."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List


def _load_json(path: str) -> Dict[str, float]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected object at {path}")
    return payload


def _parse_paths(raw: str) -> List[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _mad(values: List[float]) -> float:
    if not values:
        return 0.0
    median = statistics.median(values)
    return statistics.median([abs(v - median) for v in values])


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/perf_profile_reduce.py")
    parser.add_argument("--inputs", required=True, help="comma-separated startup profile json paths")
    parser.add_argument("--report-path", default="", help="optional output path")
    args = parser.parse_args()

    paths = _parse_paths(args.inputs)
    if not paths:
        raise RuntimeError("inputs must not be empty")
    rows = [_load_json(path) for path in paths]
    numeric_keys = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if isinstance(value, (int, float))
        }
    )
    reduced: Dict[str, float | int | str | List[str]] = {
        "inputs": paths,
        "input_count": len(paths),
    }
    for key in numeric_keys:
        values = [float(row.get(key, 0.0) or 0.0) for row in rows]
        reduced[key] = float(statistics.median(values))
        reduced[f"{key}_mad"] = float(_mad(values))

    body = json.dumps(reduced, sort_keys=True)
    print(body)
    if str(args.report_path or "").strip():
        out_path = Path(str(args.report_path)).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
