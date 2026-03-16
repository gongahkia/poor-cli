from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

from poor_cli.automation_manager import AutomationManager, parse_daily_schedule, schedule_interval


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


def test_automation_manager_creates_and_lists_automations(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = AutomationManager(repo_root)
    automation = manager.create_automation(
        name="Daily QA",
        prompt="Run the QA checklist",
        schedule=parse_daily_schedule("09:30"),
        sandbox_preset="review-only",
    )

    assert automation.enabled is True
    assert automation.next_run_at is not None
    listed = manager.list_automations()
    assert len(listed) == 1
    assert listed[0].automation_id == automation.automation_id
    assert listed[0].to_dict()["scheduleSummary"] == "daily at 09:30 UTC"


def test_automation_manager_run_due_creates_task_records(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = AutomationManager(repo_root)
    automation = manager.create_automation(
        name="Repo review",
        prompt="Inspect current changes and summarize risks",
        schedule=schedule_interval(60),
        sandbox_preset="review-only",
        requires_approval=True,
        metadata={"execution": {"provider": "openai", "model": "gpt-5"}},
    )

    due_time = datetime.fromisoformat(automation.next_run_at).astimezone(timezone.utc) + timedelta(seconds=1)
    tasks = manager.run_due(now=due_time)

    assert len(tasks) == 1
    assert tasks[0].status == "awaiting_approval"
    assert tasks[0].source == "automation"
    assert tasks[0].metadata["automationId"] == automation.automation_id
    assert tasks[0].metadata["execution"] == {"provider": "openai", "model": "gpt-5"}

    updated = manager.get_automation(automation.automation_id)
    assert updated is not None
    assert updated.last_task_id == tasks[0].task_id
    assert updated.last_run_at is not None
    assert datetime.fromisoformat(updated.next_run_at).astimezone(timezone.utc) > due_time


def test_automation_manager_disable_clears_next_run(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = AutomationManager(repo_root)
    automation = manager.create_automation(
        name="Nightly read-only",
        prompt="Summarize repository drift",
        schedule=schedule_interval(120),
        sandbox_preset="read-only",
    )

    disabled = manager.set_enabled(automation.automation_id, False)
    assert disabled.enabled is False
    assert disabled.next_run_at is None

    enabled = manager.set_enabled(automation.automation_id, True)
    assert enabled.enabled is True
    assert enabled.next_run_at is not None


def test_workspace_write_automation_requires_approval_by_default(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = AutomationManager(repo_root)
    automation = manager.create_automation(
        name="Patch repo",
        prompt="Apply the requested patch",
        schedule=schedule_interval(30),
        sandbox_preset="workspace-write",
    )

    assert automation.requires_approval is True
    assert automation.metadata == {}


def test_workspace_write_automation_auto_approve_disables_manual_gate(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    manager = AutomationManager(repo_root)
    automation = manager.create_automation(
        name="Patch repo",
        prompt="Apply the requested patch",
        schedule=schedule_interval(30),
        sandbox_preset="workspace-write",
        auto_approve=True,
    )

    assert automation.requires_approval is False
    assert automation.metadata["autoApprove"] is True
