import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.approve_cmd import run_approve_accept, run_approve_list
from seuss.commands.init_cmd import run_init
from seuss.commands.memory_cmd import run_memory_import
from seuss.jsonl_store import read_jsonl


class QueuePathConfigTests(unittest.TestCase):
    def test_custom_queue_path_is_used_for_memory_and_approve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "seuss.yaml"
            self.assertEqual(run_init(config_path=config_path, force=False), 0)

            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            cfg["adaptation"]["live_training_data"]["enabled"] = True
            cfg["adaptation"]["live_training_data"]["require_explicit_approval"] = True
            cfg["adaptation"]["live_training_data"]["queue_path"] = "./custom_queue/live_queue.jsonl"
            config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

            live_import = root / "live.jsonl"
            live_import.write_text(
                json.dumps({"text": "A live memory example for queue-path testing."}) + "\n",
                encoding="utf-8",
            )

            self.assertEqual(
                run_memory_import(config_path=config_path, import_path=live_import, text_field="text"),
                0,
            )

            custom_queue = root / "custom_queue" / "live_queue.jsonl"
            default_queue = root / ".seuss" / "training_queue.jsonl"
            self.assertTrue(custom_queue.exists())
            custom_rows = read_jsonl(custom_queue)
            default_rows = read_jsonl(default_queue)
            self.assertGreater(len(custom_rows), 0)
            self.assertEqual(len(default_rows), 0)

            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(run_approve_list(config_path=config_path, include_all=False), 0)
            self.assertIn("Queue records", out.getvalue())

            ex_id = custom_rows[0]["id"]
            self.assertEqual(run_approve_accept(config_path=config_path, record_id=ex_id), 0)
            approved_rows = read_jsonl(root / ".seuss" / "approved_training.jsonl")
            self.assertTrue(any(row.get("id") == ex_id for row in approved_rows))


if __name__ == "__main__":
    unittest.main()
