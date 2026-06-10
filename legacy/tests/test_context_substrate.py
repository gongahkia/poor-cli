import json
import tempfile
import unittest
from pathlib import Path

from poor_cli.context_substrate import (
    append_jsonl_record,
    append_run_summary_if_initialized,
    context_map,
    doctor_context,
    init_context,
    render_routed_context,
)


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

    def test_routed_context_loads_relevant_jsonl_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_context(root)
            append_jsonl_record("decisions.jsonl", {"decision": "keep writes single-threaded"}, repo_root=root)
            rendered = render_routed_context("why did we choose this architecture?", repo_root=root)
            self.assertIn("Context Map", rendered)
            self.assertIn("keep writes single-threaded", rendered)

    def test_run_summary_noops_until_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(append_run_summary_if_initialized(repo_root=root, run_id="r1", status="done"))
            init_context(root)
            result = append_run_summary_if_initialized(
                repo_root=root,
                run_id="r1",
                status="done",
                summary="completed task",
            )
            self.assertIsNotNone(result)
            text = (root / ".poor-cli" / "context" / "runs.jsonl").read_text()
            self.assertIn("completed task", text)


if __name__ == "__main__":
    unittest.main()
