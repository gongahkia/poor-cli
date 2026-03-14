import json
from pathlib import Path

from poor_cli.instructions import InstructionManager


def test_instruction_stack_merge_order(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("repo agents", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("repo claude", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "AGENTS.md").write_text("local agents", encoding="utf-8")
    (tmp_path / "pkg" / "feature.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / ".poor-cli").mkdir()
    (tmp_path / ".poor-cli" / "memory.md").write_text("repo memory", encoding="utf-8")
    (tmp_path / ".poor-cli" / "focus.json").write_text(
        json.dumps(
            {
                "goal": "finish rollout",
                "constraints": "keep tests green",
                "definition_of_done": "all phases wired",
                "started_at": "1711111111",
                "completed": False,
            }
        ),
        encoding="utf-8",
    )

    manager = InstructionManager(tmp_path)
    snapshot = manager.build_snapshot(
        [str(tmp_path / "pkg" / "feature.py")],
        plan_mode_enabled=True,
    )

    assert [source.kind for source in snapshot.sources] == [
        "runtime_policy",
        "repo_root",
        "repo_root",
        "path_local",
        "memory",
        "focus",
    ]
    assert [source.label for source in snapshot.sources] == [
        "Plan Mode",
        "Repo Root AGENTS.md",
        "Repo Root CLAUDE.md",
        "Path Local AGENTS.md",
        "Repo Memory",
        "Active Focus",
    ]
    rendered = snapshot.render_prompt_prefix()
    assert rendered.index("repo agents") < rendered.index("local agents")
    assert rendered.index("local agents") < rendered.index("repo memory")
    assert "Goal: finish rollout" in rendered
