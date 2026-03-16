import json
import subprocess
import sys
from pathlib import Path

import pytest

from poor_cli import __main__ as cli_main


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


def test_automation_create_json(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "poor-cli",
            "automation",
            "create",
            "--name",
            "Daily QA",
            "--prompt",
            "Run QA checklist",
            "--every-minutes",
            "60",
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["name"] == "Daily QA"
    assert payload["scheduleSummary"] == "every 60 minute(s)"
    assert payload["sandboxPreset"] == "read-only"


def test_task_create_json_includes_execution_metadata(monkeypatch, capsys, tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "poor-cli",
            "task",
            "create",
            "--title",
            "Deep review",
            "--prompt",
            "Review the repository",
            "--preset",
            "workspace-write",
            "--auto-approve",
            "--no-auto-start",
            "--provider",
            "openai",
            "--model",
            "gpt-5",
            "--config",
            ".poor-cli/task-config.yaml",
            "--context-file",
            "README.md",
            "--pinned-context-file",
            "docs/PLAN.md",
            "--context-budget-tokens",
            "4096",
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "queued"
    assert payload["approvedAt"] is not None
    assert payload["branchName"].startswith("codex/poor-cli-task-")
    assert payload["metadata"]["autoApprove"] is True
    assert payload["metadata"]["execution"] == {
        "provider": "openai",
        "model": "gpt-5",
        "configPath": ".poor-cli/task-config.yaml",
        "contextFiles": ["README.md"],
        "pinnedContextFiles": ["docs/PLAN.md"],
        "contextBudgetTokens": 4096,
    }


def test_automation_create_json_includes_execution_metadata(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "poor-cli",
            "automation",
            "create",
            "--name",
            "Patch repo",
            "--prompt",
            "Apply the requested patch",
            "--every-minutes",
            "30",
            "--preset",
            "workspace-write",
            "--auto-approve",
            "--provider",
            "openai",
            "--model",
            "gpt-5",
            "--context-file",
            "README.md",
            "--context-budget-tokens",
            "2048",
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["sandboxPreset"] == "workspace-write"
    assert payload["requiresApproval"] is False
    assert payload["metadata"]["autoApprove"] is True
    assert payload["metadata"]["execution"] == {
        "provider": "openai",
        "model": "gpt-5",
        "contextFiles": ["README.md"],
        "contextBudgetTokens": 2048,
    }


def test_github_task_create_json(monkeypatch, capsys, tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _init_git_repo(repo_root)

    payload = {
        "repository": {"full_name": "acme/poor-cli"},
        "pull_request": {
            "number": 3,
            "title": "Tighten help docs",
            "body": "Sync command docs.",
            "html_url": "https://github.com/acme/poor-cli/pull/3",
            "user": {"login": "octocat"},
            "base": {"ref": "main"},
            "head": {"ref": "docs/help"},
        },
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "poor-cli",
            "github-task",
            "create",
            "--event-path",
            str(event_path),
            "--mode",
            "review-only",
            "--no-auto-start",
            "--provider",
            "openai",
            "--model",
            "gpt-5",
            "--context-file",
            "README.md",
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0
    result = json.loads(capsys.readouterr().out.strip())
    assert result["task"]["sandboxPreset"] == "review-only"
    assert result["task"]["source"] == "github"
    assert result["task"]["metadata"]["execution"] == {
        "provider": "openai",
        "model": "gpt-5",
        "contextFiles": ["README.md"],
    }
    assert result["context"]["kind"] == "pull_request"
