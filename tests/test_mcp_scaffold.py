"""tests for poor_cli.mcp_scaffold module."""

import tempfile
import unittest
from pathlib import Path
from poor_cli.mcp_scaffold import scaffold_mcp_server


class TestScaffoldMcpServer(unittest.TestCase):
    def test_creates_directory_and_files(self):
        with tempfile.TemporaryDirectory() as td:
            result = scaffold_mcp_server("test_srv", language="python", output_dir=td)
            base = Path(td) / "mcp_servers" / "test_srv"
            self.assertTrue(base.is_dir())
            self.assertTrue((base / "server.py").is_file())
            self.assertTrue((base / "README.md").is_file())
            self.assertIn("test_srv", result)

    def test_python_template_has_jsonrpc_handler(self):
        with tempfile.TemporaryDirectory() as td:
            scaffold_mcp_server("py_srv", language="python", output_dir=td)
            content = (Path(td) / "mcp_servers" / "py_srv" / "server.py").read_text()
            self.assertIn("handle_request", content)
            self.assertIn("jsonrpc", content)

    def test_node_template_creates_server_js(self):
        with tempfile.TemporaryDirectory() as td:
            scaffold_mcp_server("node_srv", language="node", output_dir=td)
            self.assertTrue((Path(td) / "mcp_servers" / "node_srv" / "server.js").is_file())

    def test_readme_contains_config_snippet(self):
        with tempfile.TemporaryDirectory() as td:
            scaffold_mcp_server("cfg_srv", language="python", output_dir=td)
            readme = (Path(td) / "mcp_servers" / "cfg_srv" / "README.md").read_text()
            self.assertIn("mcp_servers:", readme)
            self.assertIn("cfg_srv", readme)

    def test_invalid_language_returns_error(self):
        with tempfile.TemporaryDirectory() as td:
            result = scaffold_mcp_server("bad", language="rust", output_dir=td)
            self.assertTrue(result.startswith("error:"))

    def test_generated_files_contain_protocol_version(self):
        with tempfile.TemporaryDirectory() as td:
            scaffold_mcp_server("proto_srv", language="python", output_dir=td)
            content = (Path(td) / "mcp_servers" / "proto_srv" / "server.py").read_text()
            self.assertIn("2024-11-05", content)


if __name__ == "__main__":
    unittest.main()
