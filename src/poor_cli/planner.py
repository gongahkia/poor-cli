from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .agents import detect_agents
from .models import AgentInfo, Plan, TaskSpec, make_id


class PlannerError(RuntimeError):
    pass


SYSTEM_PROMPT = """Return only valid JSON for a poor-cli orchestration plan.
Fields: problem_summary, architecture_assessment, assumptions, risks, tasks,
validation_strategy, routing_strategy, estimated_cost, requires_user_confirmation.
Each task needs title, objective, task_type, complexity, risk, required_context,
dependencies, suggested_agent, validation. Prefer small sequential tasks."""


class Planner:
    def __init__(self, repo_path: Path, agents: list[AgentInfo] | None = None):
        self.repo_path = repo_path
        self.agents = agents or detect_agents()

    def create(self, goal: str) -> tuple[Plan, str, str]:
        prompt = self._prompt(goal)
        response = self._call(prompt)
        plan = parse_plan(response)
        return plan, prompt, response

    def _prompt(self, goal: str) -> str:
        agent_lines = [f"- {agent.name}: {', '.join(agent.capabilities)}" for agent in self.agents]
        return "\n".join(
            [
                SYSTEM_PROMPT,
                "",
                f"Goal: {goal}",
                f"Repository: {self.repo_path}",
                "Available agents:",
                *agent_lines,
            ]
        )

    def _call(self, prompt: str) -> str:
        env_command = os.environ.get("POOR_CLI_PLANNER_COMMAND")
        timeout = int(os.environ.get("POOR_CLI_PLANNER_TIMEOUT", "300"))
        if env_command:
            command = shlex.split(env_command)
            result = subprocess.run(command, input=prompt, cwd=self.repo_path, text=True, capture_output=True, timeout=timeout, check=False)
            if result.returncode != 0:
                raise PlannerError(f"planner command failed: {result.stderr.strip()}")
            return result.stdout
        claude = shutil.which("claude")
        if claude:
            result = subprocess.run(
                [claude, "-p", "--permission-mode", "plan", "--output-format", "text", "--system-prompt", SYSTEM_PROMPT, prompt],
                cwd=self.repo_path,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                raise PlannerError(f"claude planner failed: {result.stderr.strip()}")
            return result.stdout
        codex = shutil.which("codex")
        if codex:
            result = subprocess.run(
                [codex, "exec", "--sandbox", "read-only", "--ask-for-approval", "never", prompt],
                cwd=self.repo_path,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                raise PlannerError(f"codex planner failed: {result.stderr.strip()}")
            return result.stdout
        raise PlannerError("no planner agent available; install claude/codex or set POOR_CLI_PLANNER_COMMAND")


def parse_plan(text: str) -> Plan:
    data = _extract_json(text)
    tasks = []
    for raw in data.get("tasks") or []:
        if not isinstance(raw, dict):
            continue
        tasks.append(
            TaskSpec(
                task_id=make_id("task"),
                title=str(raw.get("title") or "Untitled task"),
                objective=str(raw.get("objective") or raw.get("title") or ""),
                task_type=str(raw.get("task_type") or "implementation"),
                complexity=str(raw.get("complexity") or "medium"),
                risk=str(raw.get("risk") or "medium"),
                required_context=str(raw.get("required_context") or "small"),
                dependencies=_string_list(raw.get("dependencies")),
                suggested_agent=_clean_agent(raw.get("suggested_agent")),
                validation=_string_list(raw.get("validation")),
                metadata={k: v for k, v in raw.items() if k not in _TASK_KEYS},
            )
        )
    if not tasks:
        raise PlannerError("planner returned no tasks")
    return Plan(
        plan_id=make_id("plan"),
        problem_summary=str(data.get("problem_summary") or ""),
        architecture_assessment=str(data.get("architecture_assessment") or ""),
        assumptions=_string_list(data.get("assumptions")),
        risks=_string_list(data.get("risks")),
        tasks=tasks,
        validation_strategy=_string_list(data.get("validation_strategy")),
        routing_strategy=str(data.get("routing_strategy") or ""),
        estimated_cost=data.get("estimated_cost") if isinstance(data.get("estimated_cost"), dict) else {"tokens": None, "usd": None},
        requires_user_confirmation=bool(data.get("requires_user_confirmation", True)),
    )


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise PlannerError("planner did not return JSON") from None
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise PlannerError("planner JSON root must be an object")
    return value


def _clean_agent(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


_TASK_KEYS = {"title", "objective", "task_type", "complexity", "risk", "required_context", "dependencies", "suggested_agent", "validation"}
