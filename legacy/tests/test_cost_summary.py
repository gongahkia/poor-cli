import unittest
from types import SimpleNamespace

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.economy import EconomySavingsTracker


class CostSummaryTests(unittest.TestCase):
    def _core(self) -> PoorCLICore:
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.provider = None
        core.tool_registry = SimpleNamespace(get_output_filter_stats=lambda: {})
        core._mcp_manager = None
        core._economy_tracker = EconomySavingsTracker()
        core._session_total_input_tokens = 600
        core._session_total_output_tokens = 400
        core._session_total_cost_usd = 2.0
        core._session_cache_creation_input_tokens = 100
        core._session_cache_read_input_tokens = 300
        core._session_provider_cache_hits = 3
        core._session_provider_cache_misses = 2
        core._session_estimated_cache_savings_usd = 0.01
        core._cost_turn_history = [
            {"turn_id": "t1", "cost_usd": 0.75, "input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
            {"turn_id": "t2", "cost_usd": 1.25, "input_tokens": 400, "output_tokens": 300, "total_tokens": 700},
        ]
        core._cost_tool_totals = {
            "read_file": {"tool": "read_file", "cost_usd": 0.2, "tokens": 250, "calls": 2},
        }
        core.get_cost_history = lambda limit=500: []
        return core

    def test_cost_summary_includes_per_turn(self) -> None:
        summary = self._core().get_session_summary()

        self.assertEqual(len(summary["per_turn"]), 2)
        self.assertEqual(summary["last_turn"]["turn_id"], "t2")
        self.assertEqual(summary["top_tools"][0]["tool"], "read_file")

    def test_cost_summary_projected_monthly_math(self) -> None:
        summary = self._core().get_session_summary()

        self.assertEqual(summary["projected_monthly_usd"], 60.0)
        self.assertEqual(summary["projected_monthly_last_week_usd"], 60.0)

    def test_cache_hit_rate_computed(self) -> None:
        summary = self._core().get_session_summary()

        self.assertEqual(summary["session"]["cache_hit_rate"], 60.0)
        self.assertEqual(summary["cache"]["hits"], 3)
        self.assertEqual(summary["cache"]["misses"], 2)
