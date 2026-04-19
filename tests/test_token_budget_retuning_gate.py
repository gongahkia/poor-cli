import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "token_budget_retuning_gate.py"


def _bench_env() -> dict:
    env = os.environ.copy()
    path_sep = os.pathsep
    existing = env.get("PYTHONPATH", "")
    root = str(REPO_ROOT)
    env["PYTHONPATH"] = f"{root}{path_sep}{existing}" if existing else root
    return env


def test_token_budget_retuning_gate_outputs_expected_shape(tmp_path):
    poor_cli_dir = tmp_path / ".poor-cli"
    poor_cli_dir.mkdir(parents=True, exist_ok=True)
    log_path = poor_cli_dir / "budget_logs.jsonl"
    records = [
        {"state": {"task_complexity": 0.1}, "action": {"max_thinking_tokens": 256}, "outcome": {"task_succeeded": True}},
        {"state": {"task_complexity": 0.3}, "action": {"max_thinking_tokens": 1024}, "outcome": {"task_succeeded": True}},
        {"state": {"task_complexity": 0.6}, "action": {"max_thinking_tokens": 4096}, "outcome": {"task_succeeded": True}},
    ]
    with log_path.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row) + "\n")

    output = tmp_path / "token-budget-retuning.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--min-records",
            "1",
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
    assert "retuning" in payload
    assert "latestTuning" in payload
    assert "budgetDeltaRatios" in payload
