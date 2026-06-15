from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .models import Budget, Plan, TaskSpec

PATH_RE = re.compile(r"[\w./-]+\.[A-Za-z0-9]+")
RISK_WORDS = {"auth", "payment", "migration", "concurrency", "delete", "security", "secret", "sql", "race"}
UI_WORDS = {"ui", "ux", "design", "swiftui", "css", "frontend", "view", "layout", "screen"}


@dataclass(frozen=True)
class RouteDecision:
    role: str
    policy: str
    labels: list[str]
    test_scope: str
    task_count: int
    file_count: int
    graph_hits: int
    worker_jobs: list[dict[str, Any]] = field(default_factory=list)
    merge_constraints: list[str] = field(default_factory=list)


def classify_goal_text(task: str, *, role: str = "executor") -> dict[str, Any]:
    labels = _labels(task, "medium")
    policy = "design-review" if "design" in labels else "direct-executor"
    return asdict(RouteDecision(role, policy, labels, "focused", 1, len(_paths(task)), 0))


def classify_task(goal: str, plan: Plan, task: TaskSpec, budget: Budget, *, graph_mode: bool = False) -> RouteDecision:
    text = " ".join([goal, task.title, task.objective, task.task_type, task.complexity, task.risk, task.required_context])
    file_count = len(_paths(" ".join([text, str(task.metadata), task.required_context])))
    graph_hits = _int(task.metadata.get("graph_hits") or (1 if task.metadata.get("graph_mode") or graph_mode else 0))
    labels = _labels(text, task.risk)
    parallel = budget.max_parallel_agents > 1 or any(word in text.lower() for word in ("parallel", "independent", "batch"))
    hard = task.complexity in {"hard", "high", "large"} or "ambiguous" in text.lower() or task.risk == "high"
    if "design" in labels:
        policy = "design-review"
    elif parallel and len(plan.tasks) > 1:
        policy = "plan-task"
    elif hard:
        policy = "planner-reviewer"
    elif len(plan.tasks) <= 2 and file_count <= 3 and task.risk in {"low", "medium"}:
        policy = "direct-executor"
    else:
        policy = "planner-reviewer"
    jobs = _worker_jobs(plan) if policy == "plan-task" else []
    constraints = ["preserve task dependencies", "merge only reviewed patches"] if jobs else []
    return RouteDecision("executor", policy, labels, _test_scope(task, labels), len(plan.tasks), file_count, graph_hits, jobs, constraints)


def _labels(text: str, risk: str) -> list[str]:
    low = text.lower()
    labels = {word for word in RISK_WORDS if word in low}
    if risk == "high":
        labels.add("high-risk")
    if any(word in low for word in UI_WORDS):
        labels.add("design")
    if "ambiguous" in low or "unclear" in low:
        labels.add("ambiguous")
    return sorted(labels)


def _paths(text: str) -> set[str]:
    return {match.group(0).strip(".,:;") for match in PATH_RE.finditer(text)}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _test_scope(task: TaskSpec, labels: list[str]) -> str:
    if task.validation:
        return "focused"
    if "high-risk" in labels or task.risk == "high":
        return "full"
    if task.task_type in {"benchmark", "performance"}:
        return "bench"
    return "focused" if task.task_type == "implementation" else "none"


def _worker_jobs(plan: Plan) -> list[dict[str, Any]]:
    return [
        {"task_id": task.task_id, "title": task.title, "dependencies": task.dependencies, "merge": "patch-after-review"}
        for task in plan.tasks
        if not task.dependencies
    ]
