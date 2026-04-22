import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seuss.commands.ingest_cmd import run_ingest
from seuss.commands.init_cmd import run_init
from seuss.jsonl_store import read_jsonl


class IngestHardeningTests(unittest.TestCase):
    def test_ingest_handles_invalid_jsonl_rows_and_reports_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "seuss.yaml"
            run_init(config_path=config_path, force=False)

            chat_path = root / "data" / "chat_export.jsonl"
            chat_path.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                '{"text": "valid row one"}',
                '{"text": "valid row two"}',
                '{"text": }',
                '42',
                '{"speaker": "user"}',
                '',
            ]
            chat_path.write_text("\n".join(rows), encoding="utf-8")

            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            for source in cfg["sources"]:
                if source["name"] == "notes":
                    source["enabled"] = False
                if source["name"] == "chat_export":
                    source["enabled"] = True
            config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

            with redirect_stdout(io.StringIO()) as stdout:
                rc = run_ingest(
                    config_path=config_path,
                    source_name="chat_export",
                    direct_path=None,
                    dry_run=False,
                    rebuild=True,
                )
            self.assertEqual(rc, 0)
            printed = stdout.getvalue()
            self.assertIn("invalid_json_rows", printed)
            self.assertIn("non_object_rows", printed)
            self.assertIn("missing_text_rows", printed)

            fragments = read_jsonl(root / ".seuss" / "corpus" / "fragments.jsonl")
            self.assertGreater(len(fragments), 0)
            self.assertTrue(any(fragment.get("source") == "chat_export" for fragment in fragments))


if __name__ == "__main__":
    unittest.main()
