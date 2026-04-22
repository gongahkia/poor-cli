import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.init_cmd import run_init
from seuss.commands.memory_cmd import run_memory_import
from seuss.jsonl_store import read_jsonl


class MemoryImportHardeningTests(unittest.TestCase):
    def test_memory_import_skips_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "seuss.yaml"
            self.assertEqual(run_init(config_path=config_path, force=False), 0)

            import_path = root / "live.jsonl"
            rows = [
                json.dumps({"text": "valid memory line"}),
                '{"text": ',
                "42",
                json.dumps({"speaker": "user"}),
                "",
            ]
            import_path.write_text("\n".join(rows), encoding="utf-8")

            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(
                    run_memory_import(
                        config_path=config_path,
                        import_path=import_path,
                        text_field="text",
                    ),
                    0,
                )

            printed = out.getvalue()
            self.assertIn("invalid_json_rows=1", printed)
            self.assertIn("non_object_rows=1", printed)
            self.assertIn("missing_text_rows=1", printed)

            memories = read_jsonl(root / ".seuss" / "memory" / "memories.jsonl")
            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0].get("text"), "valid memory line")


if __name__ == "__main__":
    unittest.main()
