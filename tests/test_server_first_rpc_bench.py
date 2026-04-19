"""Tests for server first-RPC bench helpers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_server_first_rpc_profile_runs(tmp_path: Path) -> None:
    output_path = tmp_path / "server-first-rpc.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bench" / "server_first_rpc_profile.py"),
            "--python",
            sys.executable,
            "--runs",
            "1",
            "--timeout-s",
            "10",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert int(payload.get("nonzero_exit_count", 0)) == 0
    assert float(payload.get("startup_to_first_response_p50_ms", 0.0)) > 0.0


def test_server_first_rpc_compare_detects_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "base.json"
    candidate_ok = tmp_path / "head-ok.json"
    candidate_bad = tmp_path / "head-bad.json"
    baseline.write_text(
        json.dumps(
            {
                "startup_to_first_response_p50_ms": 100.0,
                "request_roundtrip_p50_ms": 30.0,
            }
        ),
        encoding="utf-8",
    )
    candidate_ok.write_text(
        json.dumps(
            {
                "startup_to_first_response_p50_ms": 120.0,
                "request_roundtrip_p50_ms": 40.0,
            }
        ),
        encoding="utf-8",
    )
    candidate_bad.write_text(
        json.dumps(
            {
                "startup_to_first_response_p50_ms": 280.0,
                "request_roundtrip_p50_ms": 140.0,
            }
        ),
        encoding="utf-8",
    )

    ok = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bench" / "server_first_rpc_compare.py"),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate_ok),
            "--relative-threshold",
            "0.30",
            "--absolute-threshold-ms",
            "50",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0, ok.stderr or ok.stdout

    bad = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bench" / "server_first_rpc_compare.py"),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate_bad),
            "--relative-threshold",
            "0.30",
            "--absolute-threshold-ms",
            "50",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 1, bad.stdout
