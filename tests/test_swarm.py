from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from poor_cli.cli import main
from poor_cli.store import RunStore


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)


def _repo(path: Path) -> Path:
    repo = path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    return repo


def _planner(path: Path, tasks: list[dict[str, object]]) -> None:
    path.write_text(
        "import json, sys\nsys.stdin.read()\n"
        f"tasks = {tasks!r}\n"
        "print(json.dumps({'problem_summary':'s','architecture_assessment':'a','assumptions':[],"
        "'risks':[],'tasks':tasks,'validation_strategy':[],'routing_strategy':'generic','estimated_cost':{}}))\n",
        encoding="utf-8",
    )


def test_run_swarm_collects_patch_without_modifying_main(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _repo(tmp_path)
    planner = tmp_path / "planner.py"
    cmd = f"{sys.executable} -c \"from pathlib import Path; Path('a.txt').write_text('worker\\\\n')\""
    _planner(planner, [{"title": "Edit A", "objective": "edit", "suggested_agent": "generic", "command": cmd}])
    monkeypatch.chdir(repo)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "run-swarm", "swarm goal", "--parallel", "2"]) == 0
    run_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))

    assert (repo / "a.txt").read_text(encoding="utf-8") == "base\n"
    merge = json.loads((tmp_path / "store" / "runs" / run_id / "artifacts" / "merge" / "MERGE_PLAN.json").read_text(encoding="utf-8"))
    assert merge["policy"] == "collect-only"
    assert merge["ordered_patches"]
    assert main(["--store-dir", str(tmp_path / "store"), "cleanup-swarm", run_id]) == 0


def test_run_swarm_refuses_dirty_main_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    planner = tmp_path / "planner.py"
    _planner(planner, [{"title": "Noop", "objective": "noop", "suggested_agent": "generic"}])
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "run-swarm", "dirty"]) == 1
    store = RunStore(tmp_path / "store")
    try:
        run_id = store.list_runs()[0]["run_id"]
        assert any(event["type"] == "swarm.refused" for event in store.list_events(run_id))
    finally:
        store.close()


def test_run_swarm_records_conflicts(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _repo(tmp_path)
    planner = tmp_path / "planner.py"
    first = f"{sys.executable} -c \"from pathlib import Path; Path('a.txt').write_text('one\\\\n')\""
    second = f"{sys.executable} -c \"from pathlib import Path; Path('a.txt').write_text('two\\\\n')\""
    _planner(
        planner,
        [
            {"title": "One", "objective": "one", "suggested_agent": "generic", "command": first},
            {"title": "Two", "objective": "two", "suggested_agent": "generic", "command": second},
        ],
    )
    monkeypatch.chdir(repo)
    monkeypatch.setenv("POOR_CLI_PLANNER_COMMAND", f"{sys.executable} {planner}")

    assert main(["--store-dir", str(tmp_path / "store"), "run-swarm", "conflict", "--allow-overlap"]) == 0
    clean_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    assert not json.loads((tmp_path / "store" / "runs" / clean_id / "artifacts" / "merge" / "MERGE_PLAN.json").read_text())["conflicts"]

    assert main(["--store-dir", str(tmp_path / "store2"), "run-swarm", "conflict"]) == 1
    conflict_id = next(line.split(":", 1)[1].strip() for line in capsys.readouterr().out.splitlines() if line.startswith("run_id:"))
    merge = json.loads((tmp_path / "store2" / "runs" / conflict_id / "artifacts" / "merge" / "MERGE_PLAN.json").read_text())
    assert merge["conflicts"][0]["resolution"] == "review-task"
