from __future__ import annotations

import subprocess
import time
from collections.abc import Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
from os import environ
from pathlib import Path
from typing import Any

from .agents import AgentResult, AgentRunner, build_agent_prompt, detect_agents
from .artifacts import write_plan_artifacts, write_review_verify_artifacts, write_worker_artifacts
from .config import explain_route, load_config
from .graph_context import graph_context_text
from .hooks import Hook, HookManager
from .models import Budget, ContextPacket, Plan, TaskSpec, make_id, to_jsonable
from .planner import Planner
from .route_policy import classify_task
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
        graph_context = planner.graph_context if graph_mode else None
        if graph_context is not None:
            graph_art = self.store.put_artifact(run_id=run_id, kind="graph.context", data=graph_context)
            self.store.append_event(
                run_id,
                "graph.context.created",
                {
                    "artifact_id": graph_art.artifact_id,
                    "available": bool(graph_context.get("available")),
                    "warning": str(graph_context.get("warning") or ""),
                },
            )
        if graph_mode:
            for task in plan.tasks:
                task.metadata["graph_mode"] = True
                if graph_context is not None:
                    task.metadata["graph_context"] = graph_context
        route_config = _route_config(load_config(self.repo_path), "executor")
        for task in plan.tasks:
            decision = classify_task(goal, plan, task, budget, graph_mode=graph_mode)
            task.metadata["route_policy"] = asdict(decision)
            task.metadata["route_config"] = route_config
            self.store.append_event(run_id, "route.policy.selected", {"task_id": task.task_id, "policy": asdict(decision)}, task.task_id)
        prompt_art = self.store.put_artifact(run_id=run_id, kind="planner.prompt", data=prompt, media_type="text/plain")
        response_art = self.store.put_artifact(run_id=run_id, kind="planner.response", data=response, media_type="text/plain")
        plan_art = self.store.put_artifact(run_id=run_id, kind="plan.json", data=to_jsonable(plan))
        write_plan_artifacts(self.store, run_id, plan)
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

    def run(self, run_id: str, budget: Budget, selected_agents: set[str] | None = None, dry_run: bool = False, *,
            allow_overlap: bool = False, cancel: Any | None = None) -> int:
        run = self.store.get_run(run_id)
        agents = detect_agents()
        if selected_agents:
            agents = [agent for agent in agents if agent.name in selected_agents or agent.agent_id in selected_agents]
        if not agents:
            raise RuntimeError("no selected agents available")
        runner = AgentRunner(agents)
        tasks = [_task_from_row(row) for row in self.store.list_tasks(run_id)]
        self.store.set_run_status(run_id, "running")
        started = time.monotonic()
        cap = _cap(budget)
        self.store.append_event(run_id, "scheduler.started", {"tasks": len(tasks), "max_parallel": cap, "allow_overlap": allow_overlap})
        exit_code = self._run_dag(run, tasks, runner, budget, dry_run, cap, allow_overlap, cancel)
        final_status = "cancelled" if cancel is not None and cancel.is_set() else ("failed" if exit_code else "completed")
        summary = self._summary(run_id)
        self._scheduler_ledger(run_id, started, cap)
        self.store.set_run_status(run_id, final_status, summary)
        write_review_verify_artifacts(self.store, run_id, status=final_status, summary=summary)
        self.store.append_event(run_id, f"run.{final_status}", {"summary": summary})
        self.hooks.after_run({"run_id": run_id, "status": final_status, "summary": summary})
        return exit_code

    def execute_one(self, run_id: str, task: TaskSpec, ordinal: int, runner: AgentRunner, budget: Budget, workdir: Path,
                    cancel: Any | None = None) -> int:
        run = self.store.get_run(run_id)
        agent = runner.choose(task.suggested_agent)
        self.hooks.before_turn({"run_id": run_id, "task_id": task.task_id, "title": task.title, "agent": agent.name})
        packet = self._context_packet(run, task)
        packet_art = self.store.put_artifact(run_id=run_id, task_id=task.task_id, kind="context.packet", data=to_jsonable(packet))
        self.store.set_task_status(task.task_id, "assigned", assigned_agent=agent.name, context_packet_id=packet_art.artifact_id)
        self.store.append_event(run_id, "context.created", {"packet_id": packet.packet_id, "artifact_id": packet_art.artifact_id},
                                task.task_id)
        self.store.append_event(run_id, "task.assigned", {"agent_id": agent.agent_id, "agent": agent.name}, task.task_id)
        preexisting_dirty = (_git(["status", "--short"], workdir) or "").splitlines()
        agent_prompt = build_agent_prompt(str(run["user_goal"]), task, packet.task_prompt)
        input_art = self.store.put_artifact(
            run_id=run_id, task_id=task.task_id, kind="agent.input",
            data={"agent_id": agent.agent_id, "agent": agent.name, "prompt": agent_prompt}
        )
        self.store.append_event(run_id, "agent.input.created", {"artifact_id": input_art.artifact_id}, task.task_id)
        self.store.append_event(run_id, "agent.started", {"agent_id": agent.agent_id, "command": agent.command}, task.task_id)
        try:
            result = runner.run(
                agent, goal=str(run["user_goal"]), task=task, context=packet.task_prompt, workdir=workdir, budget_usd=budget.max_usd,
                store=self.store, run_id=run_id, hooks=self.hooks, cancel=cancel
            )
            agent_event = "agent.completed" if result.returncode == 0 else "agent.failed"
        except Exception as exc:
            result = AgentResult(agent.agent_id, [], 1, "", f"{type(exc).__name__}: {exc}")
            agent_event = "agent.failed"
        result_art = self.store.put_artifact(run_id=run_id, task_id=task.task_id, kind="agent.result", data=to_jsonable(result))
        write_worker_artifacts(self.store, run_id, task, ordinal, to_jsonable(result), workdir, preexisting_dirty=preexisting_dirty)
        self.store.append_event(
            run_id, agent_event,
            {"agent_id": result.agent_id, "returncode": result.returncode, "artifact_id": result_art.artifact_id}, task.task_id
        )
        status = "completed" if result.returncode == 0 else "failed"
        handoff_art = self._handoff_packet(run_id, task, agent.name, status, result_art.artifact_id, result.returncode)
        self.store.set_task_status(task.task_id, status, result_artifact_id=result_art.artifact_id)
        self.store.append_event(run_id, "handoff.created", {"artifact_id": handoff_art.artifact_id}, task.task_id)
        self.store.append_event(run_id, f"task.{status}", {"result_artifact_id": result_art.artifact_id, "returncode": result.returncode},
                                task.task_id)
        return int(result.returncode or 0)

    def _run_dag(self, run: dict[str, Any], tasks: list[TaskSpec], runner: AgentRunner, budget: Budget, dry_run: bool, cap: int,
                 allow_overlap: bool, cancel: Any | None) -> int:
        deps = _deps(tasks)
        unknown = sorted({dep for values in deps.values() for dep in values if dep not in deps})
        if unknown:
            self.store.append_event(str(run["run_id"]), "scheduler.failed", {"reason": "unknown dependencies", "dependencies": unknown})
            return 1
        pending = {task.task_id for task in tasks}
        done: set[str] = set()
        failed: set[str] = set()
        blocked: set[str] = set()
        by_id = {task.task_id: task for task in tasks}
        ords = {task.task_id: index + 1 for index, task in enumerate(tasks)}
        exit_code = 0
        if dry_run:
            for task in tasks:
                self.store.set_task_status(task.task_id, "skipped")
                self.store.append_event(str(run["run_id"]), "task.skipped", {"reason": "dry-run"}, task.task_id)
            return 0
        with ThreadPoolExecutor(max_workers=cap) as pool:
            active: dict[Future[int], tuple[str, set[str]]] = {}
            while pending or active:
                if cancel is not None and cancel.is_set():
                    for task_id in sorted(pending, key=lambda key: ords[key]):
                        self.store.set_task_status(task_id, "cancelled")
                        self.store.append_event(str(run["run_id"]), "task.cancelled", {"reason": "scheduler cancellation"}, task_id)
                    return 130
                for task_id in sorted(list(pending), key=lambda key: ords[key]):
                    if any(dep in failed or dep in blocked for dep in deps[task_id]):
                        pending.remove(task_id)
                        blocked.add(task_id)
                        self.store.set_task_status(task_id, "blocked")
                        self.store.append_event(str(run["run_id"]), "task.blocked", {"dependencies": deps[task_id]}, task_id)
                made_progress = False
                for task_id in sorted(list(pending), key=lambda key: ords[key]):
                    if len(active) >= cap or not all(dep in done for dep in deps[task_id]):
                        continue
                    paths = _predicted_files(by_id[task_id])
                    if not allow_overlap and paths and any(paths & active_paths for _, active_paths in active.values()):
                        continue
                    pending.remove(task_id)
                    future = pool.submit(
                        _thread_task, self.store.root, self.repo_path, run["run_id"], by_id[task_id], ords[task_id], runner, budget, cancel
                    )
                    active[future] = (task_id, paths)
                    self.store.append_event(str(run["run_id"]), "scheduler.task_started", {"ordinal": ords[task_id]}, task_id)
                    made_progress = True
                if not active:
                    if not pending:
                        break
                    for task_id in sorted(pending, key=lambda key: ords[key]):
                        self.store.set_task_status(task_id, "blocked")
                        self.store.append_event(str(run["run_id"]), "task.blocked", {"dependencies": deps[task_id]}, task_id)
                    return exit_code or 1
                finished, _ = wait(active, timeout=0.1 if made_progress else None, return_when=FIRST_COMPLETED)
                for future in sorted(finished, key=lambda item: ords[active[item][0]]):
                    task_id, _ = active.pop(future)
                    try:
                        code = future.result()
                    except Exception as exc:
                        code = 1
                        self.store.append_event(str(run["run_id"]), "task.failed", {"error": f"{type(exc).__name__}: {exc}"}, task_id)
                    if code == 0:
                        done.add(task_id)
                    else:
                        failed.add(task_id)
                        exit_code = code or 1
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
        route = explain_route(load_config(self.repo_path), goal)
        self.store.append_event(run_id, "route.selected", route)
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
            graph_context = task.metadata.get("graph_context")
            if isinstance(graph_context, dict):
                lines.append(graph_context_text(graph_context))
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
            included_summaries=[graph_context_text(task.metadata["graph_context"])]
            if isinstance(task.metadata.get("graph_context"), dict)
            else [],
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
                "run_id": run_id, "task_id": task.task_id, "title": task.title, "status": status, "agent": agent,
                "result_artifact_id": result_artifact_id, "returncode": returncode, "next_steps": task.validation,
            },
        )

    def _summary(self, run_id: str) -> str:
        tasks = self.store.list_tasks(run_id)
        done = sum(1 for task in tasks if task["status"] == "completed")
        failed = sum(1 for task in tasks if task["status"] == "failed")
        blocked = sum(1 for task in tasks if task["status"] == "blocked")
        cancelled = sum(1 for task in tasks if task["status"] == "cancelled")
        return f"{done}/{len(tasks)} tasks completed, {failed} failed, {blocked} blocked, {cancelled} cancelled"

    def _scheduler_ledger(self, run_id: str, started: float, cap: int) -> None:
        tasks = self.store.list_tasks(run_id)
        status_counts = {
            status: sum(1 for task in tasks if task["status"] == status) for status in ("completed", "failed", "blocked", "cancelled")
        }
        budget = self.store.get_run(run_id).get("budget")
        payload = {
            "schema_version": "poor-cli-scheduler-ledger-v1",
            "planned_tasks": len(tasks),
            "max_parallel": cap,
            "wall_seconds": round(time.monotonic() - started, 3),
            "cache_hits": 0,
            "budget": budget if isinstance(budget, dict) else {},
            **status_counts,
        }
        self.store.put_artifact(run_id=run_id, kind="scheduler.ledger", data=payload)
        self.store.append_event(run_id, "scheduler.completed", payload)


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


def _route_config(config: dict[str, Any], role: str) -> dict[str, Any]:
    routes = config.get("routes")
    route = routes.get(role) if isinstance(routes, dict) else None
    return dict(route) if isinstance(route, dict) else {}


def _cap(budget: Budget) -> int:
    if environ.get("POOR_CLI_FORCE_SYNC_AGENTS") == "1":
        return 1
    cap = max(1, budget.max_parallel_agents)
    raw = environ.get("POOR_CLI_MAX_PARALLEL_AGENTS")
    if raw:
        try:
            cap = min(cap, max(1, int(raw)))
        except ValueError:
            pass
    return cap


def _deps(tasks: list[TaskSpec]) -> dict[str, list[str]]:
    titles = {task.title: task.task_id for task in tasks}
    ids = {task.task_id for task in tasks}
    return {task.task_id: [dep if dep in ids else titles.get(dep, dep) for dep in task.dependencies] for task in tasks}


def _predicted_files(task: TaskSpec) -> set[str]:
    raw = task.metadata.get("expected_files") or task.metadata.get("files") or task.metadata.get("changed_files") or []
    return {str(item) for item in raw if str(item).strip()} if isinstance(raw, list) else set()


def _thread_task(root: Path, repo: Path, run_id: str, task: TaskSpec, ordinal: int, runner: AgentRunner, budget: Budget,
                 cancel: Any | None) -> int:
    store = RunStore(root)
    try:
        return Orchestrator(store, repo).execute_one(str(run_id), task, ordinal, runner, budget, repo, cancel)
    finally:
        store.close()
