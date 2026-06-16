from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import Budget, Plan, TaskSpec

PATH_RE = re.compile(r"[\w./-]+\.[A-Za-z0-9]+")
RISK_WORDS = {"auth", "payment", "migration", "concurrency", "delete", "security", "secret", "sql", "race"}
UI_WORDS = {"ui", "ux", "design", "swiftui", "css", "frontend", "view", "layout", "screen"}
PREFLIGHT_VALUE_FLAGS = {
    "--output-format",
    "--input-format",
    "--permission-mode",
    "--model",
    "--max-turns",
    "--max-budget-usd",
    "--cwd",
    "--cd",
}


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


@dataclass(frozen=True)
class RoutePreflight:
    command: str
    args: list[str]
    stdin_mode: str
    cwd: str
    labels: list[str]
    selected_route: str
    intervention_reason: str
    pass_through_command: list[str]
    route: dict[str, Any] = field(default_factory=dict)


def classify_goal_text(task: str, *, role: str = "executor") -> dict[str, Any]:
    labels = _labels(task, "medium")
    policy = "design-review" if "design" in labels else "direct-executor"
    return asdict(RouteDecision(role, policy, labels, "focused", 1, len(_paths(task)), 0))


def preflight_route(
    command: str,
    args: list[str],
    stdin_mode: str,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    *,
    prompt: str | None = None,
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env = env or os.environ
    text = prompt if prompt is not None else _prompt_from_invocation(command, args, stdin_mode)
    labels = _preflight_labels(text, command, args, stdin_mode, env)
    selected = _selected_route(labels, route or {}, command)
    return asdict(
        RoutePreflight(
            command,
            args,
            stdin_mode,
            str(cwd),
            labels,
            selected,
            _intervention(labels, route or {}, env, selected),
            [command, *args],
            route or {},
        )
    )


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


def _preflight_labels(text: str, command: str, args: list[str], stdin_mode: str, env: Mapping[str, str]) -> list[str]:
    low = " ".join([text, command, " ".join(args)]).lower()
    labels: set[str] = set()
    if any(word in low for word in ("explain", "summarize", "inspect", "what", "why", "how")):
        labels.add("explain")
    if any(word in low for word in ("review", "audit", "check", "diff")):
        labels.add("review")
    if any(word in low for word in ("fix", "edit", "change", "update", "add", "remove")):
        labels.add("small-edit")
    if len(_paths(low)) >= 2 or any(word in low for word in ("refactor", "migration", "all files", "multi-file")):
        labels.add("multi-file-edit")
    if any(word in low for word in ("test", "pytest", "failing", "failure")):
        labels.add("test-fix")
    if any(word in low for word in ("auth", "security", "secret", "token", "password")):
        labels.add("security-risk")
    if any(word in low for word in ("sql", "database", "payment", "customer", "production data")):
        labels.add("data-risk")
    if any(word in low for word in ("migration", "migrate", "schema")):
        labels.add("migration-risk")
    if any(word in low for word in UI_WORDS):
        labels.add("design-ui")
    if _paths(low) or any(word in low for word in ("symbol", "caller", "import", "function", "class", "graph")):
        labels.add("needs-graph")
    if any(word in low for word in ("web", "latest", "current", "research", "http://", "https://")):
        labels.add("needs-web")
    if any(word in low for word in ("large", "whole repo", "entire repo")):
        labels.add("high-cost")
    if "ambiguous" in low or "unclear" in low or not text.strip():
        labels.add("ambiguous")
    if "local" in low or "offline" in low or env.get("POOR_CLI_OFFLINE"):
        labels.add("local-required")
    elif labels <= {"explain", "review", "small-edit", "test-fix", "needs-graph"}:
        labels.add("local-ok")
    if stdin_mode == "pipe":
        labels.add("stdin")
    return sorted(labels)


def _selected_route(labels: list[str], route: dict[str, Any], command: str) -> str:
    label_set = set(labels)
    if command not in {"claude", "codex"}:
        return "pass-through"
    if "local-required" in label_set:
        return "local-provider"
    if "review" in label_set:
        return "fusion-review" if route.get("fusion") else "review-lane"
    if "needs-graph" in label_set:
        return "graph-enriched"
    if {"multi-file-edit", "high-cost"} <= label_set:
        return "swarm"
    if label_set & {"multi-file-edit", "high-cost", "ambiguous", "security-risk", "data-risk", "migration-risk"}:
        return "planner-reviewer"
    return "pass-through"


def _intervention(labels: list[str], route: dict[str, Any], env: Mapping[str, str], selected: str) -> str:
    if set(labels) & {"security-risk", "data-risk", "migration-risk"}:
        return "high-risk write task requires confirmation"
    if _configured_fallback(route):
        return "route fallback"
    if env.get("POOR_CLI_OFFLINE") and route.get("provider_kind") not in {"ollama", "vllm", "sglang"}:
        return "offline blocks network agent"
    if not route.get("profile") and selected != "pass-through" and route.get("reason") != "fallback to first configured profile":
        return "missing provider/config"
    return ""


def _configured_fallback(route: dict[str, Any]) -> bool:
    fallbacks = route.get("fallbacks")
    if not isinstance(fallbacks, list):
        return False
    return any(isinstance(item, dict) and bool(item.get("profile")) for item in fallbacks)


def _prompt_from_invocation(command: str, args: list[str], stdin_mode: str) -> str:
    pos = _positionals(args[1:] if command == "codex" and args[:1] == ["exec"] else args)
    if command == "claude" and ("-p" in args or "--print" in args) and pos:
        return pos[-1]
    if command == "codex" and args[:1] == ["exec"] and pos:
        return pos[-1]
    if command == "claude" and len(pos) == 1:
        return pos[0]
    return "<stdin>" if stdin_mode == "pipe" else " ".join(pos)


def _positionals(args: list[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for item in args:
        if skip:
            skip = False
        elif item in PREFLIGHT_VALUE_FLAGS:
            skip = True
        elif not item.startswith("-"):
            out.append(item)
    return out


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
