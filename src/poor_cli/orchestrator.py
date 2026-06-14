from __future__ import annotations

import subprocess
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .agents import AgentResult, AgentRunner, build_agent_prompt, detect_agents
from .hooks import Hook, HookManager
from .models import Budget, ContextPacket, Plan, TaskSpec, make_id, to_jsonable
from .planner import Planner
from .store import RunStore


class Orchestrator:
    def __init__(self, store: RunStore, repo_path: Path | None = None, hooks: Iterable[Hook] | HookManager | None = None):
        self.store = store
        self.repo_path = (repo_path or Path.cwd()).resolve()
        self.hooks = hooks if isinstance(hooks, HookManager) else HookManager.from_hooks(hooks)

    def plan(self, goal: str, budget: Budget, *, graph_mode: bool = False) -> tuple[str, Plan]:
        run_id = self._create_run(goal, budget)
        agents = detect_agents()
        self.store.insert_agents(run_id, agents)
        self.store.append_event(run_id, "agents.detected", {"agents": [asdict(agent) for agent in agents]})
        planner = Planner(self.repo_path, agents, graph_mode=graph_mode)
        try:
            plan, prompt, response = planner.create(goal)
        except Exception as exc:
            error_art = self.store.put_artifact(
                run_id=run_id,
                kind="planner.error",
                data={"type": type(exc).__name__, "error": str(exc)},
            )
            self.store.append_event(run_id, "planner.failed", {"artifact_id": error_art.artifact_id, "error": str(exc)})
            self.store.set_run_status(run_id, "failed", "planner failed")
            self.store.append_event(run_id, "run.failed", {"summary": "planner failed"})
            raise
        if graph_mode:
            for task in plan.tasks:
                task.metadata["graph_mode"] = True
        prompt_art = self.store.put_artifact(run_id=run_id, kind="planner.prompt", data=prompt, media_type="text/plain")
        response_art = self.store.put_artifact(run_id=run_id, kind="planner.response", data=response, media_type="text/plain")
        plan_art = self.store.put_artifact(run_id=run_id, kind="plan.json", data=to_jsonable(plan))
        self.store.set_run_plan(run_id, plan.plan_id)
        self.store.insert_tasks(run_id, plan.tasks)
        self.store.append_event(
            run_id,
            "plan.created",
            {
                "plan_id": plan.plan_id,
                "artifact_id": plan_art.artifact_id,
                "prompt_artifact_id": prompt_art.artifact_id,
                "response_artifact_id": response_art.artifact_id,
                "task_count": len(plan.tasks),
                "graph_mode": graph_mode,
            },
        )
        for task in plan.tasks:
            self.store.append_event(run_id, "task.created", {"task": to_jsonable(task)}, task.task_id)
        self.store.set_run_status(run_id, "planned")
        return run_id, plan

    def run(self, run_id: str, budget: Budget, selected_agents: set[str] | None = None, dry_run: bool = False) -> int:
        run = self.store.get_run(run_id)
        agents = detect_agents()
        if selected_agents:
            agents = [agent for agent in agents if agent.name in selected_agents or agent.agent_id in selected_agents]
        if not agents:
            raise RuntimeError("no selected agents available")
        runner = AgentRunner(agents)
        tasks = [_task_from_row(row) for row in self.store.list_tasks(run_id)]
        self.store.set_run_status(run_id, "running")
        exit_code = 0
        for task in tasks:
            agent = runner.choose(task.suggested_agent)
            self.hooks.before_turn({"run_id": run_id, "task_id": task.task_id, "title": task.title, "agent": agent.name})
            packet = self._context_packet(run, task)
            packet_art = self.store.put_artifact(run_id=run_id, task_id=task.task_id, kind="context.packet", data=to_jsonable(packet))
            self.store.set_task_status(task.task_id, "assigned", assigned_agent=agent.name, context_packet_id=packet_art.artifact_id)
            self.store.append_event(
                run_id,
                "context.created",
                {"packet_id": packet.packet_id, "artifact_id": packet_art.artifact_id},
                task.task_id,
            )
            self.store.append_event(run_id, "task.assigned", {"agent_id": agent.agent_id, "agent": agent.name}, task.task_id)
            if dry_run:
                self.store.set_task_status(task.task_id, "skipped")
                self.store.append_event(run_id, "task.skipped", {"reason": "dry-run"}, task.task_id)
                continue
            agent_prompt = build_agent_prompt(str(run["user_goal"]), task, packet.task_prompt)
            input_art = self.store.put_artifact(
                run_id=run_id,
                task_id=task.task_id,
                kind="agent.input",
                data={"agent_id": agent.agent_id, "agent": agent.name, "prompt": agent_prompt},
            )
            self.store.append_event(run_id, "agent.input.created", {"artifact_id": input_art.artifact_id}, task.task_id)
            self.store.append_event(run_id, "agent.started", {"agent_id": agent.agent_id, "command": agent.command}, task.task_id)
            try:
                result = runner.run(
                    agent,
                    goal=str(run["user_goal"]),
                    task=task,
                    context=packet.task_prompt,
                    workdir=self.repo_path,
                    budget_usd=budget.max_usd,
                )
                agent_event = "agent.completed"
            except Exception as exc:
                result = AgentResult(agent.agent_id, [], 1, "", f"{type(exc).__name__}: {exc}")
                agent_event = "agent.failed"
            result_art = self.store.put_artifact(run_id=run_id, task_id=task.task_id, kind="agent.result", data=to_jsonable(result))
            self.store.append_event(
                run_id,
                agent_event,
                {"agent_id": result.agent_id, "returncode": result.returncode, "artifact_id": result_art.artifact_id},
                task.task_id,
            )
            if result.returncode == 0:
                handoff_art = self._handoff_packet(run_id, task, agent.name, "completed", result_art.artifact_id, result.returncode)
                self.store.set_task_status(task.task_id, "completed", result_artifact_id=result_art.artifact_id)
                self.store.append_event(run_id, "handoff.created", {"artifact_id": handoff_art.artifact_id}, task.task_id)
                self.store.append_event(run_id, "task.completed", {"result_artifact_id": result_art.artifact_id}, task.task_id)
            else:
                exit_code = result.returncode or 1
                handoff_art = self._handoff_packet(run_id, task, agent.name, "failed", result_art.artifact_id, result.returncode)
                self.store.set_task_status(task.task_id, "failed", result_artifact_id=result_art.artifact_id)
                self.store.append_event(run_id, "handoff.created", {"artifact_id": handoff_art.artifact_id}, task.task_id)
                self.store.append_event(
                    run_id,
                    "task.failed",
                    {"result_artifact_id": result_art.artifact_id, "returncode": result.returncode},
                    task.task_id,
                )
                break
        final_status = "failed" if exit_code else "completed"
        summary = self._summary(run_id)
        self.store.set_run_status(run_id, final_status, summary)
        self.store.append_event(run_id, f"run.{final_status}", {"summary": summary})
        self.hooks.after_run({"run_id": run_id, "status": final_status, "summary": summary})
        return exit_code

    def _create_run(self, goal: str, budget: Budget) -> str:
        commit = _git(["rev-parse", "HEAD"], self.repo_path)
        run_id = self.store.create_run(
            user_goal=goal,
            repo_path=self.repo_path,
            git_commit_start=commit,
            mode=budget.mode,
            budget=to_jsonable(budget),
        )
        self.store.append_event(run_id, "run.created", {"goal": goal, "budget": to_jsonable(budget)})
        self.store.append_event(run_id, "repo.scanned", {"repo_path": str(self.repo_path), "git_commit_start": commit})
        return run_id

    def _context_packet(self, run: dict[str, Any], task: TaskSpec) -> ContextPacket:
        lines = [
            f"Run: {run['run_id']}",
            f"Goal: {run['user_goal']}",
            f"Task objective: {task.objective}",
            f"Dependencies: {', '.join(task.dependencies) if task.dependencies else 'none'}",
        ]
        if task.metadata.get("graph_mode") is True:
            lines.append(
                "Graph mode: prefer symbolic repo navigation before grep; "
                "use find_symbol, definition_of, callers_of, imports_of, and subgraph when available."
            )
        lines.extend(
            [
                "Constraints: preserve repo intent; keep changes scoped; record validation.",
                "Expected output: changed files if needed plus concise validation summary.",
            ]
        )
        prompt = "\n".join(lines)
        return ContextPacket(
            packet_id=make_id("ctx"),
            run_id=str(run["run_id"]),
            task_id=task.task_id,
            token_estimate=max(1, len(prompt) // 4),
            included_files=[],
            included_summaries=[],
            constraints=["keep changes scoped", "report validation", "do not auto-merge"],
            task_prompt=prompt,
            validation_instructions=task.validation,
            handoff_instructions=["summarize changes", "list commands run", "list unresolved blockers"],
        )

    def _handoff_packet(self, run_id: str, task: TaskSpec, agent: str, status: str, result_artifact_id: str, returncode: int) -> Any:
        return self.store.put_artifact(
            run_id=run_id,
            task_id=task.task_id,
            kind="handoff.packet",
            data={
                "run_id": run_id,
                "task_id": task.task_id,
                "title": task.title,
                "status": status,
                "agent": agent,
                "result_artifact_id": result_artifact_id,
                "returncode": returncode,
                "next_steps": task.validation,
            },
        )

    def _summary(self, run_id: str) -> str:
        tasks = self.store.list_tasks(run_id)
        done = sum(1 for task in tasks if task["status"] == "completed")
        failed = sum(1 for task in tasks if task["status"] == "failed")
        return f"{done}/{len(tasks)} tasks completed, {failed} failed"


def _task_from_row(row: dict[str, Any]) -> TaskSpec:
    metadata = row.get("metadata")
    return TaskSpec(
        task_id=str(row["task_id"]),
        title=str(row["title"]),
        objective=str(row["objective"]),
        task_type=str(row["task_type"]),
        complexity=str(row["complexity"]),
        risk=str(row["risk"]),
        required_context=str(row["required_context"]),
        dependencies=list(row.get("dependencies") or []),
        suggested_agent=row.get("assigned_agent") or None,
        validation=list(row.get("validation") or []),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, timeout=5, check=False)
    except Exception:
        return None
    return result.stdout.strip() if result.returncode == 0 else None
