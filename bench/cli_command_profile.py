#!/usr/bin/env python3
"""Profile cold command latency for selected CLI surfaces."""

from __future__ import annotations

import argparse
import json
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_COMMANDS = "--version;--help;provider list;trust status;config list"


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
    weight = idx - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def _parse_commands(raw: str) -> List[List[str]]:
    commands: List[List[str]] = []
    for chunk in str(raw or "").split(";"):
        text = str(chunk or "").strip()
        if not text:
            continue
        argv = shlex.split(text)
        if argv:
            commands.append(argv)
    return commands


def _run_once(python_bin: str, argv: List[str]) -> Dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(
        [python_bin, "-m", "poor_cli", *argv],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    wall_ms = (time.perf_counter() - started) * 1000.0
    return {
        "wall_ms": wall_ms,
        "exit_code": int(proc.returncode),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/cli_command_profile.py")
    parser.add_argument("--python", default=sys.executable, help="python executable")
    parser.add_argument("--runs", type=int, default=5, help="runs per command")
    parser.add_argument(
        "--commands",
        default=DEFAULT_COMMANDS,
        help="semicolon-separated commands (each parsed with shlex)",
    )
    parser.add_argument("--output", default="", help="optional output json path")
    args = parser.parse_args()

    runs = max(1, int(args.runs))
    commands = _parse_commands(str(args.commands or ""))
    if not commands:
        raise RuntimeError("no commands selected")

    rows: List[Dict[str, Any]] = []
    for argv in commands:
        run_rows = [_run_once(str(args.python), argv) for _ in range(runs)]
        values = [float(row.get("wall_ms", 0.0)) for row in run_rows]
        exit_codes = [int(row.get("exit_code", 0)) for row in run_rows]
        rows.append(
            {
                "command": " ".join(argv),
                "argv": list(argv),
                "runs": runs,
                "wall_mean_ms": round(statistics.mean(values), 6),
                "wall_p50_ms": round(_percentile(values, 50.0), 6),
                "wall_p95_ms": round(_percentile(values, 95.0), 6),
                "exit_codes": exit_codes,
                "nonzero_exit_count": int(sum(1 for code in exit_codes if code != 0)),
            }
        )

    payload = {
        "python": str(args.python),
        "runs_per_command": runs,
        "commands": rows,
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
