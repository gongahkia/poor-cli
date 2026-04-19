#!/usr/bin/env python3
# ruff: noqa: E402
"""Status-view burst polling profile."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poor_cli.server.runtime import PoorCLIServer

DEFAULT_FIXTURE = REPO_ROOT / "bench" / "fixtures" / "workloads.json"


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


class _CoreStub:
    def __init__(self, delay_ms: float) -> None:
        self.delay_ms = max(0.0, float(delay_ms))
        self.calls = 0

    def build_status_view(self) -> Dict[str, Any]:
        self.calls += 1
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000.0)
        return {
            "session": {"routingMode": "manual"},
            "trust": {},
            "provider": {},
            "context": {},
            "runs": {},
            "recovery": {},
        }


def _load_fixture(path: str) -> Dict[str, Any]:
    fixture_path = Path(path).expanduser().resolve()
    if not fixture_path.exists():
        return {}
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    scoped = payload.get("status_view_burst_profile", {})
    return scoped if isinstance(scoped, dict) else {}


async def _run_burst(server: PoorCLIServer, request_count: int) -> List[float]:
    latencies: List[float] = []

    async def _single() -> None:
        started = time.perf_counter()
        await server.handle_get_status_view({})
        latencies.append((time.perf_counter() - started) * 1000.0)

    await asyncio.gather(*[_single() for _ in range(max(1, request_count))])
    return latencies


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    fixture = _load_fixture(args.fixture)
    rng = random.Random(int(args.seed))
    sequence = fixture.get("requests_per_burst_sequence", []) if isinstance(fixture, dict) else []
    request_sequence: List[int] = []
    if isinstance(sequence, list):
        for item in sequence:
            try:
                request_sequence.append(max(1, int(item)))
            except (TypeError, ValueError):
                continue
    if not request_sequence:
        request_sequence = [max(1, int(args.requests_per_burst))]
    stale_age_padding_ms = float(fixture.get("stale_age_padding_ms", 500.0)) if isinstance(fixture, dict) else 500.0
    stale_age_s = max(1.0, float(args.ttl_ms) / 1000.0 + max(0.0, stale_age_padding_ms) / 1000.0)
    server = PoorCLIServer()
    server.initialized = True
    core = _CoreStub(delay_ms=args.build_delay_ms)
    server.core = core
    server._status_view_cache_ttl_ms = float(args.ttl_ms)
    server._status_view_cache_payload = {
        "session": {"routingMode": "stale"},
        "trust": {},
        "provider": {},
        "context": {},
        "runs": {},
        "recovery": {},
    }
    server._status_view_cache_at = time.monotonic() - stale_age_s

    all_latencies: List[float] = []
    calls_before = core.calls
    burst_sizes: List[int] = []
    for idx in range(max(1, args.bursts)):
        server._status_view_cache_at = time.monotonic() - stale_age_s
        request_count = request_sequence[idx % len(request_sequence)]
        if len(request_sequence) > 1:
            offset = rng.randrange(len(request_sequence))
            request_count = request_sequence[(idx + offset) % len(request_sequence)]
        burst_sizes.append(request_count)
        all_latencies.extend(await _run_burst(server, request_count))
        await asyncio.sleep(max(0.0, float(args.settle_ms) / 1000.0))
    calls_after = core.calls

    return {
        "seed": int(args.seed),
        "bursts": int(args.bursts),
        "requests_per_burst": int(args.requests_per_burst),
        "burst_request_sizes": burst_sizes,
        "total_requests": int(sum(burst_sizes)),
        "cache_ttl_ms": float(args.ttl_ms),
        "build_delay_ms": float(args.build_delay_ms),
        "core_build_status_view_calls": int(calls_after - calls_before),
        "build_calls_per_burst": (float(calls_after - calls_before) / float(args.bursts)) if args.bursts else 0.0,
        "latency_mean_ms": statistics.mean(all_latencies) if all_latencies else 0.0,
        "latency_p50_ms": _percentile(all_latencies, 50.0),
        "latency_p95_ms": _percentile(all_latencies, 95.0),
        "latency_p99_ms": _percentile(all_latencies, 99.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/status_view_burst_profile.py")
    parser.add_argument("--bursts", type=int, default=20)
    parser.add_argument("--requests-per-burst", type=int, default=25)
    parser.add_argument("--ttl-ms", type=float, default=200.0)
    parser.add_argument("--build-delay-ms", type=float, default=30.0)
    parser.add_argument("--settle-ms", type=float, default=40.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--fixture", type=str, default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
    payload = asyncio.run(_run(args))
    body = json.dumps(payload, sort_keys=True)
    print(body)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
