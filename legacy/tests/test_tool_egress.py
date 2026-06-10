import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from poor_cli.tools_async import ToolRegistryAsync


class ToolEgressTests(unittest.TestCase):
    def test_grep_paths_only_is_compact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("needle\n")
            (root / "b.txt").write_text("needle again\n")
            registry = ToolRegistryAsync()
            result = asyncio.run(
                registry.grep_files(
                    "needle",
                    path=str(root),
                    result_mode="paths_only",
                    max_results=10,
                )
            )
            self.assertIn("matching files", result)
            self.assertIn("tool_egress", result)
            self.assertIn("a.txt", result)

    def test_read_file_summary_and_cap_report_egress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "big.txt"
            target.write_text("line\n" * 100)
            registry = ToolRegistryAsync()
            result = asyncio.run(registry.read_file(str(target), result_mode="summary", max_bytes=120))
            self.assertIn("bytes=", result)
            self.assertIn("tool_egress", result)
            self.assertIn("truncated_to_bytes", result)

    def test_list_directory_names_only_reports_egress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("a")
            registry = ToolRegistryAsync()
            result = asyncio.run(registry.list_directory(str(root), result_mode="names_only", max_results=10))
            self.assertIn("a.txt", result)
            self.assertIn("tool_egress", result)

    def test_memory_save_can_stage_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                registry = ToolRegistryAsync()
                result = asyncio.run(registry.memory_save(
                    "review me",
                    "project",
                    "needs review",
                    "content",
                    review_required=True,
                ))
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
            self.assertIn("staged memory for review", result)


if __name__ == "__main__":
    unittest.main()
