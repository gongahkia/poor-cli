import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "bench" / "tool_capability_graph_profile.py"


def test_tool_capability_graph_profile_outputs_expected_shape(tmp_path):
    output = tmp_path / "graph-profile.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--runs",
            "1",
            "--output",
            str(output),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "baseline" in payload
    assert "graphGuided" in payload
    assert "comparison" in payload
    comparison = payload["comparison"]
    assert "missRateBaseline" in comparison
    assert "missRateGraphGuided" in comparison
