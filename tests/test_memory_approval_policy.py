import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.init_cmd import run_init
from seuss.commands.memory_cmd import run_memory_import
from seuss.jsonl_store import read_jsonl


class MemoryApprovalPolicyTests(unittest.TestCase):
    def _prepare(self, root: Path, require_explicit_approval: bool) -> Path:
        config_path = root / "seuss.yaml"
        run_init(config_path=config_path, force=False)
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        cfg["adaptation"]["live_training_data"]["enabled"] = True
        cfg["adaptation"]["live_training_data"][
            "require_explicit_approval"
        ] = require_explicit_approval
        config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        return config_path

    def _write_import_file(self, root: Path) -> Path:
        import_path = root / "live.jsonl"
        row = {
            "text": "This is a live conversation line for memory capture.",
            "speaker": "user",
        }
        import_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return import_path

    def test_queue_when_explicit_approval_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._prepare(root, require_explicit_approval=True)
            import_path = self._write_import_file(root)

            self.assertEqual(
                run_memory_import(
                    config_path=config_path,
                    import_path=import_path,
                    text_field="text",
                ),
                0,
            )

            workspace = root / ".seuss"
            queue = read_jsonl(workspace / "training_queue.jsonl")
            approved = read_jsonl(workspace / "approved_training.jsonl")
            self.assertGreater(len(queue), 0)
            self.assertEqual(len(approved), 0)
            self.assertTrue(all(row.get("approval_status") == "pending" for row in queue))

    def test_auto_approve_when_policy_allows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = self._prepare(root, require_explicit_approval=False)
            import_path = self._write_import_file(root)

            self.assertEqual(
                run_memory_import(
                    config_path=config_path,
                    import_path=import_path,
                    text_field="text",
                ),
                0,
            )

            workspace = root / ".seuss"
            queue = read_jsonl(workspace / "training_queue.jsonl")
            approved = read_jsonl(workspace / "approved_training.jsonl")
            self.assertEqual(len(queue), 0)
            self.assertGreater(len(approved), 0)
            self.assertTrue(all(row.get("approval_status") == "approved" for row in approved))


if __name__ == "__main__":
    unittest.main()
