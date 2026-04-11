"""Tests for progressive instruction skill loading."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from poor_cli.instructions import InstructionManager
from poor_cli.prompts import build_tool_calling_system_instruction
from poor_cli.skills import InstructionSkillContext, SkillRegistry


class TestSkillLoading(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name)
        self.context = InstructionSkillContext(current_dir=str(self.repo))

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_builtin_instruction_skill_count(self) -> None:
        registry = SkillRegistry(self.repo)
        self.assertGreaterEqual(len(registry.list_instruction_skills()), 8)

    def test_simple_prompt_loads_only_core_skill(self) -> None:
        registry = SkillRegistry(self.repo)
        plan = registry.build_instruction_plan("fix typo in README", self.context)
        self.assertEqual(("core",), plan.system_skill_names)
        self.assertEqual((), plan.prompt_skill_names)

    def test_keyword_classifier_routes_specialized_skills(self) -> None:
        registry = SkillRegistry(self.repo)
        plan = registry.build_instruction_plan(
            "run the tests, debug the failure, then commit and push",
            self.context,
        )
        self.assertIn("testing", plan.prompt_skill_names)
        self.assertIn("debugging", plan.prompt_skill_names)
        self.assertIn("git", plan.prompt_skill_names)

    def test_context_classifier_routes_multiplayer_skill(self) -> None:
        registry = SkillRegistry(self.repo)
        context = InstructionSkillContext(
            current_dir=str(self.repo),
            multiplayer_active=True,
        )
        plan = registry.build_instruction_plan("show room state", context)
        self.assertIn("multiplayer", plan.prompt_skill_names)

    def test_user_defined_repo_skill_is_loaded(self) -> None:
        skill_dir = self.repo / ".poor-cli" / "skills"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "graphql.md").write_text(
            "---\nkeywords:\n  - graphql\n  - schema drift\n---\nCustom GraphQL instructions.",
            encoding="utf-8",
        )
        with patch("poor_cli.skills._skip_untrusted_repo_skills", return_value=False):
            registry = SkillRegistry(self.repo)
            plan = registry.build_instruction_plan("fix graphql schema drift", self.context)
        self.assertIn("graphql", plan.prompt_skill_names)

    def test_instruction_snapshot_reports_loaded_skills(self) -> None:
        registry = SkillRegistry(self.repo)
        plan = registry.build_instruction_plan("run tests after refactor", self.context)
        snapshot = InstructionManager(self.repo).build_snapshot(
            user_prompt="run tests after refactor",
            skill_context=self.context,
            skill_plan=plan,
        )
        payload = snapshot.to_dict()
        self.assertIn("core", payload["loadedSkills"])
        self.assertIn("testing", payload["loadedSkills"])
        self.assertIn("refactoring", payload["loadedSkills"])
        self.assertIn("Task Skill: testing", payload["renderedPromptPrefix"])

    def test_classifier_failure_loads_all_skills(self) -> None:
        registry = SkillRegistry(self.repo)
        with patch("poor_cli.skills._match_instruction_skills", side_effect=RuntimeError("boom")):
            plan = registry.build_instruction_plan("something strange", self.context)
        self.assertTrue(plan.fallback_loaded_all)
        available = {skill.name for skill in registry.list_instruction_skills()}
        self.assertTrue(available.issubset(set(plan.all_skill_names)))

    def test_system_instruction_payload_is_reduced(self) -> None:
        instruction = build_tool_calling_system_instruction(str(self.repo))
        self.assertLess(len(instruction), 2000)
