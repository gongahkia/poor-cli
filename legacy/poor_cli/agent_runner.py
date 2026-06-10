"""
Background agent runner for poor-cli.

Runs autonomous AI agents as background processes that can be:
- Started from CLI: poor-cli agent start --prompt "..."
- Triggered by GitHub events (issue assignment, PR comments)
- Scheduled via automations
- Managed via RPC from CLI

Each agent gets its own artifact directory with logs, events, and results.
Optionally creates a git worktree for isolation.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

from .exceptions import setup_logger, ValidationError
from .lifecycle_events import build_lifecycle_event
from .run_history import classify_error

logger = setup_logger(__name__)

AGENT_DB_NAME = "agents.db"
MAX_RUNTIME_SECONDS = 3600 # 1 hour default
MAX_COST_USD = 5.0 # default cost cap


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:48] or "agent"


@dataclass(frozen=True)
class AgentRecord:
    """Persistent record for a background agent run."""
    agent_id: str
    prompt: str
    status: str # queued | running | completed | failed | cancelled
    sandbox_preset: str
    source: str # cli | github | automation | rpc
    created_at: str
    updated_at: str
    repo_root: str
    worktree_path: str
    branch_name: str
    artifact_dir: str
    log_path: str
    result_path: str
    events_path: str
    summary: str = ""
    worker_pid: Optional[int] = None
    error_message: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    max_runtime: int = MAX_RUNTIME_SECONDS
    max_cost_usd: float = MAX_COST_USD
    metadata_json: str = "{}"

    @property
    def metadata(self) -> Dict[str, Any]:
        try:
            return json.loads(self.metadata_json) or {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agentId": self.agent_id,
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
            "resultPath": self.result_path,
            "eventsPath": self.events_path,
            "summary": self.summary,
            "workerPid": self.worker_pid,
            "errorMessage": self.error_message,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "maxRuntime": self.max_runtime,
            "maxCostUsd": self.max_cost_usd,
            "metadata": self.metadata,
        }


class AgentManager:
    """Manages background agent lifecycle — creation, execution, monitoring."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.base_dir = self.repo_root / ".poor-cli"
        self.agents_dir = self.base_dir / "agents"
        self.db_path = self.agents_dir / AGENT_DB_NAME
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── database ─────────────────────────────────────────────────────────

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
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
                    result_path TEXT NOT NULL,
                    events_path TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    worker_pid INTEGER,
                    error_message TEXT NOT NULL DEFAULT '',
                    started_at TEXT,
                    finished_at TEXT,
                    max_runtime INTEGER NOT NULL DEFAULT 3600,
                    max_cost_usd REAL NOT NULL DEFAULT 5.0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
            """)

    def _row_to_record(self, row: sqlite3.Row) -> AgentRecord:
        return AgentRecord(**dict(row))

    def _update(self, agent_id: str, **kwargs: Any) -> None:
        sets = []
        params: List[Any] = []
        kwargs["updated_at"] = _utc_now()
        for key, val in kwargs.items():
            sets.append(f"{key} = ?")
            params.append(val)
        params.append(agent_id)
        sql = f"UPDATE agents SET {', '.join(sets)} WHERE agent_id = ?"
        with self._connect() as conn:
            conn.execute(sql, params)

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create_agent(
        self,
        *,
        prompt: str,
        sandbox_preset: str = "workspace-write",
        source: str = "cli",
        branch_name: str = "",
        use_worktree: bool = True,
        max_runtime: int = MAX_RUNTIME_SECONDS,
        max_cost_usd: float = MAX_COST_USD,
        metadata: Optional[Dict[str, Any]] = None,
        auto_start: bool = False,
    ) -> AgentRecord:
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        slug = _slugify(prompt[:60])
        artifact_dir = self.agents_dir / agent_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        now = _utc_now()

        if not branch_name:
            branch_name = f"poor-cli/agent/{agent_id}-{slug}"

        if use_worktree:
            worktree_path = str(self._create_worktree(agent_id, branch_name))
        else:
            worktree_path = str(self.repo_root)

        record = AgentRecord(
            agent_id=agent_id,
            prompt=prompt,
            status="queued",
            sandbox_preset=sandbox_preset,
            source=source,
            created_at=now,
            updated_at=now,
            repo_root=str(self.repo_root),
            worktree_path=worktree_path,
            branch_name=branch_name,
            artifact_dir=str(artifact_dir),
            log_path=str(artifact_dir / "agent.log"),
            result_path=str(artifact_dir / "result.md"),
            events_path=str(artifact_dir / "events.jsonl"),
            max_runtime=max_runtime,
            max_cost_usd=max_cost_usd,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agents (
                    agent_id, prompt, status, sandbox_preset, source,
                    created_at, updated_at, repo_root, worktree_path,
                    branch_name, artifact_dir, log_path, result_path,
                    events_path, summary, worker_pid, error_message,
                    started_at, finished_at, max_runtime, max_cost_usd,
                    metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.agent_id, record.prompt, record.status,
                    record.sandbox_preset, record.source, record.created_at,
                    record.updated_at, record.repo_root, record.worktree_path,
                    record.branch_name, record.artifact_dir, record.log_path,
                    record.result_path, record.events_path, record.summary,
                    record.worker_pid, record.error_message, record.started_at,
                    record.finished_at, record.max_runtime, record.max_cost_usd,
                    record.metadata_json,
                ),
            )

        if auto_start:
            return self.start_agent(agent_id)
        return record

    def get_agent(self, agent_id: str) -> Optional[AgentRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            return None
        return self._reconcile_runtime(self._row_to_record(row))

    def list_agents(
        self,
        statuses: Optional[Sequence[str]] = None,
        limit: int = 50,
    ) -> List[AgentRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(min(max(1, limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM agents {where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._reconcile_runtime(self._row_to_record(r)) for r in rows]

    # ── lifecycle ────────────────────────────────────────────────────────

    def start_agent(self, agent_id: str) -> AgentRecord:
        """Launch agent as a background subprocess (local or cloud)."""
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValidationError(f"unknown agent: {agent_id}")
        if agent.status != "queued":
            return agent

        log_path = Path(agent.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        argv = [
            sys.executable, "-m", "poor_cli", "agent", "run",
            "--agent-id", agent.agent_id,
            "--repo-root", agent.repo_root,
        ]

        with log_path.open("ab") as log_handle:
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=agent.worktree_path,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except Exception as exc:
                self._update(agent_id, status="failed", finished_at=_utc_now(),
                             error_message=f"failed to start: {exc}")
                return self.get_agent(agent_id) or agent

        self._update(agent_id, status="running", started_at=_utc_now(),
                     worker_pid=proc.pid)
        logger.info("started agent %s (pid %d)", agent_id, proc.pid)
        return self.get_agent(agent_id) or agent

    def cancel_agent(self, agent_id: str) -> AgentRecord:
        """Cancel a running agent by sending SIGTERM."""
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValidationError(f"unknown agent: {agent_id}")
        if agent.status not in ("queued", "running"):
            return agent
        if agent.worker_pid:
            try:
                os.kill(agent.worker_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self._update(agent_id, status="cancelled", finished_at=_utc_now())
        self._record_terminal_metadata(agent_id, status="cancelled", reason_code="cancelled_by_user")
        return self.get_agent(agent_id) or agent

    def get_logs(self, agent_id: str, tail: int = 100) -> str:
        """Read the last N lines of agent logs."""
        agent = self.get_agent(agent_id)
        if not agent:
            return f"unknown agent: {agent_id}"
        log_path = Path(agent.log_path)
        if not log_path.exists():
            return "(no logs yet)"
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-tail:])

    def get_result(self, agent_id: str) -> str:
        """Read the agent's final result."""
        agent = self.get_agent(agent_id)
        if not agent:
            return f"unknown agent: {agent_id}"
        result_path = Path(agent.result_path)
        if not result_path.exists():
            return "(no result yet)"
        return result_path.read_text(encoding="utf-8", errors="replace")

    # ── worktree management ──────────────────────────────────────────────

    def _create_worktree(self, agent_id: str, branch_name: str) -> Path:
        """Create an isolated git worktree for this agent."""
        worktree_dir = self.base_dir / "worktrees" / agent_id
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(worktree_dir)],
                cwd=str(self.repo_root),
                capture_output=True, text=True, check=True,
            )
            logger.info("created worktree: %s (%s)", worktree_dir, branch_name)
        except subprocess.CalledProcessError as exc:
            logger.warning("worktree creation failed, using repo root: %s", exc.stderr.strip())
            return self.repo_root
        return worktree_dir

    def cleanup_worktree(self, agent_id: str) -> bool:
        """Remove a worktree if it has no uncommitted changes."""
        agent = self.get_agent(agent_id)
        if not agent:
            return False
        wt = Path(agent.worktree_path)
        if wt == self.repo_root or not wt.exists():
            return False
        # check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(wt), capture_output=True, text=True, check=False,
        )
        if result.stdout.strip():
            logger.info("worktree %s has changes, keeping", wt)
            return False
        try:
            subprocess.run(
                ["git", "worktree", "remove", str(wt)],
                cwd=str(self.repo_root),
                capture_output=True, text=True, check=True,
            )
            logger.info("removed worktree: %s", wt)
            return True
        except subprocess.CalledProcessError as exc:
            logger.warning("failed to remove worktree: %s", exc.stderr.strip())
            return False

    # ── runtime reconciliation ───────────────────────────────────────────

    def _reconcile_runtime(self, record: AgentRecord) -> AgentRecord:
        """Check if a 'running' agent is actually still running."""
        if record.status != "running" or not record.worker_pid:
            return record
        try:
            os.kill(record.worker_pid, 0)
        except ProcessLookupError:
            self._update(record.agent_id, status="failed",
                         finished_at=_utc_now(),
                         error_message="worker process exited unexpectedly")
            self._record_terminal_metadata(
                record.agent_id,
                status="failed",
                reason_code="worker_process_exited",
            )
            return self.get_agent(record.agent_id) or record
        return record

    def _record_terminal_metadata(
        self,
        agent_id: str,
        *,
        status: str,
        reason_code: str,
        run_id: str = "",
    ) -> None:
        record = self.get_agent(agent_id)
        if record is None:
            return
        metadata = dict(record.metadata)
        metadata["lastTerminalStatus"] = str(status)
        metadata["lastTerminalReasonCode"] = str(reason_code)
        metadata["lastTerminalAt"] = _utc_now()
        if run_id:
            metadata["lastRunId"] = str(run_id)
        self._update(agent_id, metadata_json=json.dumps(metadata, ensure_ascii=False))


