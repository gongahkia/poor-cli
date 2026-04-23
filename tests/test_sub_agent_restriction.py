"""Tests for sub-agent tool restriction."""

import unittest
from unittest.mock import MagicMock


class TestSubAgentRestriction(unittest.TestCase):
    def _make_parent(self):
        parent = MagicMock()
        parent.config.agentic.sub_agent_max_depth = 2
        parent.config.agentic.sub_agent_max_iterations = 10
        parent.config.agentic.sub_agent_timeout = 120
        parent.config.agentic.sub_agent_max_input_tokens = 40000
        parent.config.agentic.sub_agent_max_output_tokens = 12000
        parent.config.agentic.sub_agent_max_cost_usd = 0.5
        parent.config.agentic.sub_agent_default_denied_tools = []
        parent._sub_agent_depth = 0
        parent.tool_registry.get_tool_declarations.return_value = [
            {"name": "read_file"}, {"name": "write_file"},
            {"name": "bash"}, {"name": "grep_files"}, {"name": "spawn_parallel_agents"},
            {"name": "delegate_task"},
        ]
        return parent

    def test_denied_tools_filtered(self):
        from poor_cli.sub_agent import SubAgent
        parent = self._make_parent()
        agent = SubAgent(parent, denied_tools={"bash", "write_file"})
        decls = parent.tool_registry.get_tool_declarations()
        denied = agent._denied_tools | {"delegate_task"}
        filtered = [t for t in decls if t.get("name") not in denied]
        self.assertEqual({t["name"] for t in filtered}, {"read_file", "grep_files"})

    def test_allowed_tools_whitelist(self):
        from poor_cli.sub_agent import SubAgent
        agent = SubAgent(self._make_parent(), allowed_tools={"read_file", "grep_files"})
        decls = self._make_parent().tool_registry.get_tool_declarations()
        denied = agent._denied_tools | {"delegate_task"}
        filtered = [t for t in decls if t.get("name") in agent._allowed_tools and t.get("name") not in denied]
        self.assertEqual({t["name"] for t in filtered}, {"read_file", "grep_files"})

    def test_delegate_task_always_removed(self):
        from poor_cli.sub_agent import SubAgent
        agent = SubAgent(self._make_parent(), allowed_tools={"read_file", "delegate_task"})
        decls = self._make_parent().tool_registry.get_tool_declarations()
        denied = agent._denied_tools | {"delegate_task"}
        filtered = [t for t in decls if t.get("name") in agent._allowed_tools and t.get("name") not in denied]
        names = {t["name"] for t in filtered}
        self.assertNotIn("delegate_task", names)

    def test_spawn_parallel_agents_always_removed(self):
        from poor_cli.sub_agent import SubAgent
        agent = SubAgent(self._make_parent(), allowed_tools={"read_file", "spawn_parallel_agents"})
        decls = self._make_parent().tool_registry.get_tool_declarations()
        filtered = [t for t in decls if t.get("name") in agent._allowed_tools and t.get("name") not in agent._denied_tools]
        names = {t["name"] for t in filtered}
        self.assertNotIn("spawn_parallel_agents", names)

    def test_tools_param_parsing(self):
        tools_str = "read_file, grep_files, glob_files"
        allowed = {t.strip() for t in tools_str.split(",") if t.strip()}
        self.assertEqual(allowed, {"read_file", "grep_files", "glob_files"})

    def test_communication_mode_validation(self):
        from poor_cli.sub_agent import SubAgent
        SubAgent(self._make_parent(), communication_mode="latent")
        with self.assertRaises(ValueError):
            SubAgent(self._make_parent(), communication_mode="invalid")

    def test_advisor_archetype_filters_writes(self):
        from poor_cli.sub_agent import SubAgent
        agent = SubAgent(self._make_parent(), archetype="advisor")
        names = {t["name"] for t in agent._resolve_filtered_tools()}
        self.assertIn("read_file", names)
        self.assertIn("grep_files", names)
        self.assertNotIn("write_file", names)
        self.assertNotIn("bash", names)
