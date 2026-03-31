"""tests for tool orchestration safety and concurrency classification."""

import unittest

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.sandbox import ToolCapability
from poor_cli.tools_async import ToolRegistryAsync


async def _noop_tool(**kwargs):  # pragma: no cover - never awaited in unit tests
    return kwargs


class TestToolOrchestrationSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistryAsync()

    def test_builtin_read_tool_is_concurrency_safe(self) -> None:
        self.assertTrue(
            self.registry.is_concurrency_safe_tool(
                "read_file",
                {"file_path": __file__},
            )
        )

    def test_builtin_write_tool_is_not_concurrency_safe(self) -> None:
        self.assertFalse(
            self.registry.is_concurrency_safe_tool(
                "write_file",
                {"file_path": __file__, "content": "x"},
            )
        )

    def test_unknown_tool_defaults_to_sequential(self) -> None:
        self.assertFalse(self.registry.is_concurrency_safe_tool("unknown_tool", {}))

    def test_external_readonly_tool_is_concurrency_safe(self) -> None:
        declaration = {
            "name": "external_readonly",
            "description": "network read-only tool",
            "parameters": {"type": "OBJECT", "properties": {}},
            "x-poor-cli": {
                "capabilities": [ToolCapability.NETWORK_ACCESS.value],
                "mutating": False,
            },
        }
        self.registry.register_external_tool("external_readonly", _noop_tool, declaration)
        self.assertTrue(self.registry.is_concurrency_safe_tool("external_readonly", {}))

    def test_apply_patch_check_only_is_not_mutating(self) -> None:
        self.assertFalse(
            self.registry.is_mutating_tool(
                "apply_patch_unified",
                {"patch": "diff --git a/a b/a", "check_only": True},
            )
        )

    def test_memory_save_is_mutating(self) -> None:
        self.assertTrue(
            self.registry.is_mutating_tool(
                "memory_save",
                {"title": "t", "content": "c"},
            )
        )


class TestCoreParallelismConfig(unittest.TestCase):
    def test_max_parallel_tool_calls_is_clamped(self) -> None:
        core = PoorCLICore()
        core.config = Config()

        core.config.agentic.max_parallel_tool_calls = 0
        self.assertEqual(core._max_parallel_tool_calls(), 1)

        core.config.agentic.max_parallel_tool_calls = 99
        self.assertEqual(core._max_parallel_tool_calls(), 32)

        core.config.agentic.max_parallel_tool_calls = 8
        self.assertEqual(core._max_parallel_tool_calls(), 8)
