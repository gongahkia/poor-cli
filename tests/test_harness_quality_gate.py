import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "harness_quality_gate.py"


def test_harness_quality_gate_outputs_expected_shape(tmp_path):
    output = tmp_path / "harness-quality.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(output),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "taskCount" in payload
    assert "taskSuccessRate" in payload
    assert "avgToolCalls" in payload
    assert "avgToolPrecision" in payload
    assert "avgToolRecall" in payload
    assert "avgExtraCalls" in payload
    assert "p95TurnLatencyMs" in payload
    assert "estimatedCostUsdTotal" in payload
    assert "rows" in payload


def test_harness_quality_gate_autonomous_mode(tmp_path):
    output = tmp_path / "harness-quality-autonomous.json"
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
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload.get("plannerMode") == "autonomous"
    assert payload.get("avgToolRecall", 0.0) >= 0.0
