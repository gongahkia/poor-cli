from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .agents import AgentRunner, detect_agents
from .artifacts import run_artifact_dir
from .models import Budget, TaskSpec, to_jsonable
from .orchestrator import Orchestrator
from .store import RunStore


def run_swarm(store: RunStore, goal: str, budget: Budget, *, graph_mode: bool = False, selected_agents: set[str] | None = None,
              allow_dirty: bool = False, allow_overlap: bool = False, failure_policy: str = "fail-fast",
              cancel: Any | None = None) -> dict[str, Any]:
    orch = Orchestrator(store)
    run_id, plan = orch.plan(goal, budget, graph_mode=graph_mode)
    return run_swarm_plan(
        store, run_id, plan.tasks, budget, selected_agents=selected_agents, allow_dirty=allow_dirty, allow_overlap=allow_overlap,
        failure_policy=failure_policy, cancel=cancel
    )


def run_swarm_plan(store: RunStore, run_id: str, tasks: list[TaskSpec], budget: Budget, *, selected_agents: set[str] | None = None,
                   allow_dirty: bool = False, allow_overlap: bool = False, failure_policy: str = "fail-fast",
                   cancel: Any | None = None) -> dict[str, Any]:
    repo = Path(store.get_run(run_id)["repo_path"])
    dirty = _git(repo, ["status", "--porcelain=v1", "--untracked-files=all"]).splitlines()
    if dirty and not allow_dirty:
        store.set_run_status(run_id, "failed", "dirty main worktree")
        store.append_event(run_id, "swarm.refused", {"reason": "dirty main worktree", "dirty": dirty})
        raise RuntimeError("swarm refused: dirty main worktree; rerun with --allow-dirty")
    agents = detect_agents()
    if selected_agents:
        agents = [agent for agent in agents if agent.name in selected_agents or agent.agent_id in selected_agents]
    runner = AgentRunner(agents)
    root = store.root / "runs" / run_id / "worktrees"
    root.mkdir(parents=True, exist_ok=True)
    store.set_run_status(run_id, "running")
    store.append_event(run_id, "swarm.started", {"workers": len(tasks), "allow_dirty": allow_dirty, "failure_policy": failure_policy})
    workers: list[dict[str, Any]] = []
    exit_code = 0
    for ordinal, task in enumerate(tasks, 1):
        if cancel is not None and cancel.is_set():
            store.append_event(run_id, "swarm.cancelled", {"completed_workers": len(workers)})
            exit_code = 130
            break
        path = root / _name(run_id, ordinal, task)
        _git(repo, ["worktree", "add", "--detach", str(path), "HEAD"], check=True)
        meta = {
            "task_id": task.task_id, "ordinal": ordinal, "path": str(path), "route": task.metadata.get("route_config") or {},
            "dirty_baseline": dirty
        }
        store.put_artifact(run_id=run_id, task_id=task.task_id, kind="swarm.worker", data=meta)
        store.append_event(run_id, "swarm.worker.created", meta, task.task_id)
        local = Orchestrator(store, path)
        code = local.execute_one(run_id, task, ordinal, runner, budget, path, cancel)
        files = _changed(path)
        patch = _git(path, ["diff", "--no-ext-diff", "--binary", "--"])
        workers.append({**meta, "returncode": code, "changed_files": files, "patch": patch})
        if code and failure_policy == "fail-fast":
            exit_code = code
            break
        exit_code = exit_code or code
    conflict_ids = {c["task_id"] for c in conflicts} if (conflicts := _conflicts(workers, allow_overlap)) else set()
    plan_payload = {
        "schema_version": "poor-cli-swarm-merge-v1",
        "policy": "collect-only",
        "workers": [{k: v for k, v in row.items() if k != "patch"} for row in workers],
        "conflicts": conflicts,
        "ordered_patches": [row["task_id"] for row in workers if row["returncode"] == 0 and row["task_id"] not in conflict_ids],
    }
    _write_artifact(store, run_id, "merge/MERGE_PLAN.json", plan_payload)
    store.put_artifact(run_id=run_id, kind="swarm.merge_plan", data=plan_payload)
    store.append_event(run_id, "swarm.merge_planned", {"conflicts": len(conflicts), "policy": "collect-only"})
    status = "failed" if exit_code or conflicts else "completed"
    store.set_run_status(run_id, status, f"{len(workers)}/{len(tasks)} swarm workers finished, {len(conflicts)} conflicts")
    store.append_event(run_id, f"run.{status}", {"summary": store.get_run(run_id)["final_summary"] or ""})
    return {"run_id": run_id, "workers": len(workers), "conflicts": conflicts, "exit_code": exit_code or (1 if conflicts else 0)}


def cleanup_swarm(store: RunStore, run_id: str) -> list[str]:
    run = store.get_run(run_id)
    repo = Path(str(run["repo_path"]))
    removed = []
    for artifact in store.list_artifacts(run_id, "swarm.worker"):
        data = json.loads(store.artifact_payload(artifact["artifact_id"]))
        path = Path(str(data["path"]))
        if path.exists():
            result = subprocess.run(
                ["git", "worktree", "remove", "--force", str(path)], cwd=repo, text=True, capture_output=True, check=False
            )
            if result.returncode != 0:
                shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
    subprocess.run(["git", "worktree", "prune"], cwd=repo, text=True, capture_output=True, check=False)
    store.append_event(run_id, "swarm.cleanup", {"removed": removed})
    return removed


def _name(run_id: str, ordinal: int, task: TaskSpec) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", task.title.lower()).strip("-")[:40] or "task"
    role = str((task.metadata.get("route_policy") or {}).get("policy") or task.task_type)
    return f"{run_id}-worker-{ordinal:03d}-{role}-{slug}"


def _changed(path: Path) -> list[str]:
    changed = _git(path, ["diff", "--name-only", "--"]).splitlines()
    untracked = _git(path, ["ls-files", "--others", "--exclude-standard"]).splitlines()
    return sorted(set(changed + untracked))


def _conflicts(workers: list[dict[str, Any]], allow_overlap: bool) -> list[dict[str, Any]]:
    seen: dict[str, str] = {}
    conflicts = []
    for row in workers:
        for file in sorted(str(item) for item in row["changed_files"]):
            if file in seen and not allow_overlap:
                conflicts.append({"task_id": row["task_id"], "file": file, "conflicts_with": seen[file], "resolution": "review-task"})
            seen.setdefault(file, row["task_id"])
    return conflicts


def _write_artifact(store: RunStore, run_id: str, rel: str, data: dict[str, Any]) -> None:
    path = run_artifact_dir(store, run_id) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(data), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(repo: Path, args: list[str], *, check: bool = False) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout
