#!/usr/bin/env python3
"""repeatable startup/exit latency profile with cold/warm percentiles."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
STARTUP_PROBE = REPO_ROOT / "nvim-poor-cli" / "bench" / "startup_probe.lua"
QUICK_QUIT_PROBE = REPO_ROOT / "nvim-poor-cli" / "bench" / "quick_quit_probe.lua"


def _json_line_from_stdout(stdout: str) -> Dict[str, object]:
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"missing json payload: {stdout!r}")


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (max(0.0, min(100.0, float(pct))) / 100.0) * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    weight = idx - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def _summary(name: str, values: List[float]) -> Dict[str, float]:
    return {
        f"{name}_mean_ms": statistics.mean(values) if values else 0.0,
        f"{name}_std_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
        f"{name}_p50_ms": _percentile(values, 50.0),
        f"{name}_p95_ms": _percentile(values, 95.0),
        f"{name}_p99_ms": _percentile(values, 99.0),
    }


def _run_startup_probe(runs: int) -> Dict[str, float]:
    cmd = ["nvim", "--headless", "-u", "NONE", "-n", "-l", str(STARTUP_PROBE)]
    setup_return: List[float] = []
    setup_complete: List[float] = []
    for _ in range(max(1, runs)):
        env = dict(os.environ)
        env["POORCLI_BENCH_AUTO_START"] = "0"
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"startup probe failed: {proc.stderr}\n{proc.stdout}")
        row = _json_line_from_stdout(proc.stdout)
        setup_return.append(float(row.get("setup_return_ms", 0.0) or 0.0))
        setup_complete.append(float(row.get("setup_complete_ms", 0.0) or 0.0))

    warm_setup_return = setup_return[1:] if len(setup_return) > 1 else list(setup_return)
    warm_setup_complete = setup_complete[1:] if len(setup_complete) > 1 else list(setup_complete)

    result: Dict[str, float] = {
        "runs_startup": float(len(setup_return)),
        "cold_setup_return_ms": setup_return[0] if setup_return else 0.0,
        "cold_setup_complete_ms": setup_complete[0] if setup_complete else 0.0,
    }
    result.update(_summary("setup_return", setup_return))
    result.update(_summary("setup_complete", setup_complete))
    result.update(_summary("warm_setup_return", warm_setup_return))
    result.update(_summary("warm_setup_complete", warm_setup_complete))
    return result


def _run_quick_quit_probe(runs: int) -> Dict[str, float]:
    cmd = ["nvim", "--headless", "-u", "NONE", "-n", "-l", str(QUICK_QUIT_PROBE)]
    durations: List[float] = []
    for _ in range(max(1, runs)):
        env = dict(os.environ)
        env["POORCLI_BENCH_AUTO_START"] = "0"
        started = time.perf_counter()
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        durations.append((time.perf_counter() - started) * 1000.0)
        if proc.returncode != 0:
            raise RuntimeError(f"quick quit probe failed: {proc.stderr}\n{proc.stdout}")
    result: Dict[str, float] = {"runs_quick_quit": float(len(durations))}
    result.update(_summary("quick_quit", durations))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/startup_profile.py")
    parser.add_argument("--runs", type=int, default=30, help="probe iterations per benchmark")
    parser.add_argument("--output", type=str, default="", help="optional output json path")
    args = parser.parse_args()

    payload: Dict[str, float] = {}
    payload.update(_run_startup_probe(args.runs))
    payload.update(_run_quick_quit_probe(args.runs))
    payload["generated_at_unix"] = float(time.time())
    payload["commit"] = os.environ.get("GITHUB_SHA", "").strip()

    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
