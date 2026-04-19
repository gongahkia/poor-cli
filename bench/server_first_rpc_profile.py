#!/usr/bin/env python3
"""Profile poor-cli stdio server startup to first-RPC latency."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


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


async def _write_message(
    writer: asyncio.StreamWriter,
    payload: Dict[str, Any],
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    writer.write(header)
    writer.write(body)
    await writer.drain()


async def _read_message(
    reader: asyncio.StreamReader,
    timeout_s: float,
) -> Dict[str, Any]:
    header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=timeout_s)
    content_length = 0
    for raw_line in header.decode("ascii", errors="replace").splitlines():
        line = raw_line.strip()
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break
    if content_length <= 0:
        raise RuntimeError("missing Content-Length")
    body = await asyncio.wait_for(reader.readexactly(content_length), timeout=timeout_s)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("invalid response payload")
    return payload


async def _run_once(
    python_bin: str,
    method: str,
    timeout_s: float,
) -> Dict[str, Any]:
    startup_started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        python_bin,
        "-m",
        "poor_cli",
        "server",
        "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("failed to open stdio pipes")
    request_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {},
    }
    request_started = time.perf_counter()
    await _write_message(proc.stdin, request_payload)
    first_response = await _read_message(proc.stdout, timeout_s=timeout_s)
    startup_to_first_response_ms = (time.perf_counter() - startup_started) * 1000.0
    request_roundtrip_ms = (time.perf_counter() - request_started) * 1000.0

    exit_code = 0
    if proc.stdin is not None:
        proc.stdin.close()
        try:
            await proc.stdin.wait_closed()
        except Exception:
            pass
    try:
        exit_code = int(await asyncio.wait_for(proc.wait(), timeout=timeout_s))
    except asyncio.TimeoutError:
        proc.terminate()
        try:
            exit_code = int(await asyncio.wait_for(proc.wait(), timeout=timeout_s))
        except asyncio.TimeoutError:
            proc.kill()
            exit_code = int(await proc.wait())

    return {
        "startup_to_first_response_ms": startup_to_first_response_ms,
        "request_roundtrip_ms": request_roundtrip_ms,
        "exit_code": exit_code,
        "response_has_error": bool(isinstance(first_response.get("error"), dict)),
    }


async def _profile(
    python_bin: str,
    method: str,
    runs: int,
    timeout_s: float,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for _ in range(max(1, int(runs))):
        rows.append(await _run_once(python_bin, method, timeout_s))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/server_first_rpc_profile.py")
    parser.add_argument("--python", default=sys.executable, help="python executable")
    parser.add_argument("--method", default="getStartupState", help="JSON-RPC method for first request")
    parser.add_argument("--runs", type=int, default=5, help="number of runs")
    parser.add_argument("--timeout-s", type=float, default=8.0, help="timeout per read/wait")
    parser.add_argument("--output", default="", help="optional output json path")
    args = parser.parse_args()

    rows = asyncio.run(_profile(str(args.python), str(args.method), int(args.runs), float(args.timeout_s)))
    startup_values = [float(row.get("startup_to_first_response_ms", 0.0)) for row in rows]
    roundtrip_values = [float(row.get("request_roundtrip_ms", 0.0)) for row in rows]
    exit_codes = [int(row.get("exit_code", 0)) for row in rows]
    response_error_count = sum(1 for row in rows if bool(row.get("response_has_error")))

    payload = {
        "python": str(args.python),
        "method": str(args.method),
        "runs": len(rows),
        "startup_to_first_response_mean_ms": round(statistics.mean(startup_values), 6),
        "startup_to_first_response_p50_ms": round(_percentile(startup_values, 50.0), 6),
        "startup_to_first_response_p95_ms": round(_percentile(startup_values, 95.0), 6),
        "request_roundtrip_mean_ms": round(statistics.mean(roundtrip_values), 6),
        "request_roundtrip_p50_ms": round(_percentile(roundtrip_values, 50.0), 6),
        "request_roundtrip_p95_ms": round(_percentile(roundtrip_values, 95.0), 6),
        "exit_codes": exit_codes,
        "nonzero_exit_count": int(sum(1 for code in exit_codes if code != 0)),
        "response_error_count": int(response_error_count),
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
