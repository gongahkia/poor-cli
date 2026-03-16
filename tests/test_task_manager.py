from types import SimpleNamespace
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from poor_cli.task_manager import TaskManager
from poor_cli.task_manager import run_task_worker


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.name", "Poor CLI Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_task_manager_creates_durable_task_records(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = TaskManager(repo_root)
    task = manager.create_task(
        title="Review auth flow",
        prompt="Inspect auth flow changes",
        sandbox_preset="workspace-write",
        source="manual",
        requires_approval=True,
    )

    assert task.status == "awaiting_approval"
    assert task.branch_name.startswith("codex/poor-cli-task-")
    assert (repo_root / ".poor-cli" / "tasks" / "tasks.db").is_file()
    assert Path(task.artifact_dir).is_dir()
    assert Path(task.worktree_path).is_dir()
    assert str(repo_root / ".poor-cli" / "worktrees") in task.worktree_path

    loaded = manager.get_task(task.task_id)
    assert loaded is not None
    assert loaded.task_id == task.task_id
    assert loaded.metadata == {}


def test_task_manager_auto_approve_bypasses_workspace_write_gate(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = TaskManager(repo_root)
    task = manager.create_task(
        title="Apply safe fix",
        prompt="Patch the failing test",
        sandbox_preset="workspace-write",
        source="manual",
        auto_approve=True,
    )

    assert task.status == "queued"
    assert task.approved_at is not None
    assert task.metadata["autoApprove"] is True


def test_task_manager_start_process_passes_execution_config(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = TaskManager(repo_root)
    task = manager.create_task(
        title="Review repo",
        prompt="Review the current repo",
        sandbox_preset="review-only",
        source="manual",
        metadata={"execution": {"configPath": ".poor-cli/task-config.yaml"}},
    )

    fake_process = SimpleNamespace(pid=4242)
    with patch("poor_cli.task_manager.subprocess.Popen", return_value=fake_process) as popen_mock:
        started = manager.start_task_process(task.task_id)

    argv = popen_mock.call_args.args[0]
    assert started.status == "running"
    assert started.worker_pid == 4242
    assert argv[1:7] == ["-m", "poor_cli", "task", "run", "--task-id", task.task_id]
    assert "--repo-root" in argv
    assert "--config" in argv
    assert ".poor-cli/task-config.yaml" in argv


@pytest.mark.asyncio
async def test_run_task_worker_uses_execution_overrides(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "PLAN.md").write_text("plan\n", encoding="utf-8")

    manager = TaskManager(repo_root)
    task = manager.create_task(
        title="Deep review",
        prompt="Review the repository",
        sandbox_preset="review-only",
        source="manual",
        metadata={
            "execution": {
                "provider": "openai",
                "model": "gpt-5",
                "contextFiles": ["README.md"],
                "pinnedContextFiles": ["docs/PLAN.md"],
                "contextBudgetTokens": 2048,
            }
        },
    )

    captured = {}

    class FakeCore:
        def __init__(self, config_path=None):
            captured["config_path"] = config_path
            self.tool_registry = object()

        async def initialize(self, provider_name=None, model_name=None):
            captured["initialize"] = {
                "provider_name": provider_name,
                "model_name": model_name,
            }

        async def send_message_events(
            self,
            message,
            context_files=None,
            pinned_context_files=None,
            context_budget_tokens=None,
            request_id="",
        ):
            captured["send_message_events"] = {
                "message": message,
                "context_files": context_files,
                "pinned_context_files": pinned_context_files,
                "context_budget_tokens": context_budget_tokens,
                "request_id": request_id,
            }
            yield SimpleNamespace(type="text_chunk", data={"chunk": "review complete"})
            yield SimpleNamespace(type="done", data={"status": "done"})

        async def shutdown(self):
            captured["shutdown"] = True

    with patch("poor_cli.task_manager.PoorCLICore", FakeCore):
        exit_code = await run_task_worker(
            repo_root=repo_root,
            task_id=task.task_id,
        )

    assert exit_code == 0
    assert captured["initialize"] == {
        "provider_name": "openai",
        "model_name": "gpt-5",
    }
    assert captured["send_message_events"] == {
        "message": "Review the repository",
        "context_files": ["README.md"],
        "pinned_context_files": ["docs/PLAN.md"],
        "context_budget_tokens": 2048,
        "request_id": f"task-{task.task_id}",
    }
    assert Path(task.response_path).read_text(encoding="utf-8") == "review complete"
    loaded = manager.get_task(task.task_id)
    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.summary


def test_task_manager_approve_and_cancel_update_status(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = TaskManager(repo_root)
    task = manager.create_task(
        title="Lint repo",
        prompt="Run lint",
        sandbox_preset="workspace-write",
        source="manual",
        requires_approval=True,
    )

    approved = manager.approve_task(task.task_id, auto_start=False)
    assert approved.status == "queued"
    assert approved.approved_at is not None

    cancelled = manager.cancel_task(task.task_id)
    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    assert cancelled.error_message == "cancelled by user"
