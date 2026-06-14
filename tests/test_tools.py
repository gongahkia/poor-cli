from __future__ import annotations

from pathlib import Path

import pytest

from poor_cli.store import RunStore
from poor_cli.tools import ToolDispatcher, ToolReplayMiss


def _run_id(store: RunStore, root: Path) -> str:
    return store.create_run(user_goal="goal", repo_path=root, git_commit_start="abc", mode="balanced", budget={})


def test_builtin_tools_cover_v0_surface(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    dispatcher = ToolDispatcher(store, run_id, workdir=tmp_path)

    written = dispatcher.call("write_file", {"path": "src/example.txt", "content": "hello world\n"})
    read = dispatcher.call("read_file", {"path": "src/example.txt"})
    edited = dispatcher.call("edit", {"path": "src/example.txt", "old": "world", "new": "poor-cli"})
    globbed = dispatcher.call("glob", {"pattern": "src/*.txt"})
    grepped = dispatcher.call("grep", {"pattern": "poor-cli", "glob": "src/*.txt"})
    shell = dispatcher.call("shell", {"command": "printf shell-ok"})
    emitted = dispatcher.call("replay_emit", {"value": {"ok": True}})

    assert written.ok is True
    assert read.output["content"] == "hello world\n"
    assert edited.output["replacements"] == 1
    assert globbed.output["matches"] == ["src/example.txt"]
    assert grepped.output["matches"][0]["line"] == 1
    assert shell.output["stdout"] == "shell-ok"
    assert emitted.output["value"] == {"ok": True}
    assert len(store.list_artifacts(run_id, "tool.result")) == 7
    store.close()


def test_tool_dispatcher_replays_cached_result_without_execution(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)
    path = tmp_path / "note.txt"
    path.write_text("original", encoding="utf-8")

    first = ToolDispatcher(store, run_id, workdir=tmp_path).call("read_file", {"path": "note.txt"})
    path.write_text("changed", encoding="utf-8")
    replayed = ToolDispatcher(store, run_id, workdir=tmp_path, replay_only=True).call("read_file", {"path": "note.txt"})

    assert first.output["content"] == "original"
    assert replayed.output["content"] == "original"
    assert replayed.cached is True
    store.close()


def test_tool_dispatcher_fails_closed_on_replay_miss(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "store")
    run_id = _run_id(store, tmp_path)

    with pytest.raises(ToolReplayMiss):
        ToolDispatcher(store, run_id, workdir=tmp_path, replay_only=True).call("replay_emit", {"value": "missing"})

    assert store.list_events(run_id)[0]["type"] == "tool.cache_miss"
    store.close()
