#!/usr/bin/env python3
"""provider probe cold-path breakdown: cache load vs tcp connect vs http probe."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from poor_cli import provider_probe
from poor_cli.config import Config


class _ConfigManagerStub:
    def get_api_key_info(self, _provider_name: str):
        return {"key": "", "source": "none"}


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


def _summary(prefix: str, values: List[float]) -> Dict[str, float]:
    return {
        f"{prefix}_mean_ms": statistics.mean(values) if values else 0.0,
        f"{prefix}_p50_ms": _percentile(values, 50.0),
        f"{prefix}_p95_ms": _percentile(values, 95.0),
        f"{prefix}_p99_ms": _percentile(values, 99.0),
    }


def _reset_probe_cache() -> None:
    with provider_probe._probe_cache_lock:
        provider_probe._probe_cache_at = 0.0
        provider_probe._probe_cache_signature = ""
        provider_probe._probe_cache_result = None
        provider_probe._probe_cache_refreshing = False


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/provider_probe_breakdown.py")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    manager = _ConfigManagerStub()
    config = Config()
    runs = max(1, int(args.runs))
    temp_cache = Path(tempfile.gettempdir()) / "poorcli_provider_probe_breakdown_cache.json"
    os.environ["POORCLI_PROVIDER_PROBE_CACHE_PATH"] = str(temp_cache)

    total_ms: List[float] = []
    cache_load_ms: List[float] = []
    tcp_connect_ms: List[float] = []
    http_probe_ms: List[float] = []
    tcp_connect_calls: List[int] = []
    http_probe_calls: List[int] = []
    for _ in range(runs):
        _reset_probe_cache()
        try:
            temp_cache.unlink(missing_ok=True)
        except Exception:
            pass

        accum: Dict[str, float | int] = {
            "cache_load_ms": 0.0,
            "tcp_connect_ms": 0.0,
            "http_probe_ms": 0.0,
            "tcp_connect_calls": 0,
            "http_probe_calls": 0,
        }
        original_cache_load = provider_probe._load_probe_cache_from_disk
        original_connect = provider_probe.socket.create_connection
        original_urlopen = provider_probe.urlopen

        def _wrap_cache_load(signature: str):
            started = time.perf_counter()
            result = original_cache_load(signature)
            accum["cache_load_ms"] = float(accum["cache_load_ms"]) + (time.perf_counter() - started) * 1000.0
            return result

        def _wrap_connect(address, timeout=None, source_address=None):
            started = time.perf_counter()
            try:
                return original_connect(address, timeout=timeout, source_address=source_address)
            finally:
                accum["tcp_connect_ms"] = float(accum["tcp_connect_ms"]) + (time.perf_counter() - started) * 1000.0
                accum["tcp_connect_calls"] = int(accum["tcp_connect_calls"]) + 1

        def _wrap_urlopen(*wrapped_args, **wrapped_kwargs):
            started = time.perf_counter()
            try:
                return original_urlopen(*wrapped_args, **wrapped_kwargs)
            finally:
                accum["http_probe_ms"] = float(accum["http_probe_ms"]) + (time.perf_counter() - started) * 1000.0
                accum["http_probe_calls"] = int(accum["http_probe_calls"]) + 1

        provider_probe._load_probe_cache_from_disk = _wrap_cache_load  # type: ignore[assignment]
        provider_probe.socket.create_connection = _wrap_connect  # type: ignore[assignment]
        provider_probe.urlopen = _wrap_urlopen  # type: ignore[assignment]
        started = time.perf_counter()
        try:
            provider_probe.probe_providers(
                manager,
                config,
                allow_stale=False,
                background_refresh=False,
                force_refresh=False,
            )
        finally:
            total_ms.append((time.perf_counter() - started) * 1000.0)
            cache_load_ms.append(float(accum["cache_load_ms"]))
            tcp_connect_ms.append(float(accum["tcp_connect_ms"]))
            http_probe_ms.append(float(accum["http_probe_ms"]))
            tcp_connect_calls.append(int(accum["tcp_connect_calls"]))
            http_probe_calls.append(int(accum["http_probe_calls"]))
            provider_probe._load_probe_cache_from_disk = original_cache_load  # type: ignore[assignment]
            provider_probe.socket.create_connection = original_connect  # type: ignore[assignment]
            provider_probe.urlopen = original_urlopen  # type: ignore[assignment]

    payload: Dict[str, Any] = {"runs": runs}
    payload.update(_summary("probe_total", total_ms))
    payload.update(_summary("cache_load", cache_load_ms))
    payload.update(_summary("tcp_connect", tcp_connect_ms))
    payload.update(_summary("http_probe", http_probe_ms))
    payload["tcp_connect_calls_mean"] = statistics.mean(tcp_connect_calls) if tcp_connect_calls else 0.0
    payload["http_probe_calls_mean"] = statistics.mean(http_probe_calls) if http_probe_calls else 0.0

    body = json.dumps(payload, sort_keys=True)
    print(body)
    if str(args.output or "").strip():
        out_path = Path(str(args.output)).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
