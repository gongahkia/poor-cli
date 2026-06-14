from __future__ import annotations

import sys
from pathlib import Path

from poor_cli.store import RunStore
from poor_cli.tui import handle_tui_command


def test_tui_command_handler_runs_and_replays(tmp_path: Path, monkeypatch) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    store_dir = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    result = handle_tui_command(store_dir, "run --yes test goal", repo_path=tmp_path)

    assert result.run_id
    store = RunStore(store_dir)
    try:
        assert store.get_run(result.run_id)["status"] == "completed"
        assert store.list_artifacts(result.run_id, "agent.input")
    finally:
        store.close()

    replay = handle_tui_command(store_dir, f"replay {result.run_id}", repo_path=tmp_path)

    assert replay.run_id == result.run_id
    assert "completed" in replay.message
