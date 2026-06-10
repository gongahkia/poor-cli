from __future__ import annotations

import json

from poor_cli.planner import parse_plan


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