# ── agent worker entry point ─────────────────────────────────────────────

async def run_agent_worker(agent_id: str, repo_root: str) -> None:
    """
    Execute an agent's prompt using PoorCLICore in the current process.

    This is called by the subprocess spawned by AgentManager.start_agent().
    """
    from .core import PoorCLICore

    mgr = AgentManager(Path(repo_root))
    agent = mgr.get_agent(agent_id)
    if not agent:
        print(f"error: unknown agent {agent_id}", file=sys.stderr)
        return

    result_path = Path(agent.result_path)
    events_path = Path(agent.events_path)

    core = PoorCLICore()

    def _append_event(payload: Dict[str, Any]) -> None:
        try:
            with events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    try:
        await core.initialize()
    except Exception as exc:
        mgr._update(agent_id, status="failed", finished_at=_utc_now(),
                     error_message=f"init failed: {exc}")
        mgr._record_terminal_metadata(
            agent_id,
            status="failed",
            reason_code="init_failed",
        )
        result_path.write_text(f"Agent initialization failed: {exc}", encoding="utf-8")
        _append_event(
            build_lifecycle_event(
                stream="agent",
                entity_id=agent_id,
                stage="finished",
                status="failed",
                reason_code="init_failed",
                details={"error": str(exc)},
            )
        )
        return

    # auto-approve all tools based on sandbox preset
    from .permission_engine import _as_async
    core.permission_callback = _as_async(_auto_approve_callback(agent.sandbox_preset))

    accumulated_text = ""
    done_reason = ""
    try:
        _append_event(
            build_lifecycle_event(
                stream="agent",
                entity_id=agent_id,
                stage="started",
                status="running",
                reason_code="worker_started",
                details={"sandboxPreset": agent.sandbox_preset},
            )
        )
        async for event in core.send_message_events(
            agent.prompt,
            request_id=f"agent-{agent.agent_id}",
            source_kind="agent",
            source_id=agent.agent_id,
            artifact_dir=agent.artifact_dir,
            run_metadata={
                "agentId": agent.agent_id,
                "agentSource": agent.source,
            },
        ):
            _append_event({"type": event.type, "data": event.data})
            if event.type == "text_chunk":
                accumulated_text += event.data.get("chunk", "")
            elif event.type == "done":
                done_reason = str(event.data.get("reason", "") or "")
                break
    except Exception as exc:
        run_id = core.get_last_run_id() or ""
        mgr._update(agent_id, status="failed", finished_at=_utc_now(),
                     error_message=str(exc))
        mgr._record_terminal_metadata(
            agent_id,
            status="failed",
            reason_code=classify_error(str(exc)) or "agent_failed",
            run_id=str(run_id),
        )
        result_path.write_text(f"Agent failed: {exc}\n\n{accumulated_text}", encoding="utf-8")
        _append_event(
            build_lifecycle_event(
                stream="agent",
                entity_id=agent_id,
                stage="finished",
                status="failed",
                reason_code=classify_error(str(exc)) or "agent_failed",
                run_id=str(run_id),
                details={"error": str(exc)},
            )
        )
        return

    # write result
    result_path.write_text(accumulated_text, encoding="utf-8")

    # auto-commit if there are changes
    summary = _auto_commit_changes(agent, accumulated_text)

    run_id = core.get_last_run_id() or ""
    mgr._update(agent_id, status="completed", finished_at=_utc_now(),
                summary=summary or accumulated_text[:200])
    mgr._record_terminal_metadata(
        agent_id,
        status="completed",
        reason_code=done_reason or "completed",
        run_id=str(run_id),
    )
    _append_event(
        build_lifecycle_event(
            stream="agent",
            entity_id=agent_id,
            stage="finished",
            status="completed",
            reason_code=done_reason or "completed",
            run_id=str(run_id),
            details={"summary": summary or accumulated_text[:200]},
        )
    )
    logger.info("agent %s completed", agent_id)


