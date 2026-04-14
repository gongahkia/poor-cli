"""Tests for CB5 offline budget retuning job."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from poor_cli.budget_retuning import (
    apply_tuning_to_optimizer,
    list_tunings,
    load_latest_tuning,
    run_retuning,
    tuning_dir,
    tuning_path_for_date,
)
from poor_cli.thinking_budget import ThinkingBudgetOptimizer


class TuningPathTests(unittest.TestCase):
    def test_tuning_dir_under_poor_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            self.assertEqual(tuning_dir(base).name, "budget_tunings")
            self.assertEqual(tuning_dir(base).parent, base)

    def test_tuning_path_formatted_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            path = tuning_path_for_date(datetime(2026, 4, 14, tzinfo=timezone.utc), base)
            self.assertTrue(path.name.endswith("2026-04-14.json"))


class RunRetuningTests(unittest.TestCase):
    def test_with_no_logs_writes_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            result = run_retuning(base)
            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(result["path"]).exists())
            self.assertEqual(result["records"], 0)

    def test_second_run_same_day_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            run_retuning(base)
            tunings1 = list_tunings(base)
            run_retuning(base)
            tunings2 = list_tunings(base)
            self.assertEqual(len(tunings1), 1)
            self.assertEqual(len(tunings2), 1)

    def test_with_historical_logs_analyzes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            base.mkdir(parents=True, exist_ok=True)
            log_path = base / "budget_logs.jsonl"
            # synthesize a few records matching the BudgetLogger schema
            records = [
                {"state": {"task_complexity": 0.1}, "outcome": {"task_succeeded": True, "output_tokens": 100}, "action": {"max_thinking_tokens": 256}},
                {"state": {"task_complexity": 0.3}, "outcome": {"task_succeeded": True, "output_tokens": 500}, "action": {"max_thinking_tokens": 1024}},
                {"state": {"task_complexity": 0.6}, "outcome": {"task_succeeded": False, "output_tokens": 200}, "action": {"max_thinking_tokens": 3000}},
            ]
            with log_path.open("w") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
            result = run_retuning(base)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["records"], 3)
            # budgets dict has 4 task-type keys
            self.assertEqual(set(result["budgets"].keys()), {"trivial", "simple", "moderate", "complex"})


class LoadLatestTuningTests(unittest.TestCase):
    def test_returns_none_when_no_tunings(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            self.assertIsNone(load_latest_tuning(base))

    def test_returns_payload_after_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            run_retuning(base)
            payload = load_latest_tuning(base)
            self.assertIsNotNone(payload)
            self.assertIn("budgets", payload)
            self.assertIn("generated_at", payload)

    def test_multiple_tunings_latest_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            dir_ = tuning_dir(base)
            dir_.mkdir(parents=True, exist_ok=True)
            # write an older tuning manually
            (dir_ / "2024-01-01.json").write_text(json.dumps({"budgets": {"trivial": 100}}))
            (dir_ / "2026-04-14.json").write_text(json.dumps({"budgets": {"trivial": 256}}))
            payload = load_latest_tuning(base)
            self.assertEqual(payload["budgets"]["trivial"], 256)


class ApplyTuningTests(unittest.TestCase):
    def test_apply_overrides_optimizer_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            opt = ThinkingBudgetOptimizer(log_dir=base)
            payload = {
                "budgets": {"trivial": 999, "simple": 1, "moderate": 1, "complex": 1},
                "total_records_analyzed": 42,
                "estimated_savings_pct": 37.5,
            }
            ok = apply_tuning_to_optimizer(opt, payload)
            self.assertTrue(ok)
            # get_budget should use the new value now
            budget = opt.get_budget(complexity=0.1, economy_mode="balanced")
            self.assertGreaterEqual(budget, 256)  # floor applied

    def test_apply_missing_budgets_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".poor-cli"
            opt = ThinkingBudgetOptimizer(log_dir=base)
            self.assertFalse(apply_tuning_to_optimizer(opt, {"something": "else"}))


if __name__ == "__main__":
    unittest.main()
