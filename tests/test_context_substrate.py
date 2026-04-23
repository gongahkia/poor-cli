import json
import tempfile
import unittest
from pathlib import Path

from poor_cli.context_substrate import append_jsonl_record, context_map, doctor_context, init_context


class ContextSubstrateTests(unittest.TestCase):
    def test_init_creates_expected_files_and_doctor_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = init_context(root)
            self.assertTrue(result["created"])
            report = doctor_context(root)
            self.assertTrue(report["ok"])
            names = {Path(item["path"]).name for item in context_map(root)["files"]}
            self.assertIn("MAP.md", names)
            self.assertIn("decisions.jsonl", names)

    def test_append_jsonl_preserves_schema_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_context(root)
            result = append_jsonl_record("decisions.jsonl", {"decision": "ship"}, repo_root=root)
            rows = [json.loads(line) for line in Path(result["path"]).read_text().splitlines()]
            self.assertEqual(rows[0]["_schema"], "decision")
            self.assertEqual(rows[1]["decision"], "ship")


if __name__ == "__main__":
    unittest.main()
