import signal
from pathlib import Path

from poor_cli.task_manager import TaskManager
from poor_cli import task_supervisor


def test_spawn_detached_returns_task_and_writes_pid_file(tmp_path, monkeypatch):
    class FakeProcess:
        pid = 43210

    monkeypatch.setattr("poor_cli.task_manager.subprocess.Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(TaskManager, "_is_git_repo", lambda self: False)
    monkeypatch.setattr(TaskManager, "_pid_is_running", lambda self, pid: True)
    manager = TaskManager(tmp_path)

    task = manager.spawn_detached(prompt="inspect", sandbox_preset="read-only")

    assert task.task_id
    assert task.status == "running"
    assert Path(task.artifact_dir, "pid").read_text(encoding="utf-8") == "43210"
    assert Path(task.artifact_dir, "task.json").is_file()
    assert Path(task.log_path).name == "log.ndjson"


def test_attach_to_yields_supervisor_and_event_lines(tmp_path):
    manager = TaskManager(tmp_path)
    task = manager.create_task(title="x", prompt="x", sandbox_preset="read-only", source="test")
    Path(task.log_path).write_text('{"event":"supervisor_started"}\n', encoding="utf-8")
    Path(task.events_path).write_text('{"type":"done"}\n', encoding="utf-8")

    lines = list(manager.attach_to(task.task_id))

    assert lines == ['{"event":"supervisor_started"}', '{"type":"done"}']


def test_cancel_sends_term_then_kill(tmp_path, monkeypatch):
    class FakeProcess:
        pid = 444

    monkeypatch.setattr("poor_cli.task_manager.subprocess.Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(TaskManager, "_is_git_repo", lambda self: False)
    monkeypatch.setattr(TaskManager, "_pid_is_running", lambda self, pid: True)
    manager = TaskManager(tmp_path)
    task = manager.spawn_detached(prompt="inspect", sandbox_preset="read-only")
    signals = []
    monkeypatch.setattr(manager, "_signal_task_process_group", lambda pid, sig: signals.append((pid, sig)) or True)

    cancelled = manager.cancel(task.task_id, grace_timeout=0)

    assert cancelled.status == "cancelled"
    assert signals == [(444, signal.SIGTERM), (444, signal.SIGKILL)]


def test_prune_removes_matching_task_dirs_only(tmp_path):
    manager = TaskManager(tmp_path)
    completed = manager.create_task(title="done", prompt="done", sandbox_preset="read-only", source="test")
    running = manager.create_task(title="run", prompt="run", sandbox_preset="read-only", source="test")
    manager.mark_completed(completed.task_id, summary="done")

    removed = manager.prune(status="completed", older_than_days=0)

    assert removed == [completed.task_id]
    assert manager.get_task(completed.task_id) is None
    assert manager.get_task(running.task_id) is not None
    assert not Path(completed.artifact_dir).exists()


def test_supervisor_writes_ndjson_lines(tmp_path, monkeypatch, capsys):
    manager = TaskManager(tmp_path)
    task = manager.create_task(title="x", prompt="x", sandbox_preset="read-only", source="test")

    async def fake_worker(**kwargs):
        assert kwargs["repo_root"] == tmp_path.resolve()
        assert kwargs["task_id"] == task.task_id
        return 0

    monkeypatch.setattr(task_supervisor, "TaskManager", lambda repo_root: manager)
    monkeypatch.setattr(task_supervisor, "run_task_worker", fake_worker)

    code = task_supervisor.main(["--task-id", task.task_id, "--repo-root", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "supervisor_started" in out
    assert "supervisor_finished" in out


def test_task_run_parser_accepts_detach_flag():
    from poor_cli.__main__ import _build_task_parser

    parser = _build_task_parser()
    args = parser.parse_args(["run", "--detach", "--prompt", "inspect"])

    assert args.detach is True
    assert args.prompt == "inspect"
