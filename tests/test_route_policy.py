from __future__ import annotations

from poor_cli.models import Budget, Plan, TaskSpec
from poor_cli.route_policy import classify_task


def _plan(task: TaskSpec) -> Plan:
    return Plan("p", "summary", "arch", [], [], [task], [], "route", {})


def test_route_policy_classifies_small_design_and_hard_tasks() -> None:
    small = TaskSpec("t1", "Fix parser", "edit src/parser.py", risk="low")
    design = TaskSpec("t2", "Update UI", "change SwiftUI layout", task_type="design")
    hard = TaskSpec("t3", "Auth migration", "ambiguous auth migration", complexity="hard", risk="high")

    assert classify_task("goal", _plan(small), small, Budget()).policy == "direct-executor"
    assert classify_task("goal", _plan(design), design, Budget()).policy == "design-review"
    decision = classify_task("goal", _plan(hard), hard, Budget())
    assert decision.policy == "planner-reviewer"
    assert "high-risk" in decision.labels


def test_route_policy_emits_parallel_worker_jobs() -> None:
    first = TaskSpec("t1", "A", "independent file a.py")
    second = TaskSpec("t2", "B", "independent file b.py")
    plan = Plan("p", "summary", "arch", [], [], [first, second], [], "route", {})

    decision = classify_task("parallel batch", plan, first, Budget(max_parallel_agents=2))

    assert decision.policy == "plan-task"
    assert [job["task_id"] for job in decision.worker_jobs] == ["t1", "t2"]
