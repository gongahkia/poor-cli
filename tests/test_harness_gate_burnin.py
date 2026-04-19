import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "harness_gate_burnin.py"


def test_harness_gate_burnin_outputs_expected_shape(tmp_path):
    history = tmp_path / "harness-gates-history.jsonl"
    rows = [
        {"at": "2026-04-01T00:00:00+00:00", "gate": "harness_quality", "metrics": {"taskSuccessRate": 1.0, "avgToolPrecision": 1.0, "avgToolRecall": 1.0, "avgToolCalls": 2.0, "avgExtraCalls": 0.0, "p95TurnLatencyMs": 40.0}},
        {"at": "2026-04-02T00:00:00+00:00", "gate": "turn_replay", "metrics": {"decisionDriftRate": 0.0, "completionReasonDriftRate": 0.0, "latencyDeltaAbsMs": 10.0, "costDeltaAbsUsd": 0.0}},
        {"at": "2026-04-03T00:00:00+00:00", "gate": "failure_matrix", "metrics": {"recoverySuccessRate": 1.0, "stuckCount": 0.0, "meanRecoveryLatencyMs": 120.0}},
        {"at": "2026-04-04T00:00:00+00:00", "gate": "budget_retuning", "metrics": {"maxBudgetDeltaRatio": 0.2}},
    ]
    history.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    output_json = tmp_path / "burnin.json"
    output_md = tmp_path / "burnin.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(history),
            "--window-days",
            "14",
            "--min-samples-per-metric",
            "1",
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_md),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert "metrics" in payload
    assert "readyToTighten" in payload
    assert output_md.exists()
