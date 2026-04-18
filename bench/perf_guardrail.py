#!/usr/bin/env python3
"""lightweight perf guardrails for startup/quit/probe paths."""

from __future__ import annotations

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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _ConfigManagerStub:
    def get_api_key_info(self, _provider_name: str):
        return {"key": "", "source": "none"}


def _json_line_from_stdout(stdout: str) -> Dict[str, object]:
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"missing json payload: {stdout!r}")


def _run_startup_probe(runs: int = 5) -> Dict[str, float]:
    rows: List[Dict[str, object]] = []
    cmd = ["nvim", "--headless", "-u", "NONE", "-n", "-l", str(STARTUP_PROBE)]
    for _ in range(runs):
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
        rows.append(_json_line_from_stdout(proc.stdout))
    setup_return = [float(row.get("setup_return_ms", 0.0) or 0.0) for row in rows]
    setup_complete = [float(row.get("setup_complete_ms", 0.0) or 0.0) for row in rows]
    return {
        "setup_return_mean_ms": statistics.mean(setup_return),
        "setup_complete_mean_ms": statistics.mean(setup_complete),
    }


def _run_quick_quit_probe(runs: int = 10) -> Dict[str, float]:
    cmd = ["nvim", "--headless", "-u", "NONE", "-n", "-l", str(QUICK_QUIT_PROBE)]
    durations: List[float] = []
    for _ in range(runs):
        env = dict(os.environ)
        env["POORCLI_BENCH_AUTO_START"] = "0"
        start = time.perf_counter()
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        durations.append((time.perf_counter() - start) * 1000.0)
        if proc.returncode != 0:
            raise RuntimeError(f"quick quit probe failed: {proc.stderr}\n{proc.stdout}")
    return {"quick_quit_mean_ms": statistics.mean(durations)}


def _run_provider_probe_microbench() -> Dict[str, float]:
    from poor_cli.config import Config
    from poor_cli import provider_probe

    manager = _ConfigManagerStub()
    config = Config()
    with provider_probe._probe_cache_lock:
        provider_probe._probe_cache_at = 0.0
        provider_probe._probe_cache_signature = ""
        provider_probe._probe_cache_result = None
        provider_probe._probe_cache_refreshing = False

    t0 = time.perf_counter()
    provider_probe.probe_providers(
        manager,
        config,
        allow_stale=False,
        background_refresh=False,
        force_refresh=True,
    )
    cold_ms = (time.perf_counter() - t0) * 1000.0

    repeats: List[float] = []
    for _ in range(20):
        t1 = time.perf_counter()
        provider_probe.probe_providers(manager, config)
        repeats.append((time.perf_counter() - t1) * 1000.0)
    return {
        "provider_probe_cold_ms": cold_ms,
        "provider_probe_repeat_mean_ms": statistics.mean(repeats),
    }


def _threshold(name: str, default: float) -> float:
    value = os.environ.get(name, "")
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def main() -> int:
    startup = _run_startup_probe()
    quick_quit = _run_quick_quit_probe()
    provider_probe_stats = _run_provider_probe_microbench()
    result = {**startup, **quick_quit, **provider_probe_stats}
    print(json.dumps(result, sort_keys=True))

    checks = [
        ("setup_return_mean_ms", _threshold("POORCLI_PERF_MAX_SETUP_RETURN_MS", 30.0)),
        ("setup_complete_mean_ms", _threshold("POORCLI_PERF_MAX_SETUP_COMPLETE_MS", 80.0)),
        ("quick_quit_mean_ms", _threshold("POORCLI_PERF_MAX_QUICK_QUIT_MS", 120.0)),
        ("provider_probe_cold_ms", _threshold("POORCLI_PERF_MAX_PROVIDER_PROBE_COLD_MS", 500.0)),
        ("provider_probe_repeat_mean_ms", _threshold("POORCLI_PERF_MAX_PROVIDER_PROBE_REPEAT_MS", 2.0)),
    ]
    failures = [
        f"{metric}={result[metric]:.2f}ms > {limit:.2f}ms"
        for metric, limit in checks
        if float(result.get(metric, 0.0)) > limit
    ]
    if failures:
        for failure in failures:
            print(f"[perf-guardrail] {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
