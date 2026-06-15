from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from poor_cli.cli import main
from poor_cli.config import add_provider, empty_config, provider_preset, save_repo_config
from poor_cli.lanes import LaneError, review_run
from poor_cli.providers import ProviderResponse
from poor_cli.store import RunStore


def test_cli_plan_run_inspect_replay(tmp_path: Path) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["POOR_CLI_PLANNER_COMMAND"] = f"{sys.executable} {planner}"
    store = tmp_path / "store"

    run = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "run", "test goal", "--yes"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    run_id = next(line.split(":", 1)[1].strip() for line in run.stdout.splitlines() if line.startswith("run_id:"))

    inspect = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "inspect", run_id, "--events", "--context", "--json"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(inspect.stdout)
    assert payload["run"]["status"] == "completed"
    assert payload["tasks"][0]["status"] == "completed"
    assert any(event["type"] == "agent.completed" for event in payload["events"])
    assert payload["context_artifacts"]
    assert payload["handoff_artifacts"]
    run_store = RunStore(store)
    try:
        assert run_store.list_artifacts(run_id, "agent.input")
        assert run_store.list_artifacts(run_id, "agent.result")
        assert run_store.list_artifacts(run_id, "handoff.packet")
    finally:
        run_store.close()

    replay = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "replay", run_id, "--json"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    state = json.loads(replay.stdout)
    assert state["tasks"][payload["tasks"][0]["task_id"]]["status"] == "completed"


def test_cli_main_in_process_run_inspect_replay(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n"
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(store), "run", "test goal", "--yes"]) == 0
    run_output = capsys.readouterr().out
    run_id = next(line.split(":", 1)[1].strip() for line in run_output.splitlines() if line.startswith("run_id:"))

    assert main(["--store-dir", str(store), "inspect", run_id, "--events", "--context"]) == 0
    inspect_output = capsys.readouterr().out
    assert "agent.completed" in inspect_output
    assert "handoff " in inspect_output

    assert main(["--store-dir", str(store), "inspect", run_id, "--artifacts", "--json"]) == 0
    artifacts = json.loads(capsys.readouterr().out)["artifacts"]
    paths = {artifact["path"] for artifact in artifacts}
    assert {"PLAN.json", "PLAN.md", "review/REVIEW.json", "verify/VERIFY.json"} <= paths
    assert any(path.endswith("/RESULT.md") for path in paths)
    review = json.loads((store / "runs" / run_id / "artifacts" / "review" / "REVIEW.json").read_text(encoding="utf-8"))
    verify = json.loads((store / "runs" / run_id / "artifacts" / "verify" / "VERIFY.json").read_text(encoding="utf-8"))
    assert review["finding_fields"] == ["severity", "file", "line", "evidence", "recommendation"]
    assert "benchmark_deltas" in verify

    assert main(["--store-dir", str(store), "cleanup", run_id]) == 0
    assert "removed:" in capsys.readouterr().out

    assert main(["--store-dir", str(store), "replay", run_id]) == 0
    replay_output = capsys.readouterr().out
    assert "completed" in replay_output

    before_verify = _tree_bytes(store / "runs" / run_id)
    assert main(["--store-dir", str(store), "replay", run_id, "--verify", "--json"]) == 0
    first_verify = capsys.readouterr().out
    assert main(["--store-dir", str(store), "replay", run_id, "--verify", "--json"]) == 0
    second_verify = capsys.readouterr().out
    after_verify = _tree_bytes(store / "runs" / run_id)
    assert first_verify == second_verify
    assert before_verify == after_verify
    assert json.loads(first_verify)["verification"]["verified"] is True

    monkeypatch.delenv("POOR_CLI_PLANNER_COMMAND", raising=False)
    old_offline = os.environ.get("POOR_CLI_OFFLINE")
    try:
        assert main(["--offline", "--store-dir", str(store), "replay", run_id, "--verify", "--json"]) == 0
        offline_replay = json.loads(capsys.readouterr().out)
        assert offline_replay["verification"]["verified"] is True
    finally:
        if old_offline is None:
            os.environ.pop("POOR_CLI_OFFLINE", None)
        else:
            os.environ["POOR_CLI_OFFLINE"] = old_offline


