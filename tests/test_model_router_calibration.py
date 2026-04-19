import json
import os
import subprocess
import sys
from pathlib import Path

from poor_cli.run_history import RunHistoryManager


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "model_router_calibration.py"


def _bench_env() -> dict:
    env = os.environ.copy()
    path_sep = os.pathsep
    existing = env.get("PYTHONPATH", "")
    root = str(REPO_ROOT)
    env["PYTHONPATH"] = f"{root}{path_sep}{existing}" if existing else root
    return env


def test_model_router_calibration_outputs_expected_shape(tmp_path):
    manager = RunHistoryManager(repo_root=tmp_path)
    for idx in range(4):
        run = manager.start_run(
            source_kind="session",
            source_id=f"seed-{idx}",
            metadata={
                "turnTransitions": [{"reasonCode": "complete"}] * (1 + idx),
                "turnOrchestration": [{"iterationIndex": 1, "callCount": idx}],
            },
        )
        manager.finish_run(
            run.run_id,
            status="completed" if idx % 2 == 0 else "failed",
            provider_summary={"name": "gemini", "model": "gemini-2.5-flash"},
            cost_summary={"estimated_cost_usd": 0.002 * (idx + 1)},
            summary="seed",
        )
    output = tmp_path / "router-calibration.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--provider",
            "gemini",
            "--min-samples",
            "2",
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
    assert "providers" in payload
    providers = payload["providers"]
    assert providers
    first = providers[0]
    assert "recommendedRouting" in first
    assert "complexityStats" in first
