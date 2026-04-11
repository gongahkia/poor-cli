"""tests for lazy/on-demand tool schema loading."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.enhanced_tools import CORE_TOOL_GROUP, EnhancedToolRegistry
from poor_cli.mcp_client import MCPManager
from poor_cli.providers.base import ProviderCapabilities


class FakeProvider:
    def __init__(self) -> None:
        self.initialize_calls = []
        self.history = []

    async def initialize(self, tools=None, system_instruction=None):
        self.initialize_calls.append(
            {
                "tools": [tool.get("name", "") for tool in tools or []],
                "system_instruction": system_instruction,
            }
        )

    def get_history(self):
        return list(self.history)

    def set_history(self, messages):
        self.history = list(messages)

    def get_capabilities(self):
        return ProviderCapabilities(supports_function_calling=True)


class FakeMCPClient:
    def __init__(self) -> None:
        self.connected = False
        self.list_tools_calls = 0
        self.call_tool_calls = 0
        self.health_checks = 0

    async def connect(self) -> None:
        self.connected = True

    async def list_tools(self):
        self.list_tools_calls += 1
        return [
            {
                "name": "search",
                "description": "demo search",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"query": {"type": "STRING"}},
                    "required": ["query"],
                },
            }
        ]

    async def list_resources(self):
        return []

    async def list_prompts(self):
        return []

    async def call_tool_raw(self, name: str, arguments):
        self.call_tool_calls += 1
        return {"content": [{"type": "text", "text": f"{name}:{arguments['query']}"}]}

    async def health_check(self) -> bool:
        self.health_checks += 1
        return True

    async def disconnect(self) -> None:
        self.connected = False


class TestLazyToolAudit(unittest.TestCase):
    def test_audit_counts_builtin_catalog(self) -> None:
        registry = EnhancedToolRegistry(Config())

        audit = registry.audit_tool_catalog()

        self.assertGreaterEqual(audit.total_tools, 30)
        self.assertGreater(audit.schema_chars, 0)
        self.assertGreater(audit.schema_tokens, 0)
        self.assertIn(CORE_TOOL_GROUP, audit.group_counts)

    def test_explain_function_selects_core_and_search(self) -> None:
        registry = EnhancedToolRegistry(Config())

        groups = registry.required_tool_groups("explain this function")
        declarations = registry.get_tool_declarations_for_groups(groups)
        names = {declaration["name"] for declaration in declarations}

        self.assertEqual(groups, ["core", "search"])
        self.assertIn("read_file", names)
        self.assertIn("grep_files", names)
        self.assertNotIn("git_status", names)
        self.assertNotIn("run_tests", names)


class TestLazyToolSelection(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_activation_refreshes_provider_with_relevant_tools(self) -> None:
        core = object.__new__(PoorCLICore)
        core.tool_registry = EnhancedToolRegistry(Config())
        core.provider = FakeProvider()
        core.config = Config()
        core._initialized = True
        core._system_instruction = "sys"
        core._mcp_manager = None
        core._active_tool_groups = tuple()
        core._active_tool_names = set()
        core._active_tool_declarations = []

        await core._activate_tools_for_prompt("explain this function")

        active_names = set(core._active_tool_names)
        self.assertIn("read_file", active_names)
        self.assertIn("grep_files", active_names)
        self.assertNotIn("git_status", active_names)
        self.assertEqual(core.provider.initialize_calls[-1]["tools"], [tool["name"] for tool in core._active_tool_declarations])

    async def test_missing_tool_loads_group_on_demand(self) -> None:
        core = object.__new__(PoorCLICore)
        core.tool_registry = EnhancedToolRegistry(Config())
        core.provider = FakeProvider()
        core.config = Config()
        core._initialized = True
        core._system_instruction = "sys"
        core._mcp_manager = None
        core._active_tool_groups = tuple()
        core._active_tool_names = set()
        core._active_tool_declarations = []

        await core._activate_tool_groups(["core"], refresh_provider=False)
        note = await core._ensure_tool_available_for_call("web_search", user_request="search online")

        self.assertIsNotNone(note)
        self.assertIn("network", note)
        self.assertIn("web_search", core._active_tool_names)


class TestLazyMCPTools(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_health_check_does_not_force_schema_load(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = MCPManager({"demo": {"command": "fake", "enabled": True}}, repo_root=Path(td))
            client = FakeMCPClient()
            with patch.object(MCPManager, "_create_client", return_value=client):
                await manager.initialize()
                health = await manager.health_check_all()

            self.assertEqual(client.list_tools_calls, 0)
            self.assertTrue(health["demo"])
            self.assertFalse(manager.status()["servers"]["demo"]["schemasLoaded"])

    async def test_execute_tool_lazy_loads_schema_on_first_use(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = MCPManager({"demo": {"command": "fake", "enabled": True}}, repo_root=Path(td))
            client = FakeMCPClient()
            with patch.object(MCPManager, "_create_client", return_value=client):
                await manager.initialize()
                result = await manager.execute_tool("demo:search", {"query": "abc"})

            status = manager.status()
            self.assertEqual(result, "search:abc")
            self.assertEqual(client.list_tools_calls, 1)
            self.assertEqual(client.call_tool_calls, 1)
            self.assertTrue(status["servers"]["demo"]["schemasLoaded"])
            self.assertIn("demo:search", [tool["name"] for tool in manager.get_tool_declarations()])


if __name__ == "__main__":
    unittest.main()
