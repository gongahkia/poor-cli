"""Tests for sub-agent cost tracking."""

import unittest
from unittest.mock import MagicMock


class TestSubAgentCost(unittest.TestCase):
    def _make_agent(self):
        from poor_cli.sub_agent import SubAgent
        parent = MagicMock()
        parent.config.agentic.sub_agent_max_depth = 2
        parent.config.agentic.sub_agent_max_iterations = 10
        parent.config.agentic.sub_agent_timeout = 120
        parent.config.agentic.sub_agent_max_input_tokens = 40000
        parent.config.agentic.sub_agent_max_output_tokens = 12000
        parent.config.agentic.sub_agent_max_cost_usd = 0.5
        parent.config.agentic.sub_agent_default_denied_tools = []
        parent._sub_agent_depth = 0
        parent._estimate_cost = lambda in_toks, out_toks: (in_toks / 1000.0) * 0.0005 + (out_toks / 1000.0) * 0.0015
        return SubAgent(parent)

    def test_initial_usage_zeros(self):
        agent = self._make_agent()
        usage = agent.get_usage()
        self.assertEqual(usage["input_tokens"], 0)
        self.assertEqual(usage["output_tokens"], 0)

    def test_accumulate_usage(self):
        agent = self._make_agent()
        chunk = MagicMock()
        chunk.usage.input_tokens = 100
        chunk.usage.output_tokens = 50
        chunk.usage.prompt_tokens = 0
        chunk.usage.completion_tokens = 0
        agent._accumulate_usage(chunk)
        self.assertEqual(agent.get_usage()["input_tokens"], 100)
        self.assertEqual(agent.get_usage()["output_tokens"], 50)
        self.assertGreater(agent.get_usage()["estimated_cost_usd"], 0.0)

    def test_accumulate_multiple(self):
        agent = self._make_agent()
        for i in range(3):
            chunk = MagicMock()
            chunk.usage.input_tokens = 10
            chunk.usage.output_tokens = 5
            chunk.usage.prompt_tokens = 0
            chunk.usage.completion_tokens = 0
            agent._accumulate_usage(chunk)
        self.assertEqual(agent.get_usage()["input_tokens"], 30)
        self.assertEqual(agent.get_usage()["output_tokens"], 15)

    def test_no_usage_attr_skips(self):
        agent = self._make_agent()
        chunk = MagicMock(spec=[]) # no attributes
        agent._accumulate_usage(chunk)
        self.assertEqual(agent.get_usage()["input_tokens"], 0)

    def test_budget_limit_message_reports_input_cap(self):
        agent = self._make_agent()
        agent._max_input_tokens = 10
        chunk = MagicMock()
        chunk.usage.input_tokens = 11
        chunk.usage.output_tokens = 0
        chunk.usage.prompt_tokens = 0
        chunk.usage.completion_tokens = 0
        agent._accumulate_usage(chunk)
        self.assertIn("input token budget reached", agent._budget_limit_message())