def _auto_approve_callback(sandbox_preset: str) -> Callable:
    """Create a permission callback that auto-approves based on preset."""
    from .sandbox import evaluate_tool_access
    async def callback(tool_name: str, tool_args: dict) -> dict:
        decision = evaluate_tool_access(tool_name, tool_args, sandbox_preset)
        return {"allowed": decision.get("allowed", False)}
    return callback


def _auto_commit_changes(agent: AgentRecord, response_text: str) -> str:
    """If worktree has changes, auto-commit them."""
    wt = Path(agent.worktree_path)
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(wt), capture_output=True, text=True, check=False,
    )
    if not result.stdout.strip():
        return "no changes"

    # stage all changes
    subprocess.run(["git", "add", "-A"], cwd=str(wt), check=False)

    # create commit
    summary = response_text.split("\n")[0][:70] if response_text else "agent changes"
    message = (
        f"feat(agent): {summary}\n\n"
        f"Agent: {agent.agent_id}\n"
        f"Prompt: {agent.prompt[:200]}\n\n"
        f"Co-Authored-By: poor-cli agent <noreply@poor-cli.dev>"
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(wt), capture_output=True, text=True, check=False,
    )
    return f"committed changes on branch {agent.branch_name}"


# ── GitHub event trigger ─────────────────────────────────────────────────

