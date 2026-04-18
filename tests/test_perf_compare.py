import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "perf_compare.py"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_perf_compare_passes_within_threshold(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_json(
        baseline,
        {
            "warm_setup_return_p95_ms": 30.0,
            "warm_setup_complete_p95_ms": 60.0,
            "quick_quit_p95_ms": 100.0,
        },
    )
    _write_json(
        candidate,
        {
            "warm_setup_return_p95_ms": 33.0,
            "warm_setup_complete_p95_ms": 63.0,
            "quick_quit_p95_ms": 104.0,
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--metrics",
            "warm_setup_return_p95_ms,warm_setup_complete_p95_ms,quick_quit_p95_ms",
            "--relative-threshold",
            "0.15",
            "--absolute-threshold-ms",
            "8.0",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_perf_compare_fails_on_meaningful_regression(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_json(baseline, {"warm_setup_return_p95_ms": 30.0})
    _write_json(candidate, {"warm_setup_return_p95_ms": 48.5})

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--metrics",
            "warm_setup_return_p95_ms",
            "--relative-threshold",
            "0.15",
            "--absolute-threshold-ms",
            "8.0",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "warm_setup_return_p95_ms" in proc.stdout + proc.stderr
