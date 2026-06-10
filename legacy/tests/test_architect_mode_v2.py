"""M4 architect mode improvements: plan validation + presets + cost tracking."""

from __future__ import annotations

import unittest

from poor_cli.architect_mode import (
    PRESET_PAIRS,
    ArchitectConfig,
    ArchitectMode,
    ArchitectPlan,
    ArchitectPlanStep,
    validate_plan,
)


class PresetPairTests(unittest.TestCase):
    def test_known_presets_exist(self):
        for name in ("anthropic-gemini", "openai-gemini", "anthropic-ollama", "all-local-hf"):
            self.assertIn(name, PRESET_PAIRS)

    def test_apply_preset_copies_fields(self):
        cfg = ArchitectConfig()
        self.assertTrue(cfg.apply_preset("anthropic-gemini"))
        self.assertEqual(cfg.architect_provider, "anthropic")
        self.assertEqual(cfg.editor_provider, "gemini")

    def test_apply_unknown_preset_returns_false(self):
        cfg = ArchitectConfig()
        self.assertFalse(cfg.apply_preset("does-not-exist"))
        self.assertEqual(cfg.architect_provider, "")


class PlanValidationTests(unittest.TestCase):
    def test_valid_dict_plan_parses(self):
        raw = {
            "goal": "refactor auth",
            "rationale": "current code is tangled",
            "steps": [
                {"id": "s1", "description": "extract helper", "tools": ["edit_file"], "files": ["src/auth.py"]},
                {"id": "s2", "description": "add tests", "acceptance": "tests pass"},
            ],
        }
        plan, errors = validate_plan(raw)
        self.assertEqual(errors, [])
        self.assertIsInstance(plan, ArchitectPlan)
        self.assertEqual(plan.goal, "refactor auth")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].id, "s1")
        self.assertIn("edit_file", plan.steps[0].tools)

    def test_valid_json_string_parses(self):
        raw = '{"goal": "x", "steps": [{"id": "a", "description": "do it"}]}'
        plan, errors = validate_plan(raw)
        self.assertEqual(errors, [])
        self.assertIsNotNone(plan)
        self.assertEqual(plan.goal, "x")

    def test_json_wrapped_in_code_fence_parses(self):
        raw = '```json\n{"goal": "x", "steps": [{"id": "a", "description": "do it"}]}\n```'
        plan, errors = validate_plan(raw)
        self.assertEqual(errors, [])
        self.assertIsNotNone(plan)

    def test_missing_goal_errors(self):
        plan, errors = validate_plan({"steps": [{"id": "a", "description": "x"}]})
        self.assertIn("missing_goal", errors)

    def test_missing_steps_errors(self):
        plan, errors = validate_plan({"goal": "x"})
        self.assertIn("steps_must_be_nonempty_array", errors)
        self.assertIsNone(plan)

    def test_step_without_id_or_description_soft_error(self):
        plan, errors = validate_plan({
            "goal": "x",
            "steps": [
                {"id": "ok", "description": "good"},
                {"id": "", "description": "no id"},
                {"id": "a", "description": ""},
            ],
        })
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 1)
        self.assertIn("step_1_missing_id", errors)
        self.assertIn("step_2_missing_description", errors)

    def test_invalid_json_rejected(self):
        plan, errors = validate_plan("not json")
        self.assertIn("invalid_json", errors)
        self.assertIsNone(plan)

    def test_render_prefix_includes_steps(self):
        plan = ArchitectPlan(
            goal="refactor",
            rationale="cleanup",
            steps=[
                ArchitectPlanStep(id="s1", description="do it", tools=["bash"], files=["a.py"], acceptance="x"),
            ],
        )
        text = plan.render_prefix()
        self.assertIn("Goal: refactor", text)
        self.assertIn("Rationale: cleanup", text)
        self.assertIn("do it", text)
        self.assertIn("files: a.py", text)
        self.assertIn("tools: bash", text)
        self.assertIn("acceptance: x", text)


class CostTrackingTests(unittest.TestCase):
    def _mode(self) -> ArchitectMode:
        cfg = ArchitectConfig(enabled=True, architect_provider="anthropic", architect_model="x",
                              editor_provider="gemini", editor_model="y")
        return ArchitectMode(cfg)

    def test_record_cost_increments_bucket(self):
        m = self._mode()
        m.record_cost("architect", tokens=1000, usd=0.003)
        m.record_cost("editor", tokens=2000, usd=0.0006)
        breakdown = m.cost_breakdown()
        self.assertEqual(breakdown["architect"]["tokens"], 1000)
        self.assertEqual(breakdown["editor"]["tokens"], 2000)
        self.assertAlmostEqual(breakdown["totalUsd"], 0.0036)
        self.assertAlmostEqual(breakdown["architectShare"], 0.003 / 0.0036, places=3)

    def test_record_cost_rejects_unknown_phase(self):
        m = self._mode()
        m.record_cost("mystery", tokens=500, usd=0.01)
        self.assertEqual(m.cost_breakdown()["totalUsd"], 0.0)

    def test_negative_tokens_clamped_to_zero(self):
        m = self._mode()
        m.record_cost("editor", tokens=-100, usd=-0.5)
        self.assertEqual(m.cost_breakdown()["editor"]["tokens"], 0)
        self.assertEqual(m.cost_breakdown()["editor"]["usd"], 0.0)

    def test_cost_breakdown_in_status(self):
        m = self._mode()
        m.record_cost("architect", tokens=100, usd=0.0003)
        status = m.format_status()
        self.assertIn("cost_breakdown", status)
        self.assertEqual(status["cost_breakdown"]["architect"]["tokens"], 100)


class PlanIntegrationTests(unittest.TestCase):
    def test_switch_to_editor_with_structured_plan_renders_prefix(self):
        import asyncio
        cfg = ArchitectConfig(enabled=True, architect_provider="anthropic", architect_model="x",
                              editor_provider="gemini", editor_model="y")
        mode = ArchitectMode(cfg)

        class FakeLifecycle:
            async def switch_provider(self, provider, model):
                return True

        mode = ArchitectMode(cfg, lifecycle_service=FakeLifecycle())
        plan_json = '{"goal": "fix auth", "steps": [{"id": "a", "description": "extract helper"}]}'
        asyncio.run(mode.switch_to_editor(None, plan_json))
        prefix = mode.get_plan_prefix()
        self.assertIn("Goal: fix auth", prefix)
        self.assertIn("extract helper", prefix)
        self.assertIsNotNone(mode.parsed_plan)

    def test_switch_to_editor_with_free_text_plan_falls_back(self):
        import asyncio
        cfg = ArchitectConfig(enabled=True, architect_provider="anthropic", architect_model="x",
                              editor_provider="gemini", editor_model="y")

        class FakeLifecycle:
            async def switch_provider(self, provider, model):
                return True

        mode = ArchitectMode(cfg, lifecycle_service=FakeLifecycle())
        asyncio.run(mode.switch_to_editor(None, "free text plan without JSON"))
        prefix = mode.get_plan_prefix()
        self.assertIn("Plan from architect model", prefix)
        self.assertIn("free text plan", prefix)
        self.assertIsNone(mode.parsed_plan)


if __name__ == "__main__":
    unittest.main()
