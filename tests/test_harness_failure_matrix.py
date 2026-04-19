import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "harness_failure_matrix.py"


def _bench_env() -> dict:
    env = os.environ.copy()
    path_sep = os.pathsep
    existing = env.get("PYTHONPATH", "")
    root = str(REPO_ROOT)
    env["PYTHONPATH"] = f"{root}{path_sep}{existing}" if existing else root
    return env


def test_harness_failure_matrix_outputs_expected_shape(tmp_path):
    output = tmp_path / "harness-failure-matrix.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
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
    assert "scenarioCount" in payload
    assert "recoverySuccessRate" in payload
    assert "meanRecoveryLatencyMs" in payload
    assert "rows" in payload
