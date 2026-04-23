import asyncio
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


if __name__ == "__main__":
    unittest.main()
