"""
Durable local task storage, isolated worktrees, and background execution.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .core import PoorCLICore
from .run_history import RunHistoryManager
from .sandbox import (
    evaluate_tool_access,
    normalize_preset,
    permission_mode_from_preset,
    raise_for_denial,
)

APPROVAL_REQUIRED_PRESETS = {"workspace-write", "full-access"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    safe = safe.strip("-")
    return safe[:48] or "task"


def _execution_mode_from_metadata(metadata: Dict[str, Any]) -> str:
    execution = metadata.get("execution")
    if not isinstance(execution, dict):
        return "worktree"
    mode = str(execution.get("executionMode", "") or "").strip().lower()
    return "local" if mode == "local" else "worktree"


def _current_git_branch(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "local"
    branch = result.stdout.strip()
    return branch or "local"


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    title: str
    prompt: str
    status: str
    sandbox_preset: str
    source: str
    created_at: str
    updated_at: str
    repo_root: str
    worktree_path: str
    branch_name: str
    artifact_dir: str
    log_path: str
    response_path: str
    events_path: str
    summary: str = ""
    worker_pid: Optional[int] = None
    error_message: str = ""
    approved_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    metadata_json: str = "{}"

    @property
    def metadata(self) -> Dict[str, Any]:
        try:
            loaded = json.loads(self.metadata_json)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def to_dict(self) -> Dict[str, Any]:
        metadata = self.metadata
        return {
            "taskId": self.task_id,
            "title": self.title,
            "prompt": self.prompt,
            "status": self.status,
            "sandboxPreset": self.sandbox_preset,
            "source": self.source,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "repoRoot": self.repo_root,
            "worktreePath": self.worktree_path,
            "branchName": self.branch_name,
            "artifactDir": self.artifact_dir,
            "logPath": self.log_path,
            "responsePath": self.response_path,
            "eventsPath": self.events_path,
            "summary": self.summary,
            "workerPid": self.worker_pid,
            "errorMessage": self.error_message,
            "approvedAt": self.approved_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "executionMode": _execution_mode_from_metadata(metadata),
            "metadata": metadata,
        }


class TaskManager:
    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.base_dir = self.repo_root / ".poor-cli"
        self.tasks_dir = self.base_dir / "tasks"
        self.worktrees_dir = self.base_dir / "worktrees"
        self.db_path = self.tasks_dir / "tasks.db"
        self.run_history = RunHistoryManager(self.repo_root)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sandbox_preset TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    repo_root TEXT NOT NULL,
                    worktree_path TEXT NOT NULL,
                    branch_name TEXT NOT NULL,
                    artifact_dir TEXT NOT NULL,
                    log_path TEXT NOT NULL,
                    response_path TEXT NOT NULL,
                    events_path TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    worker_pid INTEGER,
                    error_message TEXT NOT NULL DEFAULT '',
                    approved_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def create_task(
        self,
        *,
        title: str,
        prompt: str,
        sandbox_preset: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        auto_start: bool = False,
        requires_approval: bool = False,
        auto_approve: bool = False,
    ) -> TaskRecord:
        task_id = uuid.uuid4().hex[:12]
        slug = _slugify(title)
        artifact_dir = self.tasks_dir / task_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        created_at = _utc_now()
        preset = normalize_preset(sandbox_preset)
        metadata_payload = dict(metadata or {})
        execution_mode = _execution_mode_from_metadata(metadata_payload)
        if execution_mode == "local":
            worktree_path = self.repo_root
            branch_name = _current_git_branch(self.repo_root)
        else:
            branch_name = f"codex/poor-cli-task-{task_id}-{slug}"
            worktree_path = self._ensure_worktree(task_id, slug, branch_name)
        effective_auto_approve = bool(
            auto_approve or metadata_payload.get("autoApprove", False)
        )
        if effective_auto_approve or "autoApprove" in metadata_payload or auto_approve:
            metadata_payload["autoApprove"] = effective_auto_approve
        requires_manual_approval = bool(
            requires_approval or (preset in APPROVAL_REQUIRED_PRESETS and not effective_auto_approve)
        )
        record = TaskRecord(
            task_id=task_id,
            title=title.strip() or "Task",
            prompt=prompt,
            status="awaiting_approval" if requires_manual_approval else "queued",
            sandbox_preset=preset,
            source=source,
            created_at=created_at,
            updated_at=created_at,
            repo_root=str(self.repo_root),
            worktree_path=str(worktree_path),
            branch_name=branch_name,
            artifact_dir=str(artifact_dir),
            log_path=str(artifact_dir / "worker.log"),
            response_path=str(artifact_dir / "response.md"),
            events_path=str(artifact_dir / "events.jsonl"),
            approved_at=created_at if effective_auto_approve else None,
            metadata_json=json.dumps(metadata_payload, ensure_ascii=False),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, title, prompt, status, sandbox_preset, source,
                    created_at, updated_at, repo_root, worktree_path, branch_name,
                    artifact_dir, log_path, response_path, events_path, summary,
                    worker_pid, error_message, approved_at, started_at, finished_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.task_id,
                    record.title,
                    record.prompt,
                    record.status,
                    record.sandbox_preset,
                    record.source,
                    record.created_at,
                    record.updated_at,
                    record.repo_root,
                    record.worktree_path,
                    record.branch_name,
                    record.artifact_dir,
                    record.log_path,
                    record.response_path,
                    record.events_path,
                    record.summary,
                    record.worker_pid,
                    record.error_message,
                    record.approved_at,
                    record.started_at,
                    record.finished_at,
                    record.metadata_json,
                ),
            )
        if auto_start and record.status == "queued":
            return self.start_task_process(record.task_id)
        return record

    def list_tasks(
        self,
        *,
        statuses: Optional[Sequence[str]] = None,
        limit: int = 50,
        inbox_only: bool = False,
    ) -> List[TaskRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(str(status) for status in statuses)
        if inbox_only:
            clauses.append("status != 'completed'")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM tasks
                {where_sql}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._reconcile_task_runtime(self._row_to_task(row)) for row in rows]

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (str(task_id).strip(),),
            ).fetchone()
        if row is None:
            return None
        return self._reconcile_task_runtime(self._row_to_task(row))

    def approve_task(self, task_id: str, *, auto_start: bool = True) -> TaskRecord:
        task = self._require_task(task_id)
        if task.status != "awaiting_approval":
            return task
        self._update_task(
            task.task_id,
            status="queued",
            approved_at=_utc_now(),
            error_message="",
        )
        if auto_start:
            return self.start_task_process(task.task_id)
        return self._require_task(task.task_id)

    def cancel_task(self, task_id: str) -> TaskRecord:
        task = self._require_task(task_id)
        if task.worker_pid:
            self._signal_task_process_group(task.worker_pid, signal.SIGTERM)
        self._update_task(
            task.task_id,
            status="cancelled",
            finished_at=_utc_now(),
            error_message="cancelled by user",
            worker_pid=None,
        )
        return self._require_task(task.task_id)

    def retry_task(self, task_id: str, *, auto_start: Optional[bool] = None) -> TaskRecord:
        task = self._require_task(task_id)
        metadata = dict(task.metadata)
        last_run = self.run_history.list_runs(
            source_kind="task",
            source_id=task.task_id,
            limit=1,
        )
        metadata["retryOfTaskId"] = task.task_id
        metadata.pop("replayOfRunId", None)
        if metadata.get("lastRunId"):
            metadata["retryOfRunId"] = str(metadata["lastRunId"])
        elif last_run:
            metadata["retryOfRunId"] = last_run[0].run_id

        effective_auto_approve = bool(metadata.get("autoApprove", False))
        requires_approval = bool(
            task.sandbox_preset in APPROVAL_REQUIRED_PRESETS and not effective_auto_approve
        )
        effective_auto_start = (
            not requires_approval if auto_start is None else bool(auto_start)
        )
        return self.create_task(
            title=f"{task.title} (retry)",
            prompt=task.prompt,
            sandbox_preset=task.sandbox_preset,
            source=task.source,
            metadata=metadata,
            auto_start=effective_auto_start and not requires_approval,
            requires_approval=requires_approval,
            auto_approve=effective_auto_approve,
        )

    def replay_task(self, task_id: str, *, auto_start: Optional[bool] = None) -> TaskRecord:
        task = self._require_task(task_id)
        metadata = dict(task.metadata)
        replay_run = self.run_history.last_successful_run(
            source_kind="task",
            source_id=task.task_id,
        )
        if replay_run is None:
            recent = self.run_history.list_runs(
                source_kind="task",
                source_id=task.task_id,
                limit=1,
            )
            replay_run = recent[0] if recent else None
        metadata["replayOfTaskId"] = task.task_id
        metadata.pop("retryOfRunId", None)
        if replay_run is not None:
            metadata["replayOfRunId"] = replay_run.run_id

        effective_auto_approve = bool(metadata.get("autoApprove", False))
        requires_approval = bool(
            task.sandbox_preset in APPROVAL_REQUIRED_PRESETS and not effective_auto_approve
        )
        effective_auto_start = (
            not requires_approval if auto_start is None else bool(auto_start)
        )
        return self.create_task(
            title=f"{task.title} (replay)",
            prompt=task.prompt,
            sandbox_preset=task.sandbox_preset,
            source=task.source,
            metadata=metadata,
            auto_start=effective_auto_start and not requires_approval,
            requires_approval=requires_approval,
            auto_approve=effective_auto_approve,
        )

    def task_runs(self, task_id: str, *, limit: int = 25) -> List[Dict[str, Any]]:
        return [
            record.to_dict()
            for record in self.run_history.list_runs(
                source_kind="task",
                source_id=str(task_id).strip(),
                limit=limit,
            )
        ]

    def attach_run(self, task_id: str, run_id: str) -> TaskRecord:
        task = self._require_task(task_id)
        metadata = dict(task.metadata)
        metadata["lastRunId"] = str(run_id).strip()
        self._update_task(
            task_id,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        updated = self._require_task(task_id)
        self._update_linked_automation_state(
            updated,
            lastRunId=str(run_id).strip(),
        )
        return updated

    def start_task_process(self, task_id: str) -> TaskRecord:
        task = self._require_task(task_id)
        if task.status not in {"queued"}:
            return task
        if (
            task.sandbox_preset in APPROVAL_REQUIRED_PRESETS
            and task.approved_at is None
            and not bool(task.metadata.get("autoApprove", False))
        ):
            self._update_task(task.task_id, status="awaiting_approval")
            return self._require_task(task.task_id)

        worker_log_path = Path(task.log_path)
        worker_log_path.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            sys.executable,
            "-m",
            "poor_cli",
            "task",
            "run",
            "--task-id",
            task.task_id,
            "--repo-root",
            task.repo_root,
        ]
        execution = task.metadata.get("execution", {})
        if isinstance(execution, dict):
            config_path = str(execution.get("configPath", "")).strip()
            if config_path:
                argv.extend(["--config", config_path])
        with worker_log_path.open("ab") as handle:
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=task.repo_root,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except Exception as error:
                self._update_task(
                    task.task_id,
                    status="failed",
                    finished_at=_utc_now(),
                    worker_pid=None,
                    error_message=f"worker failed to start: {error}",
                )
                return self._require_task(task.task_id)
        self._update_task(
            task.task_id,
            worker_pid=process.pid,
            status="running",
            started_at=_utc_now(),
        )
        return self._require_task(task.task_id)

    def mark_running(self, task_id: str, *, worker_pid: Optional[int] = None) -> TaskRecord:
        self._update_task(
            task_id,
            status="running",
            started_at=_utc_now(),
            worker_pid=worker_pid,
            error_message="",
        )
        task = self._require_task(task_id)
        self._update_linked_automation_state(
            task,
            lastRunStatus="running",
            lastRunSummary="",
            lastRunError="",
        )
        return task

    def mark_completed(self, task_id: str, *, summary: str = "") -> TaskRecord:
        self._update_task(
            task_id,
            status="completed",
            finished_at=_utc_now(),
            summary=summary.strip(),
            worker_pid=None,
            error_message="",
        )
        task = self._require_task(task_id)
        self._update_linked_automation_state(
            task,
            lastRunStatus="completed",
            lastRunSummary=summary.strip(),
            lastRunError="",
        )
        return task

    def mark_failed(self, task_id: str, *, error_message: str) -> TaskRecord:
        self._update_task(
            task_id,
            status="failed",
            finished_at=_utc_now(),
            error_message=error_message.strip(),
            worker_pid=None,
        )
        task = self._require_task(task_id)
        self._update_linked_automation_state(
            task,
            lastRunStatus="failed",
            lastRunSummary="",
            lastRunError=error_message.strip(),
        )
        return task

    def _update_linked_automation_state(self, task: TaskRecord, **updates: Any) -> None:
        automation_id = str(task.metadata.get("automationId", "") or "").strip()
        if not automation_id:
            return

        db_path = self.tasks_dir / "automations.db"
        if not db_path.exists():
            return

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT metadata_json FROM automations WHERE automation_id = ?",
                (automation_id,),
            ).fetchone()
            if row is None:
                return
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            for key, value in updates.items():
                if value is None:
                    continue
                metadata[key] = value
            conn.execute(
                """
                UPDATE automations
                SET metadata_json = ?, updated_at = ?
                WHERE automation_id = ?
                """,
                (json.dumps(metadata, ensure_ascii=False), _utc_now(), automation_id),
            )

    def _update_task(self, task_id: str, **updates: Any) -> None:
        if not updates:
            return
        updates["updated_at"] = _utc_now()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        params = list(updates.values()) + [task_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE tasks SET {assignments} WHERE task_id = ?",
                params,
            )

    def _require_task(self, task_id: str) -> TaskRecord:
        task = self.get_task(task_id)
        if task is None:
            raise FileNotFoundError(f"Unknown task: {task_id}")
        return task

    @staticmethod
    def _pid_is_running(pid: Optional[int]) -> bool:
        if pid is None or int(pid) <= 0:
            return False
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _signal_task_process_group(pid: Optional[int], sig: int) -> bool:
        if pid is None or int(pid) <= 0:
            return False

        target_pid = int(pid)
        if hasattr(os, "killpg"):
            try:
                os.killpg(target_pid, sig)
                return True
            except PermissionError:
                return True
            except OSError:
                pass

        try:
            os.kill(target_pid, sig)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _reconcile_task_runtime(self, task: TaskRecord) -> TaskRecord:
        if task.status != "running":
            return task
        if task.worker_pid is None or self._pid_is_running(task.worker_pid):
            return task

        self._update_task(
            task.task_id,
            status="failed",
            finished_at=_utc_now(),
            worker_pid=None,
            error_message="worker process exited unexpectedly",
        )
        refreshed = self._require_task(task.task_id)
        self._update_linked_automation_state(
            refreshed,
            lastRunStatus="failed",
            lastRunSummary="",
            lastRunError="worker process exited unexpectedly",
        )
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task.task_id,),
            ).fetchone()
        return self._row_to_task(row) if row is not None else task

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            title=row["title"],
            prompt=row["prompt"],
            status=row["status"],
            sandbox_preset=row["sandbox_preset"],
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            repo_root=row["repo_root"],
            worktree_path=row["worktree_path"],
            branch_name=row["branch_name"],
            artifact_dir=row["artifact_dir"],
            log_path=row["log_path"],
            response_path=row["response_path"],
            events_path=row["events_path"],
            summary=row["summary"],
            worker_pid=row["worker_pid"],
            error_message=row["error_message"],
            approved_at=row["approved_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            metadata_json=row["metadata_json"],
        )

    def _ensure_worktree(self, task_id: str, slug: str, branch_name: str) -> Path:
        worktree_path = self.worktrees_dir / f"{task_id}-{slug}"
        if worktree_path.exists():
            return worktree_path

        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if self._is_git_repo():
            result = subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "-b",
                    branch_name,
                    str(worktree_path),
                    "HEAD",
                ],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return worktree_path

        worktree_path.mkdir(parents=True, exist_ok=True)
        return self.repo_root

    def _is_git_repo(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(self.repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0


async def run_task_worker(
    *,
    repo_root: Path,
    task_id: str,
    config_path: Optional[Path] = None,
) -> int:
    manager = TaskManager(repo_root)
    task = manager.get_task(task_id)
    if task is None:
        raise FileNotFoundError(f"Unknown task: {task_id}")
    if task.status == "cancelled":
        return 0

    output_dir = Path(task.artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manager.mark_running(task.task_id, worker_pid=os.getpid())

    response_chunks: List[str] = []
    original_cwd = Path.cwd()
    target_cwd = Path(task.worktree_path) if task.worktree_path else repo_root
    execution = task.metadata.get("execution", {}) if isinstance(task.metadata, dict) else {}
    if not isinstance(execution, dict):
        execution = {}
    execution_mode = _execution_mode_from_metadata(task.metadata)
    reasoning_effort = str(execution.get("reasoningEffort", "") or "").strip().lower()

    def _permission_callback(
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        assert core.tool_registry is not None
        mutation_paths = list(preview.get("paths") or []) if isinstance(preview, dict) else []
        if not mutation_paths:
            mutation_paths = core.tool_registry.inspect_mutation_targets(tool_name, tool_args)
        capabilities = core.tool_registry.get_tool_capabilities(tool_name)
        decision = evaluate_tool_access(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_capabilities=capabilities,
            permission_mode="prompt",
            sandbox_preset=task.sandbox_preset,
            trusted_roots=[target_cwd.resolve()],
            mutation_paths=mutation_paths,
            enforce_trusted_workspace=bool(
                getattr(getattr(core, "config", None), "security", None) is None
                or getattr(core.config.security, "enforce_trusted_workspace", True)
            ),
            safe_process_commands=getattr(
                getattr(getattr(core, "config", None), "security", None),
                "safe_commands",
                None,
            ),
        )
        raise_for_denial(
            tool_name,
            permission_mode_from_preset(task.sandbox_preset),
            decision,
        )
        return {"allowed": True, "approvedPaths": [], "approvedChunks": []}

    core = PoorCLICore(config_path=config_path)
    core.permission_callback = _async_wrap_permission_callback(_permission_callback)
    initialized = False

    try:
        os.chdir(target_cwd)
        await core.initialize(
            provider_name=str(execution.get("provider", "")).strip() or None,
            model_name=str(execution.get("model", "")).strip() or None,
        )
        initialized = True
        routing_mode = str(execution.get("routingMode", "")).strip()
        if routing_mode:
            core.set_routing_mode(routing_mode)
        context_files = [
            str(path)
            for path in execution.get("contextFiles", [])
            if isinstance(path, str) and str(path).strip()
        ]
        pinned_context_files = [
            str(path)
            for path in execution.get("pinnedContextFiles", [])
            if isinstance(path, str) and str(path).strip()
        ]
        raw_context_budget = execution.get("contextBudgetTokens")
        context_budget_tokens = int(raw_context_budget) if isinstance(raw_context_budget, int) else None
        run_metadata: Dict[str, Any] = {
            "taskId": task.task_id,
            "taskTitle": task.title,
            "taskSource": task.source,
            "executionMode": execution_mode,
        }
        if reasoning_effort:
            run_metadata["reasoningEffort"] = reasoning_effort
        for key in (
            "automationId",
            "automationName",
            "retryOfRunId",
            "replayOfRunId",
            "retryOfTaskId",
            "replayOfTaskId",
        ):
            value = task.metadata.get(key)
            if value:
                run_metadata[key] = value
        task_hook_payload = {
            "taskId": task.task_id,
            "title": task.title,
            "source": task.source,
            "sandboxPreset": task.sandbox_preset,
            "executionMode": execution_mode,
            "worktreePath": str(target_cwd),
        }
        await core._emit_policy_hooks("task_started", task_hook_payload)
        if task.metadata.get("automationId"):
            await core._emit_policy_hooks(
                "automation_started",
                {
                    **task_hook_payload,
                    "automationId": str(task.metadata.get("automationId", "")),
                    "automationName": str(task.metadata.get("automationName", "")),
                },
            )
        with Path(task.events_path).open("w", encoding="utf-8") as event_handle:
            async for event in core.send_message_events(
                task.prompt,
                context_files=context_files,
                pinned_context_files=pinned_context_files,
                context_budget_tokens=context_budget_tokens,
                request_id=f"task-{task.task_id}",
                source_kind="task",
                source_id=task.task_id,
                artifact_dir=task.artifact_dir,
                run_metadata=run_metadata,
            ):
                event_handle.write(
                    json.dumps(
                        {"type": event.type, "data": event.data},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                if event.type == "text_chunk":
                    chunk = str(event.data.get("chunk", ""))
                    if chunk:
                        response_chunks.append(chunk)
        run_id = core.get_last_run_id()
        if run_id:
            manager.attach_run(task.task_id, run_id)
        response_text = "".join(response_chunks).strip()
        Path(task.response_path).write_text(response_text, encoding="utf-8")
        completed_task = manager.mark_completed(
            task.task_id,
            summary=textwrap.shorten(response_text or "completed", width=180, placeholder="..."),
        )
        finish_payload = {
            **task_hook_payload,
            "status": "completed",
            "runId": str(run_id or ""),
            "summary": completed_task.summary,
        }
        await core._emit_policy_hooks("task_finished", finish_payload)
        if task.metadata.get("automationId"):
            await core._emit_policy_hooks(
                "automation_finished",
                {
                    **finish_payload,
                    "automationId": str(task.metadata.get("automationId", "")),
                    "automationName": str(task.metadata.get("automationName", "")),
                },
            )
        return 0
    except Exception as error:
        message = str(error)
        run_id = core.get_last_run_id()
        if run_id:
            manager.attach_run(task.task_id, run_id)
        Path(task.response_path).write_text(message, encoding="utf-8")
        manager.mark_failed(task.task_id, error_message=message)
        finish_payload = {
            "taskId": task.task_id,
            "title": task.title,
            "source": task.source,
            "sandboxPreset": task.sandbox_preset,
            "executionMode": execution_mode,
            "worktreePath": str(target_cwd),
            "status": "failed",
            "runId": str(run_id or ""),
            "error": message,
        }
        if initialized:
            await core._emit_policy_hooks("task_finished", finish_payload)
            if task.metadata.get("automationId"):
                await core._emit_policy_hooks(
                    "automation_finished",
                    {
                        **finish_payload,
                        "automationId": str(task.metadata.get("automationId", "")),
                        "automationName": str(task.metadata.get("automationName", "")),
                    },
                )
        return 1
    finally:
        os.chdir(original_cwd)
        if initialized:
            await core.shutdown()


def _async_wrap_permission_callback(callback):
    async def _wrapped(tool_name: str, tool_args: Dict[str, Any], preview: Optional[Dict[str, Any]] = None):
        return callback(tool_name, tool_args, preview)

    return _wrapped
