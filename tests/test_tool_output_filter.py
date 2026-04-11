"""tests for tool output filtering middleware."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.enhanced_tools import EnhancedToolRegistry
from poor_cli.mcp_client import MCPManager
from poor_cli.tool_output_filter import ToolOutputFilter


class TestToolOutputFilter(unittest.TestCase):
    def test_auto_filters_large_github_response_under_one_kb(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            payload = []
            for idx in range(5):
                payload.append(
                    {
                        "number": idx + 1,
                        "title": f"PR {idx + 1}",
                        "state": "OPEN",
                        "author": {"login": f"user{idx}"},
                        "url": f"https://example.test/pr/{idx + 1}",
                        "body": "x" * 9000,
                        "files": [{"path": f"file_{n}.py", "patch": "y" * 800} for n in range(5)],
                    }
                )
            response = json.dumps(payload)
            self.assertGreater(len(response), 40000)

            filtered = ToolOutputFilter(repo_root=Path(td)).filter("gh_pr_list", response)

            self.assertTrue(filtered.applied)
            self.assertLess(len(filtered.output.encode("utf-8")), 1024)
            self.assertIn("[tool-output-filter]", filtered.output)
            self.assertGreater(filtered.tokens_saved, 0)

    def test_repo_yaml_overrides_projection_rule(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            poor_dir = repo_root / ".poor-cli"
            poor_dir.mkdir(parents=True, exist_ok=True)
            (poor_dir / "tool_projections.yaml").write_text(
                """
tool_projections:
  fetch_url:
    max_tokens: 10
    fields:
      - title
      - body
""".strip()
                + "\n",
                encoding="utf-8",
            )
            payload = json.dumps(
                {
                    "title": "Example",
                    "body": "kept",
                    "html": "x" * 2000,
                    "links": ["https://example.test"] * 100,
                }
            )

            filtered = ToolOutputFilter(repo_root=repo_root).filter("fetch_url", payload)

            self.assertTrue(filtered.applied)
            self.assertIn('"title": "Example"', filtered.output)
            self.assertIn('"body": "kept"', filtered.output)
            self.assertNotIn('"html"', filtered.output)

    def test_parses_list_directory_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            listing = "\n".join(
                ["Contents of /tmp/demo:", "FILE   12B foo.txt", "DIR    4.0KB src", "LINK   3B current"]
            )
            filtered = ToolOutputFilter(repo_root=Path(td), default_max_tokens=5).filter(
                "list_directory",
                listing,
            )

            self.assertTrue(filtered.applied)
            self.assertIn('"name": "foo.txt"', filtered.output)
            self.assertIn('"type": "dir"', filtered.output)
            self.assertIn('"size": "3B"', filtered.output)


class TestEnhancedToolRegistryFiltering(unittest.IsolatedAsyncioTestCase):
    async def test_execute_tool_raw_strips_projection_args_and_tracks_stats(self) -> None:
        seen = {}

        async def fake_tool(limit: int = 0) -> str:
            seen["limit"] = limit
            payload = [
                {
                    "number": 1,
                    "title": "one",
                    "state": "OPEN",
                    "author": {"login": "dev"},
                    "url": "https://example.test/pr/1",
                    "body": "x" * 6000,
                }
            ]
            return json.dumps(payload)

        registry = EnhancedToolRegistry(config=Config())
        registry.register_external_tool(
            "gh_pr_list",
            fake_tool,
            {
                "name": "gh_pr_list",
                "description": "fake gh list",
                "parameters": {"type": "OBJECT", "properties": {"limit": {"type": "INTEGER"}}},
            },
        )

        result = await registry.execute_tool_raw(
            "gh_pr_list",
            {"limit": 5, "_projection": ["number", "title"]},
        )

        self.assertEqual(seen["limit"], 5)
        self.assertIn('"number": 1', result)
        self.assertIn('"title": "one"', result)
        self.assertNotIn('"body"', result)
        self.assertEqual(registry.get_output_filter_stats()["filtered_calls"], 1)


class FakeMCPClient:
    def __init__(self) -> None:
        self.seen_arguments = None

    async def call_tool_raw(self, name: str, arguments):
        self.seen_arguments = {"name": name, "arguments": arguments}
        return {
            "content": [{"type": "text", "text": "x" * 25000}],
            "structuredContent": {
                "title": "Search Result",
                "url": "https://example.test/result",
                "blob": "y" * 5000,
            },
            "metadata": {"trace": "z" * 4000},
        }

    async def disconnect(self) -> None:
        return None


class TestMCPFiltering(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_manager_filters_projected_response(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = MCPManager({}, repo_root=Path(td))
            client = FakeMCPClient()
            manager._tool_to_client["demo:search"] = client
            manager._tool_name_map["demo:search"] = "search"
            manager._tool_declarations["demo:search"] = {
                "name": "demo:search",
                "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}},
            }

            result = await manager.execute_tool(
                "demo:search",
                {
                    "query": "abc",
                    "_projection": ["structuredContent.title", "structuredContent.url"],
                },
            )

            self.assertEqual(client.seen_arguments["name"], "search")
            self.assertEqual(client.seen_arguments["arguments"], {"query": "abc"})
            self.assertIn('"title": "Search Result"', result)
            self.assertIn('"url": "https://example.test/result"', result)
            self.assertNotIn("blob", result)
            self.assertEqual(manager.get_output_filter_stats()["filtered_calls"], 1)


class TestCostSurface(unittest.TestCase):
    def test_cost_summary_includes_tool_filter_savings(self) -> None:
        core = object.__new__(PoorCLICore)
        core.tool_registry = SimpleNamespace(
            get_output_filter_stats=lambda: {
                "filtered_calls": 2,
                "projection_filtered_calls": 2,
                "auto_filtered_calls": 1,
                "tokens_saved": 1200,
            }
        )
        core._mcp_manager = SimpleNamespace(
            get_output_filter_stats=lambda: {
                "filtered_calls": 1,
                "projection_filtered_calls": 1,
                "auto_filtered_calls": 1,
                "tokens_saved": 800,
            }
        )
        core._session_total_input_tokens = 100
        core._session_total_output_tokens = 50
        core._session_total_cost_usd = 0.01
        core._session_cache_creation_input_tokens = 0
        core._session_cache_read_input_tokens = 0
        core._session_provider_cache_hits = 0
        core._session_provider_cache_misses = 0
        core._session_estimated_cache_savings_usd = 0.0
        core._economy_tracker = SimpleNamespace(get_summary=lambda: {})
        core.provider = None
        core.config = Config()
        core._response_cache = {}
        core.get_context_breakdown = lambda: {}
        core.get_context_pressure = lambda: {}
        core.get_cache_stats = lambda: {}

        summary = core.get_session_cost_summary()
        report = core.export_cost_report()

        self.assertEqual(summary["tool_filtering_tokens_saved"], 2000)
        self.assertEqual(summary["toolFilteringTokensSaved"], 2000)
        self.assertEqual(report["tool_filtering"]["tokens_saved"], 2000)


if __name__ == "__main__":
    unittest.main()
