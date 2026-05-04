from pathlib import Path

from poor_cli.spec_mode import SpecMode, Subtask, SubtaskStatus, latest_checkpoint, topological_subtasks


class FakeCheckpoint:
    def __init__(self, checkpoint_id):
        self.checkpoint_id = checkpoint_id


class FakeCheckpointManager:
    def __init__(self):
        self.created = []
        self.restored = []

    def create_checkpoint(self, paths, description, operation_type="manual", tags=None):
        checkpoint = FakeCheckpoint(f"cp-{len(self.created) + 1}")
        self.created.append((paths, description, operation_type, tags))
        return checkpoint

    def restore_checkpoint(self, checkpoint_id):
        self.restored.append(checkpoint_id)
        return 1


def test_topological_sort_respects_dependencies():
    tasks = [
        Subtask("c", "C", "third", depends_on=["b"]),
        Subtask("a", "A", "first"),
        Subtask("b", "B", "second", depends_on=["a"]),
    ]

    assert [task.id for task in topological_subtasks(tasks)] == ["a", "b", "c"]


def test_failing_subtask_blocks_dependents(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n\n## One\n\n## Two\n", encoding="utf-8")

    def runner(agent, prompt, run, subtask):
        if subtask.id == "task-1" and agent == "reviewer":
            return "BLOCKER: missing work"
        return "ok"

    result = SpecMode(tmp_path, subagent_runner=runner).run(spec)

    assert result.status == "paused"
    assert result.subtasks[0].status == SubtaskStatus.BLOCKED
    assert result.subtasks[1].status == SubtaskStatus.PENDING


def test_resume_picks_next_pending_subtask(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n\n## One\n\n## Two\n", encoding="utf-8")
    mode = SpecMode(tmp_path)
    run = mode.plan(spec)
    run.subtasks[0].status = SubtaskStatus.DONE
    mode._save(run)

    resumed = mode.resume(run.spec_id)

    assert resumed.status == "completed"
    assert all(task.status == SubtaskStatus.DONE for task in resumed.subtasks)


def test_abort_restores_latest_checkpoint(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n\n## One\n", encoding="utf-8")
    checkpoints = FakeCheckpointManager()
    mode = SpecMode(tmp_path, checkpoint_manager=checkpoints)
    run = mode.run(spec)

    aborted = mode.abort(run.spec_id)

    assert aborted.status == "aborted"
    assert checkpoints.created
    assert checkpoints.restored == [latest_checkpoint(run)]


def test_fixture_spec_runs_end_to_end_with_three_checkpoints(tmp_path):
    source = Path("tests/fixtures/spec_basic.md")
    spec = tmp_path / "spec_basic.md"
    spec.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    checkpoints = FakeCheckpointManager()

    result = SpecMode(tmp_path, checkpoint_manager=checkpoints).run(spec)

    assert result.status == "completed"
    assert len(result.subtasks) == 3
    assert len(checkpoints.created) == 3
