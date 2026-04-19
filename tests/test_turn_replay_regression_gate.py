import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "turn_replay_regression_gate.py"


def _bench_env() -> dict:
    env = os.environ.copy()
    path_sep = os.pathsep
    existing = env.get("PYTHONPATH", "")
    root = str(REPO_ROOT)
    env["PYTHONPATH"] = f"{root}{path_sep}{existing}" if existing else root
    return env


def test_turn_replay_regression_gate_outputs_expected_shape(tmp_path):
    output = tmp_path / "turn-replay-gate.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "autonomous",
            "--output",
            str(output),
        ],
        cwd=str(REPO_ROOT),
        env=_bench_env(),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "baseline" in payload
    assert "candidate" in payload
    assert "comparison" in payload
    comparison = payload["comparison"]
    assert "decisionDriftRate" in comparison
    assert "completionReasonDriftRate" in comparison
