from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from poor_cli.rpc import RpcServer
from poor_cli.store import RunStore


def _planner(path: Path, command: str | None = None) -> None:
    command_field = f", 'command': {command!r}" if command else ""
    path.write_text(
        "import json, sys\nsys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        f"'risks':[],'tasks':[{{'title':'Task','objective':'obj','suggested_agent':'generic'{command_field}}}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{}}))\n",
        encoding="utf-8",
    )


def _lines(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_rpc_rejects_malformed_json(tmp_path: Path, capsys) -> None:
    RpcServer(tmp_path / "store").handle("{bad\n")

    response = _lines(capsys.readouterr().out)[0]
    assert response["error"]["code"] == -32700


def test_rpc_run_status_inspect_replay(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    _planner(planner)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")
    server = RpcServer(tmp_path / "store")

    server.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "run", "params": {"goal": "rpc goal"}}))
    run_id = _lines(capsys.readouterr().out)[0]["result"]["run_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        store = RunStore(tmp_path / "store")
        status = store.get_run(str(run_id))["status"]
        store.close()
        if status == "completed":
            break
        time.sleep(0.05)

    server.handle(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "status", "params": {"run_id": run_id}}))
    server.handle(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "inspect", "params": {"run_id": run_id}}))
    server.handle(json.dumps({"jsonrpc": "2.0", "id": 4, "method": "replay", "params": {"run_id": run_id, "verify": True}}))
    responses = _lines(capsys.readouterr().out)

    assert any(row.get("method") == "poor/event" for row in responses)
    assert [row["result"]["status"] for row in responses if row.get("id") == 2] == ["completed"]
    assert [row["result"]["tasks"][0]["status"] for row in responses if row.get("id") == 3] == ["completed"]
    assert [row["result"]["verification"]["verified"] for row in responses if row.get("id") == 4] == [True]


def test_rpc_cancel_active_run(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    _planner(planner, f'{sys.executable} -c "import time; time.sleep(5)"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")
    server = RpcServer(tmp_path / "store")

    server.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "run", "params": {"goal": "cancel"}}))
    run_id = _lines(capsys.readouterr().out)[0]["result"]["run_id"]
    server.handle(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "cancel", "params": {"run_id": run_id}}))
    assert _lines(capsys.readouterr().out)[0]["result"]["cancelled"] is True

    deadline = time.monotonic() + 5
    status = ""
    while time.monotonic() < deadline:
        store = RunStore(tmp_path / "store")
        status = str(store.get_run(str(run_id))["status"])
        store.close()
        if status == "cancelled":
            break
        time.sleep(0.05)
    assert status == "cancelled"
