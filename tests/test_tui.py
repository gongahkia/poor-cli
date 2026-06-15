from __future__ import annotations

import sys
from pathlib import Path

from poor_cli.config import add_provider, empty_config, load_config, provider_preset, save_repo_config
from poor_cli.store import RunStore
from poor_cli.tui import handle_tui_command, render_artifact_panel, render_provider_panel, render_run_graph_panel


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


def test_tui_panels_render_provider_graph_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    config = empty_config()
    profile = provider_preset("openai", profile_id="openai", model="gpt-5.5")
    config = add_provider(config, "openai", profile["openai"])
    save_repo_config(config, tmp_path)
    store_dir = tmp_path / "store"
    store = RunStore(store_dir)
    run_id = store.create_run(user_goal="goal", repo_path=tmp_path, git_commit_start="abc", mode="balanced", budget={})
    store.put_artifact(run_id=run_id, kind="artifact.plan.md", data="# Plan\n", media_type="text/markdown")
    store.close()
    monkeypatch.chdir(tmp_path)

    provider = render_provider_panel(store_dir, tmp_path)
    graph = render_run_graph_panel(store_dir, run_id)
    artifacts = render_artifact_panel(store_dir, run_id)

    assert "openai" in provider
    assert "gpt-5.5" in provider
    assert "run graph" in graph
    assert "artifacts" in artifacts


def test_tui_route_switcher_uses_validated_config(tmp_path: Path, monkeypatch) -> None:
    config = empty_config()
    profile = provider_preset("openai", profile_id="openai", model="gpt-5.5")
    config = add_provider(config, "openai", profile["openai"])
    save_repo_config(config, tmp_path)
    monkeypatch.chdir(tmp_path)

    result = handle_tui_command(
        tmp_path / "store",
        "route set --role reviewer --profile openai --model gpt-5.5",
        repo_path=tmp_path,
    )

    assert result.run_id is None
    assert "route reviewer" in result.message
    assert load_config(tmp_path, include_env=False)["routes"]["reviewer"] == {"model": "gpt-5.5", "profile": "openai"}
