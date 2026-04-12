import json
import unittest
from types import SimpleNamespace

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.enhanced_tools import EnhancedToolRegistry
from poor_cli.server.handlers.tools import ToolsHandlersMixin
from poor_cli.tool_output_filter import OutputFilterSpec, apply_schema_output_filter
from poor_cli.tools_async import FilteredToolResult


class TestSchemaOutputFilter(unittest.TestCase):
    def test_jsonpath_filter_projects_fields(self) -> None:
        raw = json.dumps(
            {
                "number": 12,
                "title": "keep",
                "body": "keep body",
                "comments": [{"body": "drop"}],
                "files": [{"patch": "drop"}],
            }
        )
        result = apply_schema_output_filter(
            raw,
            {"type": "jsonpath", "paths": ["$.number", "$.title", "$.body"]},
        )

        self.assertTrue(result.applied)
        self.assertIn('"number": 12', result.output)
        self.assertNotIn("comments", result.output)
        self.assertIn("comments", result.dropped_paths)

    def test_regex_filter_keeps_matches(self) -> None:
        raw = "noise\nabc123 commit one\nnoise\nfff999 commit two\n"
        result = apply_schema_output_filter(
            raw,
            OutputFilterSpec(type="regex", pattern=r"^[0-9a-f]{6}\s+.*$"),
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.output, "abc123 commit one\nfff999 commit two")

    def test_keeplines_filter_keeps_matching_lines(self) -> None:
        raw = "hint text\nERROR failed here\ntrace detail\nok\n"
        result = apply_schema_output_filter(
            raw,
            {"type": "keeplines", "patterns": [r"ERROR|failed"]},
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.output, "ERROR failed here")

    def test_absent_filter_falls_through(self) -> None:
        raw = "full output"
        result = apply_schema_output_filter(raw, None)

        self.assertFalse(result.applied)
        self.assertEqual(result.output, raw)
        self.assertEqual(result.original_output, raw)


class TestRegistrySchemaOutputFilter(unittest.IsolatedAsyncioTestCase):
    async def test_declared_filter_applies_post_execution(self) -> None:
        async def fake() -> str:
            return json.dumps({"keep": "yes", "drop": "x" * 2000})

        registry = EnhancedToolRegistry(config=Config())
        registry.register_external_tool(
            "fake_json",
            fake,
            {
                "name": "fake_json",
                "description": "fake",
                "parameters": {"type": "OBJECT", "properties": {}, "required": []},
                "output_filter": {"type": "jsonpath", "paths": ["$.keep"]},
            },
        )

        result = await registry.execute_tool_raw("fake_json", {})

        self.assertIsInstance(result, FilteredToolResult)
        self.assertIn('"keep": "yes"', result.output)
        self.assertNotIn("drop", result.output)
        self.assertIn("drop", result.raw_output)
        self.assertEqual(registry.get_output_filter_stats()["filtered_calls"], 1)

    async def test_namespaced_external_tool_does_not_schema_filter(self) -> None:
        async def fake() -> str:
            return json.dumps({"keep": "yes", "drop": "raw"})

        registry = EnhancedToolRegistry(config=Config())
        registry.register_external_tool(
            "demo:fake_json",
            fake,
            {
                "name": "demo:fake_json",
                "description": "fake",
                "parameters": {"type": "OBJECT", "properties": {}, "required": []},
                "output_filter": {"type": "jsonpath", "paths": ["$.keep"]},
            },
        )

        result = await registry.execute_tool_raw("demo:fake_json", {})

        self.assertIsInstance(result, str)
        self.assertIn("drop", result)


class TestToolFullOutputRpc(unittest.IsolatedAsyncioTestCase):
    async def test_full_output_retrievable_via_rpc(self) -> None:
        core = object.__new__(PoorCLICore)
        core._tool_full_outputs = {
            "call-1": {
                "callId": "call-1",
                "toolName": "fake",
                "output": "raw-output",
                "filter": {"originalSize": 10, "filteredSize": 3},
            }
        }
        ctx = SimpleNamespace(core=core, _ensure_initialized=lambda: None)

        result = await ToolsHandlersMixin.handle_tool_full_output(ctx, {"callId": "call-1"})

        self.assertTrue(result["found"])
        self.assertEqual(result["output"], "raw-output")
