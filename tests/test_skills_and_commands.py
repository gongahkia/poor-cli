from pathlib import Path

from poor_cli.custom_commands import CustomCommandRegistry
from poor_cli.skills import SkillRegistry


def test_repo_skill_precedes_user_skill(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo_skill = repo_root / ".poor-cli" / "skills" / "triage"
    repo_skill.mkdir(parents=True)
    (repo_skill / "SKILL.md").write_text(
        "# Triage\nRepo skill description\n",
        encoding="utf-8",
    )
    (repo_skill / "assets").mkdir()
    (repo_skill / "scripts").mkdir()

    user_skill = tmp_path / ".poor-cli" / "skills" / "triage"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text(
        "# Triage\nUser skill description\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("poor_cli.skills.Path.home", lambda: tmp_path)

    registry = SkillRegistry(repo_root)
    skill = registry.get_skill("triage")

    assert skill is not None
    assert skill.scope == "repo"
    assert skill.description == "Repo skill description"
    assert skill.assets_dir == repo_skill / "assets"
    assert skill.scripts_dir == repo_skill / "scripts"


def test_custom_command_render_prompt_replaces_placeholders(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    commands_dir = repo_root / ".poor-cli" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "review.md").write_text(
        "# Review\nReview {{args}} from {{cwd}} in {{repo_root}}\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr("poor_cli.custom_commands.Path.home", lambda: tmp_path)

    registry = CustomCommandRegistry(repo_root)
    rendered = registry.render_prompt("review", args_text="src/main.py")

    assert "src/main.py" in rendered
    assert str(repo_root) in rendered
    assert "{{args}}" not in rendered
    assert "{{cwd}}" not in rendered
    assert "{{repo_root}}" not in rendered