def create_agent_from_github_event(
    event_type: str,
    payload: Dict[str, Any],
    repo_root: Optional[Path] = None,
) -> Optional[AgentRecord]:
    """
    Create a background agent from a GitHub webhook event.

    Supported events:
    - issues.assigned: creates agent from issue body
    - issue_comment.created: creates agent from comment mentioning @poor-cli
    - pull_request_review_comment.created: creates agent from PR review comment
    """
    mgr = AgentManager(repo_root)

    if event_type == "issues" and payload.get("action") == "assigned":
        issue = payload.get("issue", {})
        title = issue.get("title", "")
        body = issue.get("body", "")
        number = issue.get("number", "")
        prompt = f"Fix GitHub issue #{number}: {title}\n\n{body}"
        return mgr.create_agent(
            prompt=prompt,
            source="github",
            sandbox_preset="workspace-write",
            metadata={"github_issue": number, "event": event_type},
            auto_start=True,
        )

    if event_type == "issue_comment" and payload.get("action") == "created":
        comment = payload.get("comment", {})
        body = comment.get("body", "")
        if "@poor-cli" not in body.lower():
            return None
        issue = payload.get("issue", {})
        number = issue.get("number", "")
        prompt = f"Respond to GitHub issue #{number} comment:\n\n{body}"
        return mgr.create_agent(
            prompt=prompt,
            source="github",
            sandbox_preset="workspace-write",
            metadata={"github_issue": number, "event": event_type},
            auto_start=True,
        )

    return None
