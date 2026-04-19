#!/usr/bin/env python3
"""Measure CLI entrypoint import/startup overhead with python -X importtime."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


SCENARIOS: Dict[str, Dict[str, Any]] = {
    "version": {
        "argv": ["--version"],
        "track_modules": ["poor_cli.__main__", "poor_cli.cli_app", "poor_cli.server.runtime"],
    },
    "help": {
        "argv": ["--help"],
        "track_modules": ["poor_cli.__main__", "poor_cli.cli_app", "poor_cli.server.runtime"],
    },
    "server_help": {
        "argv": ["server", "--help"],
        "track_modules": ["poor_cli.__main__", "poor_cli.cli_app", "poor_cli.server.runtime", "poor_cli.server.cli"],
    },
}

_IMPORT_RE = re.compile(r"^import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(.+)$")


def _percentile(values: List[float], pct: float) -> float:
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


def _parse_importtime(stderr: str, tracked_modules: List[str]) -> Dict[str, float]:
    total_cumulative_us = 0
    tracked_us: Dict[str, int] = {name: 0 for name in tracked_modules}
    for line in (stderr or "").splitlines():
        stripped = line.strip()
        match = _IMPORT_RE.match(stripped)
        if not match:
            continue
        cumulative_us = int(match.group(2))
        module_name = match.group(3).strip()
        if cumulative_us > total_cumulative_us:
            total_cumulative_us = cumulative_us
        if module_name in tracked_us and cumulative_us > tracked_us[module_name]:
            tracked_us[module_name] = cumulative_us
    payload: Dict[str, float] = {"import_total_ms": total_cumulative_us / 1000.0}
    for module_name, value in tracked_us.items():
        payload[f"module_{module_name}_ms"] = value / 1000.0
    return payload


def _run_once(python_bin: str, argv: List[str], tracked_modules: List[str]) -> Dict[str, Any]:
    cmd = [python_bin, "-X", "importtime", "-m", "poor_cli", *argv]
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    wall_ms = (time.perf_counter() - started) * 1000.0
    parsed = _parse_importtime(proc.stderr, tracked_modules)
    parsed["wall_ms"] = wall_ms
    parsed["exit_code"] = int(proc.returncode)
    parsed["stderr_lines"] = len((proc.stderr or "").splitlines())
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/import_time_profile.py")
    parser.add_argument("--python", default=sys.executable, help="python executable")
    parser.add_argument("--runs", type=int, default=5, help="runs per scenario")
    parser.add_argument("--scenarios", default="version,help,server_help", help="comma-separated scenario names")
    parser.add_argument("--output", default="", help="optional output json path")
    args = parser.parse_args()

    selected = [name.strip() for name in str(args.scenarios or "").split(",") if name.strip()]
    selected = [name for name in selected if name in SCENARIOS]
    if not selected:
        raise RuntimeError("no valid scenarios selected")

    scenario_rows: List[Dict[str, Any]] = []
    for scenario_name in selected:
        definition = SCENARIOS[scenario_name]
        argv = list(definition.get("argv", []))
        tracked_modules = list(definition.get("track_modules", []))
        run_rows = [
            _run_once(str(args.python), argv, tracked_modules)
            for _ in range(max(1, int(args.runs)))
        ]
        wall_values = [float(row.get("wall_ms", 0.0)) for row in run_rows]
        import_values = [float(row.get("import_total_ms", 0.0)) for row in run_rows]
        module_rows: Dict[str, Dict[str, float]] = {}
        for module_name in tracked_modules:
            key = f"module_{module_name}_ms"
            values = [float(row.get(key, 0.0)) for row in run_rows]
            module_rows[module_name] = {
                "p50_ms": round(_percentile(values, 50.0), 6),
                "p95_ms": round(_percentile(values, 95.0), 6),
                "mean_ms": round(statistics.mean(values), 6),
            }
        scenario_rows.append(
            {
                "scenario": scenario_name,
                "argv": argv,
                "runs": len(run_rows),
                "wall_mean_ms": round(statistics.mean(wall_values), 6),
                "wall_p50_ms": round(_percentile(wall_values, 50.0), 6),
                "wall_p95_ms": round(_percentile(wall_values, 95.0), 6),
                "import_total_mean_ms": round(statistics.mean(import_values), 6),
                "import_total_p50_ms": round(_percentile(import_values, 50.0), 6),
                "import_total_p95_ms": round(_percentile(import_values, 95.0), 6),
                "modules": module_rows,
                "exit_codes": [int(row.get("exit_code", 0)) for row in run_rows],
            }
        )

    payload = {
        "python": str(args.python),
        "runs_per_scenario": max(1, int(args.runs)),
        "scenarios": scenario_rows,
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