def test_cli_exposes_tui_help(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(tmp_path / "store"), "tui", "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--run-id" in result.stdout


def test_doctor_reports_graph_dependencies(tmp_path: Path, capsys) -> None:
    assert main(["--store-dir", str(tmp_path / "store"), "doctor"]) == 0
    output = capsys.readouterr().out

    assert "graph:python:" in output
    assert "tree_sitter_python" in output
    assert main(["--store-dir", str(tmp_path / "store"), "agents", "doctor"]) == 0
    assert "graph:python:" in capsys.readouterr().out


def test_cli_sets_offline_env(capsys) -> None:
    old = os.environ.get("POOR_CLI_OFFLINE")
    os.environ.pop("POOR_CLI_OFFLINE", None)

    try:
        assert main(["--offline", "--version"]) == 0

        assert os.environ["POOR_CLI_OFFLINE"] == "1"
        assert capsys.readouterr().out.strip() == "6.0.0a1"
    finally:
        if old is None:
            os.environ.pop("POOR_CLI_OFFLINE", None)
        else:
            os.environ["POOR_CLI_OFFLINE"] = old


def test_cli_runs_filters_by_prefix(tmp_path: Path, capsys) -> None:
    store = RunStore(tmp_path / "store")
    first = store.create_run(user_goal="alpha fix parser", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    store.create_run(user_goal="beta fix tools", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    store.close()

    assert main(["--store-dir", str(tmp_path / "store"), "runs", "--prefix", "alpha"]) == 0
    output = capsys.readouterr().out

    assert first in output
    assert "beta fix tools" not in output


def test_cli_plan_graph_stores_graph_prompt_bias(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Trace','objective':'trace symbols','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(store), "plan", "trace parser flow", "--graph", "--json"]) == 0
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    run_store = RunStore(store)
    try:
        prompt_artifact = run_store.list_artifacts(run_id, "planner.prompt")[0]
        prompt = run_store.artifact_payload(prompt_artifact["artifact_id"]).decode()
        plan_events = [event for event in run_store.list_events(run_id) if event["type"] == "plan.created"]
        route_events = [event for event in run_store.list_events(run_id) if event["type"] == "route.selected"]
        assert "Graph mode:" in prompt
        assert "find_symbol" in prompt
        assert "subgraph" in prompt
        assert plan_events[0]["payload"]["graph_mode"] is True
        assert route_events
        assert route_events[0]["payload"]["role"] == "executor"
    finally:
        run_store.close()


def test_cli_run_graph_stores_graph_agent_prompt(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "src" / "parser.py"
    source.parent.mkdir()
    source.write_text("def parse_flow(value):\n    return value\n", encoding="utf-8")
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Trace','objective':'trace symbols','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(store), "run", "trace parse flow", "--graph", "--yes"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    run_store = RunStore(store)
    try:
        task = run_store.list_tasks(run_id)[0]
        agent_input = json.loads(run_store.artifact_payload(run_store.list_artifacts(run_id, "agent.input")[0]["artifact_id"]))
        graph_context = json.loads(run_store.artifact_payload(run_store.list_artifacts(run_id, "graph.context")[0]["artifact_id"]))
        assert task["metadata"]["graph_mode"] is True
        assert graph_context["available"] is True
        assert any(symbol["name"] == "parse_flow" for symbol in graph_context["symbols"])
        assert "Graph mode:" in agent_input["prompt"]
        assert "symbol parse_flow" in agent_input["prompt"]
        assert "find_symbol" in agent_input["prompt"]
        assert "subgraph" in agent_input["prompt"]
    finally:
        run_store.close()


def test_cli_run_graph_replays_offline(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Trace','objective':'trace symbols','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(store), "run", "trace parser flow", "--graph", "--yes"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    run_store = RunStore(store)
    try:
        assert run_store.list_tasks(run_id)[0]["metadata"]["graph_mode"] is True
    finally:
        run_store.close()

    monkeypatch.delenv("POOR_CLI_PLANNER_COMMAND", raising=False)
    old_offline = os.environ.get("POOR_CLI_OFFLINE")
    try:
        assert main(["--offline", "--store-dir", str(store), "replay", run_id, "--verify", "--json"]) == 0
        offline_replay = json.loads(capsys.readouterr().out)
        assert offline_replay["verification"]["verified"] is True
    finally:
        if old_offline is None:
            os.environ.pop("POOR_CLI_OFFLINE", None)
        else:
            os.environ["POOR_CLI_OFFLINE"] = old_offline


def test_cli_run_executes_generic_command_metadata(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    command = f"{sys.executable} -c \"from pathlib import Path; Path('fixed.txt').write_text('ok')\""
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        f"command = {command!r}\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Fix','objective':'write file','suggested_agent':'generic','command':command}],"
        "'validation_strategy':['check file'],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "run", "fixture bug", "--yes"]) == 0

    assert (tmp_path / "fixed.txt").read_text(encoding="utf-8") == "ok"
    assert "run_id:" in capsys.readouterr().out


def test_cli_run_local_provider_agent_records_result(tmp_path: Path, monkeypatch, capsys) -> None:
    class FakeProvider:
        def call(self, request):
            return ProviderResponse(provider=request.provider, model=request.model, content="local guidance")

    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Local','objective':'ask local model','suggested_agent':'local'}],"
        "'validation_strategy':[],'routing_strategy':'local','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")
    monkeypatch.setenv("POOR_CLI_PROVIDER", "vllm")
    monkeypatch.setenv("POOR_CLI_MODEL", "qwen")
    monkeypatch.setenv("POOR_CLI_LOCAL_BASE_URL", "http://vllm.test")
    monkeypatch.setattr("poor_cli.agents._provider_for_agent", lambda agent: FakeProvider())

    assert main(["--store-dir", str(store), "run", "local goal", "--yes"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    run_store = RunStore(store)
    try:
        result_artifact = run_store.list_artifacts(run_id, "agent.result")[0]
        result = json.loads(run_store.artifact_payload(result_artifact["artifact_id"]))
        assert result["stdout"] == "local guidance"
        assert result["command"] == ["local-provider", "vllm", "qwen", "http://vllm.test"]
        assert run_store.get_run(run_id)["status"] == "completed"
    finally:
        run_store.close()


def test_cli_review_run_uses_reviewer_route_and_writes_artifact(tmp_path: Path, monkeypatch, capsys) -> None:
    class FakeProvider:
        def call(self, request):
            return ProviderResponse(
                provider=request.provider,
                model=request.model,
                content=json.dumps({"findings": [], "recommendation": "accept"}),
                raw={"usage": {"input_tokens": 100, "output_tokens": 20}},
            )

    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    profile = provider_preset("openai-compatible", profile_id="reviewer", model="review-model", base_url="http://review.test")
    config = add_provider(config, "reviewer", profile["reviewer"])
    config["routes"] = {"reviewer": {"profile": "reviewer", "model": "review-model"}}
    save_repo_config(config, tmp_path)
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")
    monkeypatch.setattr("poor_cli.lanes._provider_for_agent", lambda agent: FakeProvider())

    assert main(["--store-dir", str(store), "run", "review goal", "--yes"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    assert main(["--store-dir", str(store), "review-run", run_id]) == 0

    run_store = RunStore(store)
    try:
        review = json.loads((store / "runs" / run_id / "artifacts" / "review" / "REVIEW.json").read_text(encoding="utf-8"))
        assert review["schema_version"] == "poor-cli-review-v1"
        assert review["recommendation"] == "accept"
        assert run_store.list_artifacts(run_id, "budget.ledger")
        assert any(event["type"] == "review.completed" for event in run_store.list_events(run_id))
    finally:
        run_store.close()


def test_cli_review_run_rejects_and_suppresses_findings(tmp_path: Path, monkeypatch, capsys) -> None:
    class FakeProvider:
        def call(self, request):
            return ProviderResponse(
                provider=request.provider,
                model=request.model,
                content=json.dumps(
                    {
                        "findings": [
                            {
                                "id": "rev_known",
                                "severity": "high",
                                "file": "a.py",
                                "line": 1,
                                "evidence": "bad patch",
                                "recommendation": "fix",
                            }
                        ],
                        "recommendation": "reject",
                    }
                ),
            )

    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = empty_config()
    profile = provider_preset("openai-compatible", profile_id="reviewer", model="review-model", base_url="http://review.test")
    config = add_provider(config, "reviewer", profile["reviewer"])
    config["routes"] = {"reviewer": {"profile": "reviewer", "model": "review-model"}}
    save_repo_config(config, tmp_path)
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")
    monkeypatch.setattr("poor_cli.lanes._provider_for_agent", lambda agent: FakeProvider())

    assert main(["--store-dir", str(store), "run", "review goal", "--yes"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    assert main(["--store-dir", str(store), "review-run", run_id]) == 2
    rejected = json.loads((store / "runs" / run_id / "artifacts" / "review" / "REVIEW.json").read_text(encoding="utf-8"))
    assert rejected["recommendation"] == "reject"
    assert (
        main(
            [
                "--store-dir",
                str(store),
                "review-run",
                run_id,
                "--suppress-finding",
                "rev_known",
                "--reason",
                "false positive",
                "--expires",
                "2026-12-31",
            ]
        )
        == 0
    )
    suppressed = json.loads((store / "runs" / run_id / "artifacts" / "review" / "REVIEW.json").read_text(encoding="utf-8"))
    assert suppressed["recommendation"] == "accept"
    assert suppressed["findings"][0]["suppressed"] is True


def test_review_run_fusion_requires_budget_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    store = RunStore(tmp_path / "store")
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    config = empty_config()
    profile = provider_preset("openrouter", profile_id="router", model="openrouter/fusion")
    config = add_provider(config, "router", profile["router"])
    config["routes"] = {"reviewer": {"profile": "router", "model": "openrouter/fusion"}}
    save_repo_config(config, tmp_path)

    try:
        with pytest.raises(LaneError, match="Fusion review requires"):
            review_run(store, run_id)
    finally:
        store.close()


def test_cli_verify_run_executes_validation_command(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    command = f"{sys.executable} -c \"from pathlib import Path; Path('fixed.txt').write_text('ok')\""
    verify_command = f"{sys.executable} -c \"from pathlib import Path; assert Path('fixed.txt').read_text() == 'ok'\""
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        f"command = {command!r}\n"
        f"verify_command = {verify_command!r}\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Fix','objective':'write file','suggested_agent':'generic','command':command,"
        "'validation':[verify_command]}],"
        "'validation_strategy':[verify_command],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(store), "run", "verify goal", "--yes"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    assert main(["--store-dir", str(store), "verify-run", run_id]) == 0

    verify = json.loads((store / "runs" / run_id / "artifacts" / "verify" / "VERIFY.json").read_text(encoding="utf-8"))
    assert verify["schema_version"] == "poor-cli-verify-v1"
    assert verify["pass"] is True
    assert verify["commands"][0]["returncode"] == 0


def test_cli_verify_run_reports_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(store), "run", "verify goal", "--yes"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    assert main(["--store-dir", str(store), "verify-run", run_id, "--command", "false"]) == 1

    verify = json.loads((store / "runs" / run_id / "artifacts" / "verify" / "VERIFY.json").read_text(encoding="utf-8"))
    assert verify["pass"] is False
    assert verify["commands"][0]["returncode"] == 1


def test_cli_run_without_yes_records_confirmation_event(tmp_path: Path) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':[{'title':'Record','objective':'record execution','suggested_agent':'generic'}],"
        "'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{'tokens':None,'usd':None}}))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["POOR_CLI_PLANNER_COMMAND"] = f"{sys.executable} {planner}"
    store = tmp_path / "store"

    result = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "run", "test goal"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    run_id = next(line.split(":", 1)[1].strip() for line in result.stdout.splitlines() if line.startswith("run_id:"))
    run_store = RunStore(store)
    try:
        events = [event["type"] for event in run_store.list_events(run_id)]
        assert result.returncode == 1
        assert "run.confirmation_required" in events
        assert "agent.started" not in events
        assert run_store.get_run(run_id)["status"] == "awaiting_confirmation"
    finally:
        run_store.close()


def test_cli_plan_failure_records_structured_events(tmp_path: Path) -> None:
    planner = tmp_path / "planner.py"
    planner.write_text("import sys\nsys.stderr.write('planner broke')\nsys.exit(2)\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["POOR_CLI_PLANNER_COMMAND"] = f"{sys.executable} {planner}"
    store = tmp_path / "store"

    result = subprocess.run(
        [sys.executable, "-m", "poor_cli", "--store-dir", str(store), "plan", "test goal"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    run_store = RunStore(store)
    try:
        run = run_store.list_runs()[0]
        events = [event["type"] for event in run_store.list_events(run["run_id"])]
        assert result.returncode == 1
        assert run["status"] == "failed"
        assert "planner.failed" in events
        assert "run.failed" in events
        assert run_store.list_artifacts(run["run_id"], "planner.error")
    finally:
        run_store.close()


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}
