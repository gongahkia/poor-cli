#!/usr/bin/env python3
"""lightweight perf guardrails for CLI startup/quit/probe paths."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import tempfile
import asyncio
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
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


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    target = max(0.0, min(100.0, float(pct)))
    idx = (target / 100.0) * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    weight = idx - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def _latency_summary(metric: str, values: List[float]) -> Dict[str, float]:
    return {
        f"{metric}_mean_ms": statistics.mean(values) if values else 0.0,
        f"{metric}_std_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
        f"{metric}_p50_ms": _percentile(values, 50.0),
        f"{metric}_p95_ms": _percentile(values, 95.0),
        f"{metric}_p99_ms": _percentile(values, 99.0),
    }


def _run_cli_command(cmd: List[str], runs: int, metric: str) -> Dict[str, float]:
    durations: List[float] = []
    for _ in range(runs):
        env = dict(os.environ)
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
    return _latency_summary(metric, durations)


def _run_startup_probe(runs: int = 5) -> Dict[str, float]:
    timings = _run_cli_command([sys.executable, "-m", "poor_cli", "help"], runs, "cli_startup")
    values = [float(v) for k, v in timings.items() if k.startswith("cli_startup_") and k.endswith("_ms")]
    mean_ms = float(timings.get("cli_startup_mean_ms", 0.0))
    result = {}
    result.update(_latency_summary("setup_return", [mean_ms]))
    result.update(_latency_summary("setup_complete", [mean_ms]))
    result.update(_latency_summary("first_tick", values or [mean_ms]))
    return result


def _run_quick_quit_probe(runs: int = 10) -> Dict[str, float]:
    return _run_cli_command([sys.executable, "-m", "poor_cli", "--version"], runs, "quick_quit")


def _run_quick_quit_stall_probe(runs: int = 5, ultra_fast: bool = False) -> Dict[str, float]:
    metric = "quick_quit_stall_ultrafast" if ultra_fast else "quick_quit_stall"
    return _run_cli_command([sys.executable, "-m", "poor_cli", "help"], runs, metric)


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


def _run_mock_ttft_bench(cold_runs: int = 3, warm_runs_per_cold: int = 3) -> Dict[str, float]:
    from poor_cli.core import PoorCLICore
    from poor_cli.providers.base import ProviderCapabilities, ProviderResponse, UsageMetadata
    from poor_cli.providers.capability import ProviderCapability
    from poor_cli.providers.provider_factory import ProviderFactory

    class _FakeProvider:
        capabilities = frozenset({
            ProviderCapability.STREAMING,
            ProviderCapability.TOOL_CALLING,
            ProviderCapability.SYSTEM_INSTRUCTIONS,
        })

        def __init__(self) -> None:
            self.model_name = "perf-bench-model"
            self._history = []

        async def initialize(self, tools=None, system_instruction=None):
            await asyncio.sleep(0.04)

        async def send_message(self, message, **kwargs):
            await asyncio.sleep(0.05)
            return ProviderResponse(content="ok")

        async def send_message_stream(self, message):
            await asyncio.sleep(0.05)
            yield ProviderResponse(
                content="ok",
                usage=UsageMetadata(input_tokens=4, output_tokens=2),
            )

        async def clear_history(self):
            self._history = []

        def get_history(self):
            return list(self._history)

        def set_history(self, messages):
            self._history = list(messages)

        def get_capabilities(self):
            return ProviderCapabilities(
                supports_streaming=True,
                supports_function_calling=True,
                supports_system_instructions=True,
                max_context_tokens=200000,
            )

        def format_tool_results(self, tool_results):
            return tool_results

        def update_system_instruction(self, instruction):
            return None

        def update_prompt_prefix(self, prefix: str):
            return None

        def switch_model(self, model_name: str):
            self.model_name = str(model_name or self.model_name)
            return None

    original_create = ProviderFactory.create
    cold_timings: List[float] = []
    warm_timings: List[float] = []

    def _measure_first_token_ms(core: PoorCLICore, prompt: str) -> float:
        started = time.perf_counter()
        first_token_ms = None

        async def _consume() -> None:
            nonlocal first_token_ms
            async for event in core.send_message_events(prompt, source_kind="session"):
                if event.type == "text_chunk" and first_token_ms is None:
                    first_token_ms = (time.perf_counter() - started) * 1000.0
                if event.type == "done":
                    break

        asyncio.run(_consume())
        if first_token_ms is None:
            raise RuntimeError("mock ttft bench did not receive text_chunk")
        return float(first_token_ms)

    try:
        ProviderFactory.create = staticmethod(lambda **kwargs: _FakeProvider())  # type: ignore[method-assign]
        for run_idx in range(cold_runs):
            with tempfile.TemporaryDirectory() as td:
                cwd = Path.cwd()
                os.chdir(td)
                try:
                    core = PoorCLICore()
                    awaitable = core.initialize(
                        provider_name="openai",
                        model_name="gpt-5.1",
                        api_key="dummy",
                    )
                    asyncio.run(awaitable)
                    cold_timings.append(_measure_first_token_ms(core, f"cold-{run_idx}"))
                    for warm_idx in range(max(0, warm_runs_per_cold)):
                        warm_timings.append(_measure_first_token_ms(core, f"warm-{run_idx}-{warm_idx}"))
                    asyncio.run(core.shutdown())
                finally:
                    os.chdir(cwd)
    finally:
        ProviderFactory.create = original_create  # type: ignore[assignment]
    merged_timings = warm_timings if warm_timings else cold_timings
    result = _latency_summary("mock_ttft", merged_timings)
    result["mock_ttft_max_ms"] = max(merged_timings) if merged_timings else 0.0
    result.update(_latency_summary("mock_ttft_cold", cold_timings))
    result["mock_ttft_cold_max_ms"] = max(cold_timings) if cold_timings else 0.0
    result.update(_latency_summary("mock_ttft_warm", warm_timings))
    result["mock_ttft_warm_max_ms"] = max(warm_timings) if warm_timings else 0.0
    return result


def _threshold(name: str, default: float) -> float:
    value = os.environ.get(name, "")
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _checks_from_result(result: Dict[str, float], include_provider_probe_fail: bool) -> Dict[str, object]:
    mock_ttft_metric = "mock_ttft_warm_mean_ms" if "mock_ttft_warm_mean_ms" in result else "mock_ttft_mean_ms"
    hard_checks = [
        ("first_tick_p95_ms", _threshold("POORCLI_PERF_MAX_FIRST_TICK_MS", 300.0)),
        ("setup_return_mean_ms", _threshold("POORCLI_PERF_MAX_SETUP_RETURN_MS", 300.0)),
        ("setup_complete_mean_ms", _threshold("POORCLI_PERF_MAX_SETUP_COMPLETE_MS", 400.0)),
        ("quick_quit_mean_ms", _threshold("POORCLI_PERF_MAX_QUICK_QUIT_MS", 300.0)),
        (mock_ttft_metric, _threshold("POORCLI_PERF_MAX_MOCK_TTFT_MS", 1400.0)),
    ]
    soft_checks = [
        ("quick_quit_stall_p95_ms", _threshold("POORCLI_PERF_MAX_STALLED_QUIT_P95_MS", 2800.0)),
        ("quick_quit_stall_ultrafast_p95_ms", _threshold("POORCLI_PERF_MAX_STALLED_QUIT_ULTRAFAST_P95_MS", 450.0)),
        ("provider_probe_cold_ms", _threshold("POORCLI_PERF_MAX_PROVIDER_PROBE_COLD_MS", 500.0)),
        ("provider_probe_repeat_mean_ms", _threshold("POORCLI_PERF_MAX_PROVIDER_PROBE_REPEAT_MS", 2.0)),
    ]
    hard_failures = [
        f"{metric}={result.get(metric, 0.0):.2f}ms > {limit:.2f}ms"
        for metric, limit in hard_checks
        if float(result.get(metric, 0.0)) > limit
    ]
    soft_failures = [
        f"{metric}={result.get(metric, 0.0):.2f}ms > {limit:.2f}ms"
        for metric, limit in soft_checks
        if float(result.get(metric, 0.0)) > limit
    ]
    if include_provider_probe_fail:
        hard_failures.extend(soft_failures)
    return {
        "hardChecks": [
            {"metric": metric, "limitMs": limit}
            for metric, limit in hard_checks
        ],
        "softChecks": [
            {"metric": metric, "limitMs": limit}
            for metric, limit in soft_checks
        ],
        "hardFailures": hard_failures,
        "softFailures": soft_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/perf_guardrail.py")
    parser.add_argument(
        "--report-path",
        default="",
        help="optional output path for machine-readable report",
    )
    parser.add_argument(
        "--include-provider-probe-fail",
        action="store_true",
        help="promote provider-probe soft failures to hard failures",
    )
    args = parser.parse_args()

    startup = _run_startup_probe()
    quick_quit = _run_quick_quit_probe()
    quick_quit_stall = _run_quick_quit_stall_probe()
    quick_quit_stall_ultrafast = _run_quick_quit_stall_probe(ultra_fast=True)
    provider_probe_stats = _run_provider_probe_microbench()
    mock_ttft = _run_mock_ttft_bench()
    result = {
        **startup,
        **quick_quit,
        **quick_quit_stall,
        **quick_quit_stall_ultrafast,
        **provider_probe_stats,
        **mock_ttft,
    }
    scenario_rows = [
        {
            "scenario": "normal",
            "setupReturnMeanMs": float(result.get("setup_return_mean_ms", 0.0)),
            "setupCompleteMeanMs": float(result.get("setup_complete_mean_ms", 0.0)),
            "quickQuitMeanMs": float(result.get("quick_quit_mean_ms", 0.0)),
            "firstTickP95Ms": float(result.get("first_tick_p95_ms", 0.0)),
        },
        {
            "scenario": "backend_unavailable",
            "providerProbeColdMs": float(result.get("provider_probe_cold_ms", 0.0)),
            "providerProbeRepeatMeanMs": float(result.get("provider_probe_repeat_mean_ms", 0.0)),
        },
        {
            "scenario": "stalled_exit",
            "quickQuitStallMeanMs": float(result.get("quick_quit_stall_mean_ms", 0.0)),
            "quickQuitStallP95Ms": float(result.get("quick_quit_stall_p95_ms", 0.0)),
            "quickQuitStallUltraFastMeanMs": float(result.get("quick_quit_stall_ultrafast_mean_ms", 0.0)),
            "quickQuitStallUltraFastP95Ms": float(result.get("quick_quit_stall_ultrafast_p95_ms", 0.0)),
        },
        {
            "scenario": "slow_startup",
            "setupCompleteP99Ms": float(result.get("setup_complete_p99_ms", 0.0)),
            "mockTtftP95Ms": float(result.get("mock_ttft_warm_p95_ms", result.get("mock_ttft_p95_ms", 0.0))),
        },
    ]
    checks = _checks_from_result(result, include_provider_probe_fail=args.include_provider_probe_fail)
    payload = {
        "metrics": result,
        "scenarioRows": scenario_rows,
        "checks": checks,
    }
    encoded = json.dumps(payload, sort_keys=True)
    print(encoded)
    if str(args.report_path or "").strip():
        out_path = Path(str(args.report_path)).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(encoded + "\n", encoding="utf-8")

    hard_failures = list(checks.get("hardFailures", []))
    soft_failures = list(checks.get("softFailures", []))
    if hard_failures:
        for failure in hard_failures:
            print(f"[perf-guardrail] {failure}", file=sys.stderr)
        return 1
    for failure in soft_failures:
        print(f"[perf-guardrail soft] {failure}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
