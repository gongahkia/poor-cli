from __future__ import annotations

import json
from pathlib import Path

import pytest

from poor_cli.planner import Planner, PlannerError, parse_plan


def test_parse_plan_schema() -> None:
    plan = parse_plan(
        json.dumps(
            {
                "problem_summary": "summary",
                "architecture_assessment": "assessment",
                "assumptions": ["a"],
                "risks": ["r"],
                "tasks": [{"title": "Do it", "objective": "obj", "suggested_agent": "generic", "validation": ["check"]}],
                "validation_strategy": ["pytest"],
                "routing_strategy": "generic",
                "estimated_cost": {"tokens": None, "usd": None},
            }
        )
    )
    assert plan.tasks[0].title == "Do it"
    assert plan.tasks[0].suggested_agent == "generic"


def test_parse_plan_accepts_string_list_fields() -> None:
    plan = parse_plan(
        json.dumps(
            {
                "problem_summary": "summary",
                "architecture_assessment": "assessment",
                "assumptions": "single assumption",
                "risks": "single risk",
                "tasks": [
                    {
                        "title": "Do it",
                        "objective": "obj",
                        "dependencies": "prior task",
                        "validation": "pytest",
                    }
                ],
                "validation_strategy": "run tests",
                "routing_strategy": "generic",
                "estimated_cost": {"tokens": None, "usd": None},
            }
        )
    )

    assert plan.assumptions == ["single assumption"]
    assert plan.risks == ["single risk"]
    assert plan.validation_strategy == ["run tests"]
    assert plan.tasks[0].dependencies == ["prior task"]
    assert plan.tasks[0].validation == ["pytest"]


def test_offline_planner_requires_custom_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("POOR_CLI_OFFLINE", "1")
    monkeypatch.delenv("POOR_CLI_PLANNER_COMMAND", raising=False)

    with pytest.raises(PlannerError, match="offline mode requires"):
        Planner(tmp_path, []).create("goal")
