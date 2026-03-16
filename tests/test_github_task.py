import json
import subprocess
from pathlib import Path

from poor_cli.github_task import (
    build_task_prompt,
    create_task_from_context,
    default_mode_for_context,
    load_github_context,
)
from poor_cli.task_manager import TaskManager


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


def test_load_pull_request_context_and_create_task(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    payload = {
        "repository": {"full_name": "acme/poor-cli"},
        "pull_request": {
            "number": 42,
            "title": "Improve task runner",
            "body": "Adds more durable task handling.",
            "html_url": "https://github.com/acme/poor-cli/pull/42",
            "user": {"login": "octocat"},
            "base": {"ref": "main"},
            "head": {"ref": "feature/tasks"},
        },
    }
    event_path = tmp_path / "pull_request.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")

    context = load_github_context(event_path, env={"GITHUB_EVENT_NAME": "pull_request"})
    assert context.kind == "pull_request"
    assert default_mode_for_context(context) == "review-only"

    prompt = build_task_prompt(context, mode="review-only")
    assert "Stay in review mode" in prompt
    assert "Base ref: main" in prompt
    assert "Head ref: feature/tasks" in prompt

    manager = TaskManager(repo_root)
    task = create_task_from_context(
        manager,
        context,
        auto_start=False,
        metadata={"execution": {"provider": "openai", "model": "gpt-5"}},
    )
    assert task.sandbox_preset == "review-only"
    assert task.source == "github"
    assert task.metadata["kind"] == "pull_request"
    assert task.metadata["execution"] == {"provider": "openai", "model": "gpt-5"}


def test_load_issue_context_defaults_to_read_only(tmp_path: Path):
    payload = {
        "repository": {"full_name": "acme/poor-cli"},
        "issue": {
            "number": 7,
            "title": "Document automations",
            "body": "Need a CLI example.",
            "html_url": "https://github.com/acme/poor-cli/issues/7",
            "user": {"login": "octocat"},
        },
    }
    event_path = tmp_path / "issue.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")

    context = load_github_context(event_path, env={"GITHUB_EVENT_NAME": "issues"})

    assert context.kind == "issue"
    assert default_mode_for_context(context) == "read-only"
    assert "Summarize relevant code areas" in build_task_prompt(context, mode="read-only")
