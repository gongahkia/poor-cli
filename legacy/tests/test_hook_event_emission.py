from __future__ import annotations

from poor_cli.checkpoint import CheckpointManager
from poor_cli.edit_staging import EditStage
from poor_cli.history_pruning import HistoryPruner
from poor_cli.policy_hooks import PolicyHookManager, emit_policy_hook_nowait
from poor_cli.token_budget_controller import TokenBudgetAction, _clamp_action


def test_sync_hook_emission_points_call_policy_manager(tmp_path, monkeypatch) -> None:
    captured: list[str] = []

    async def fake_run(self, event, payload):
        captured.append(event)
        return []

    monkeypatch.setattr(PolicyHookManager, "run", fake_run)
    manager = PolicyHookManager(repo_root=tmp_path)

    emit_policy_hook_nowait(manager, "notification", {"title": "hello"})

    pruner = HistoryPruner()
    pruner._hook_manager = manager
    pruner.prune(
        [{"role": "user", "content": "old"}],
        target_tokens=1,
        mode="aggressive",
    )

    target = tmp_path / "a.txt"
    target.write_text("old\n", encoding="utf-8")
    checkpoints = CheckpointManager(
        workspace_root=tmp_path,
        enable_background_cleanup=False,
    )
    checkpoints._hook_manager = manager
    checkpoints.create_checkpoint([str(target)], "manual", "manual")

    stage = EditStage()
    stage._hook_manager = manager
    edit = stage.stage(path=str(target), original="old\n", proposed="new\n")
    stage.accept_all(edit.edit_id)

    assert "notification" in captured
    assert "pre_prune" in captured
    assert "post_prune" in captured
    assert "pre_checkpoint" in captured
    assert "post_checkpoint" in captured
    assert "pre_edit" in captured
    assert "post_edit" in captured


def test_budget_clamp_emits_budget_breach_when_hooks_dir_exists(tmp_path, monkeypatch) -> None:
    captured: list[str] = []

    async def fake_run(self, event, payload):
        captured.append(event)
        return []

    monkeypatch.setattr(PolicyHookManager, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".poor-cli" / "hooks").mkdir(parents=True)

    action = _clamp_action(TokenBudgetAction(max_output_tokens=99_999))

    assert action.max_output_tokens == 8192
    assert "budget_breach" in captured
