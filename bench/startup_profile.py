#!/usr/bin/env python3
"""repeatable CLI startup/exit latency profile with cold/warm percentiles."""

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
DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "workloads.json"


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


def _load_startup_fixture(path: str) -> Dict[str, object]:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.exists():
        return {}
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    startup_payload = payload.get("startup_profile", {})
    return startup_payload if isinstance(startup_payload, dict) else {}


def _probe_env(extra_env: Dict[str, str], seed: int, run_idx: int, *, ultra_fast: bool | None = None) -> Dict[str, str]:
    env = dict(os.environ)
    for key, value in extra_env.items():
        env[str(key)] = str(value)
    env["POORCLI_BENCH_SEED"] = str(seed)
    env["POORCLI_BENCH_RUN_INDEX"] = str(run_idx)
    if ultra_fast is not None:
        env["POORCLI_BENCH_EXIT_ULTRA_FAST"] = "1" if ultra_fast else "0"
    return env


def _run_cli_command(cmd: List[str], runs: int, *, startup_env: Dict[str, str], seed: int, metric: str) -> Dict[str, float]:
    durations: List[float] = []
    for idx in range(max(1, runs)):
        env = _probe_env(startup_env, seed, idx)
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
            raise RuntimeError(f"{metric} probe failed: {proc.stderr}\n{proc.stdout}")
    result: Dict[str, float] = {f"runs_{metric}": float(len(durations))}
    result.update(_summary(metric, durations))
    return result


def _run_startup_probe(runs: int, *, startup_env: Dict[str, str], seed: int) -> Dict[str, float]:
    cmd = [sys.executable, "-m", "poor_cli", "help"]
    setup_return: List[float] = []
    setup_complete: List[float] = []
    first_tick: List[float] = []
    for idx in range(max(1, runs)):
        env = _probe_env(startup_env, seed, idx)
        started = time.perf_counter()
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
        elapsed = (time.perf_counter() - started) * 1000.0
        setup_return.append(elapsed)
        setup_complete.append(elapsed)
        first_tick.append(elapsed)

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
    result.update(_summary("first_tick", first_tick))
    return result


def _run_quick_quit_probe(runs: int, *, startup_env: Dict[str, str], seed: int) -> Dict[str, float]:
    return _run_cli_command(
        [sys.executable, "-m", "poor_cli", "--version"],
        runs,
        startup_env=startup_env,
        seed=seed,
        metric="quick_quit",
    )


def _run_quick_quit_stall_probe(
    runs: int,
    *,
    startup_env: Dict[str, str],
    seed: int,
    ultra_fast: bool = False,
) -> Dict[str, float]:
    metric = "quick_quit_stall_ultrafast" if ultra_fast else "quick_quit_stall"
    return _run_cli_command(
        [sys.executable, "-m", "poor_cli", "help"],
        runs,
        startup_env=startup_env,
        seed=seed,
        metric=metric,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/startup_profile.py")
    parser.add_argument("--runs", type=int, default=30, help="probe iterations per benchmark")
    parser.add_argument("--output", type=str, default="", help="optional output json path")
    parser.add_argument("--seed", type=int, default=0, help="deterministic seed for benchmark env")
    parser.add_argument("--fixture", type=str, default=str(DEFAULT_FIXTURE), help="workload fixture json path")
    args = parser.parse_args()

    fixture = _load_startup_fixture(args.fixture)
    fixture_env_raw = fixture.get("env", {}) if isinstance(fixture, dict) else {}
    startup_env: Dict[str, str] = {}
    if isinstance(fixture_env_raw, dict):
        startup_env = {str(key): str(value) for key, value in fixture_env_raw.items()}
    probe_order = fixture.get("probe_order", []) if isinstance(fixture, dict) else []
    if not isinstance(probe_order, list) or not probe_order:
        probe_order = ["startup", "quick_quit", "quick_quit_stall", "quick_quit_stall_ultrafast"]

    payload: Dict[str, float] = {}
    for step in probe_order:
        name = str(step).strip().lower()
        if name == "startup":
            payload.update(_run_startup_probe(args.runs, startup_env=startup_env, seed=int(args.seed)))
        elif name == "quick_quit":
            payload.update(_run_quick_quit_probe(args.runs, startup_env=startup_env, seed=int(args.seed)))
        elif name == "quick_quit_stall":
            payload.update(
                _run_quick_quit_stall_probe(
                    args.runs,
                    startup_env=startup_env,
                    seed=int(args.seed),
                    ultra_fast=False,
                )
            )
        elif name == "quick_quit_stall_ultrafast":
            payload.update(
                _run_quick_quit_stall_probe(
                    args.runs,
                    startup_env=startup_env,
                    seed=int(args.seed),
                    ultra_fast=True,
                )
            )
    payload["generated_at_unix"] = float(time.time())
    payload["commit"] = os.environ.get("GITHUB_SHA", "").strip()
    payload["seed"] = int(args.seed)

    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
