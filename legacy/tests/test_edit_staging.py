import tempfile
import unittest
from pathlib import Path

from poor_cli.config import Config
from poor_cli.edit_staging import EditStage, should_stage_edit


class FakeCheckpoint:
    checkpoint_id = "cp-1"


class FakeCheckpointManager:
    def __init__(self):
        self.calls = []

    def create_for_batch(self, edit_id, path, label):
        self.calls.append((edit_id, path, label))
        return FakeCheckpoint()


class EditStageTests(unittest.TestCase):
    def test_stage_computes_hunks_from_bytes(self):
        stage = EditStage()
        edit = stage.stage(path="demo.py", original=b"a\nb\n", proposed=b"a\nc\n")
        self.assertEqual(len(edit.hunks), 1)
        self.assertIn("@@", edit.hunks[0].header)
        self.assertIn("-b", edit.diff_text)

    def test_accept_hunk_marks_accepted_without_writing_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo.py"
            path.write_text("a\nb\n", encoding="utf-8")
            stage = EditStage()
            edit = stage.stage(path=str(path), original="a\nb\n", proposed="a\nc\n")
            result = stage.accept_hunk(edit.edit_id, edit.hunks[0].hunk_id)
            self.assertEqual(result["hunks"][0]["status"], "accepted")
            self.assertEqual(path.read_text(encoding="utf-8"), "a\nb\n")

    def test_reject_hunk_leaves_file_unchanged_after_finalize(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo.py"
            path.write_text("a\nb\n", encoding="utf-8")
            stage = EditStage()
            edit = stage.stage(path=str(path), original="a\nb\n", proposed="a\nc\n")
            stage.reject_hunk(edit.edit_id, edit.hunks[0].hunk_id)
            stage.finalize(edit.edit_id)
            self.assertEqual(path.read_text(encoding="utf-8"), "a\nb\n")

    def test_accept_all_writes_file_and_creates_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo.py"
            path.write_text("a\nb\n", encoding="utf-8")
            stage = EditStage()
            edit = stage.stage(path=str(path), original="a\nb\n", proposed="a\nc\n", prompt="make c")
            checkpoints = FakeCheckpointManager()
            result = stage.accept_all(edit.edit_id, checkpoint_manager=checkpoints)
            self.assertEqual(path.read_text(encoding="utf-8"), "a\nc\n")
            self.assertEqual(result["checkpointId"], "cp-1")
            self.assertEqual(len(checkpoints.calls), 1)
            self.assertIn("make c", checkpoints.calls[0][2])

    def test_reject_all_never_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo.py"
            path.write_text("a\nb\n", encoding="utf-8")
            stage = EditStage()
            edit = stage.stage(path=str(path), original="a\nb\n", proposed="a\nc\n")
            stage.reject_all(edit.edit_id)
            self.assertEqual(path.read_text(encoding="utf-8"), "a\nb\n")

    def test_regenerate_hunk_swaps_in_new_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo.py"
            path.write_text("a\nb\n", encoding="utf-8")
            stage = EditStage()
            edit = stage.stage(path=str(path), original="a\nb\n", proposed="a\nc\n")
            stage.regenerate_hunk(edit.edit_id, edit.hunks[0].hunk_id, "d\n")
            stage.accept_all(edit.edit_id)
            self.assertEqual(path.read_text(encoding="utf-8"), "a\nd\n")

    def test_non_interactive_bypass_applies_immediately(self):
        config = Config()
        config.diff_review.require_diff_preview = False
        self.assertFalse(should_stage_edit(config, "demo.py", "a\n", "b\n", interactive=False))

    def test_default_requires_staging_even_when_non_interactive(self):
        config = Config()
        self.assertTrue(should_stage_edit(config, "demo.py", "a\n", "b\n", interactive=False))

    def test_audit_log_records_stage_and_finalize(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "demo.py"
            path.write_text("a\nb\n", encoding="utf-8")
            stage = EditStage()
            edit = stage.stage(path=str(path), original="a\nb\n", proposed="a\nc\n")
            stage.accept_all(edit.edit_id)
            ops = [event["operation"] for event in stage.audit_events]
            self.assertIn("diff.stage", ops)
            self.assertIn("diff.finalize", ops)


if __name__ == "__main__":
    unittest.main()
