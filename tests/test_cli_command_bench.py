"""Tests for CLI command latency profiling helpers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_cli_command_profile_runs(tmp_path: Path) -> None:
    output_path = tmp_path / "cli-profile.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bench" / "cli_command_profile.py"),
            "--python",
            sys.executable,
            "--runs",
            "1",
            "--commands=--version;--help",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    commands = payload.get("commands", [])
    assert isinstance(commands, list)
    assert len(commands) == 2
    assert all(int(row.get("nonzero_exit_count", 0)) == 0 for row in commands if isinstance(row, dict))


def test_cli_command_compare_detects_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "base.json"
    candidate_ok = tmp_path / "head-ok.json"
    candidate_bad = tmp_path / "head-bad.json"
    baseline.write_text(
        json.dumps(
            {
                "commands": [
                    {"command": "--help", "wall_p50_ms": 100.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    candidate_ok.write_text(
        json.dumps(
            {
                "commands": [
                    {"command": "--help", "wall_p50_ms": 110.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    candidate_bad.write_text(
        json.dumps(
            {
                "commands": [
                    {"command": "--help", "wall_p50_ms": 260.0},
                ]
            }
        ),
        encoding="utf-8",
    )

    ok = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bench" / "cli_command_compare.py"),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate_ok),
            "--relative-threshold",
            "0.30",
            "--absolute-threshold-ms",
            "60",
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
            str(REPO_ROOT / "bench" / "cli_command_compare.py"),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate_bad),
            "--relative-threshold",
            "0.30",
            "--absolute-threshold-ms",
            "60",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 1, bad.stdout
