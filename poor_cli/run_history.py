"""Persistent run history shared by manual executions, tasks, and automations."""

from __future__ import annotations

import json
import sqlite3
import textwrap
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_error(error_message: str) -> str:
    text = str(error_message or "").strip().lower()
    if not text:
        return ""
    if "api key" in text or "configuration" in text or "config" in text:
        return "configuration_failure"
    if "permission" in text or "policy" in text:
        return "policy_denial"
    if "sandbox" in text or "not allowed" in text or "blocked" in text:
        return "sandbox_denial"
    if "cancel" in text:
        return "user_cancel"
    if "timeout" in text or "connection" in text or "network" in text or "unreachable" in text:
        return "connectivity_failure"
    if "provider" in text or "api" in text or "fallback" in text:
        return "provider_failure"
    return "tool_failure"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    source_kind: str
    source_id: str
    status: str
    started_at: str
    finished_at: Optional[str]
    error_class: str
    artifact_dir: str
    checkpoint_id: Optional[str]
    provider_summary_json: str
    cost_summary_json: str
    retry_of_run_id: Optional[str]
    replay_of_run_id: Optional[str]
    summary: str
    metadata_json: str

    @property
    def provider_summary(self) -> Dict[str, Any]:
        return _load_json_object(self.provider_summary_json)

    @property
    def cost_summary(self) -> Dict[str, Any]:
        return _load_json_object(self.cost_summary_json)

    @property
    def metadata(self) -> Dict[str, Any]:
        return _load_json_object(self.metadata_json)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runId": self.run_id,
            "sourceKind": self.source_kind,
            "sourceId": self.source_id,
            "status": self.status,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "errorClass": self.error_class,
            "artifactDir": self.artifact_dir,
            "checkpointId": self.checkpoint_id,
            "providerSummary": self.provider_summary,
            "costSummary": self.cost_summary,
            "retryOfRunId": self.retry_of_run_id,
            "replayOfRunId": self.replay_of_run_id,
            "summary": self.summary,
            "metadata": self.metadata,
        }


class RunHistoryManager:
    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.base_dir = self.repo_root / ".poor-cli"
        self.db_path = self.base_dir / "runs.db"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    source_kind TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error_class TEXT NOT NULL DEFAULT '',
                    artifact_dir TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT,
                    provider_summary_json TEXT NOT NULL DEFAULT '{}',
                    cost_summary_json TEXT NOT NULL DEFAULT '{}',
                    retry_of_run_id TEXT,
                    replay_of_run_id TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def start_run(
        self,
        *,
        source_kind: str,
        source_id: str,
        artifact_dir: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        retry_of_run_id: Optional[str] = None,
        replay_of_run_id: Optional[str] = None,
    ) -> RunRecord:
        run = RunRecord(
            run_id=uuid.uuid4().hex[:12],
            source_kind=str(source_kind or "").strip() or "session",
            source_id=str(source_id or "").strip() or "unknown",
            status="running",
            started_at=_utc_now(),
            finished_at=None,
            error_class="",
            artifact_dir=str(artifact_dir or ""),
            checkpoint_id=None,
            provider_summary_json="{}",
            cost_summary_json="{}",
            retry_of_run_id=retry_of_run_id,
            replay_of_run_id=replay_of_run_id,
            summary="",
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, source_kind, source_id, status, started_at, finished_at,
                    error_class, artifact_dir, checkpoint_id, provider_summary_json,
                    cost_summary_json, retry_of_run_id, replay_of_run_id, summary, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.source_kind,
                    run.source_id,
                    run.status,
                    run.started_at,
                    run.finished_at,
                    run.error_class,
                    run.artifact_dir,
                    run.checkpoint_id,
                    run.provider_summary_json,
                    run.cost_summary_json,
                    run.retry_of_run_id,
                    run.replay_of_run_id,
                    run.summary,
                    run.metadata_json,
                ),
            )
        return run

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        error_class: str = "",
        artifact_dir: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        provider_summary: Optional[Dict[str, Any]] = None,
        cost_summary: Optional[Dict[str, Any]] = None,
        summary: str = "",
        metadata_updates: Optional[Dict[str, Any]] = None,
    ) -> RunRecord:
        record = self.require_run(run_id)
        metadata = dict(record.metadata)
        if metadata_updates:
            metadata.update(metadata_updates)
        updates = {
            "status": str(status or "").strip() or record.status,
            "finished_at": _utc_now(),
            "error_class": str(error_class or "").strip(),
            "artifact_dir": str(artifact_dir if artifact_dir is not None else record.artifact_dir),
            "checkpoint_id": checkpoint_id,
            "provider_summary_json": json.dumps(provider_summary or {}, ensure_ascii=False),
            "cost_summary_json": json.dumps(cost_summary or {}, ensure_ascii=False),
            "summary": textwrap.shorten(str(summary or "").strip(), width=180, placeholder="..."),
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        }
        assignments = ", ".join(f"{column} = ?" for column in updates)
        params = list(updates.values()) + [run_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {assignments} WHERE run_id = ?", params)
        return self.require_run(run_id)

    def list_runs(
        self,
        *,
        source_kind: Optional[str] = None,
        source_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[RunRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        if source_kind:
            clauses.append("source_kind = ?")
            params.append(str(source_kind))
        if source_id:
            clauses.append("source_id = ?")
            params.append(str(source_id))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM runs
                {where_sql}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (str(run_id).strip(),),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def require_run(self, run_id: str) -> RunRecord:
        record = self.get_run(run_id)
        if record is None:
            raise FileNotFoundError(f"Unknown run: {run_id}")
        return record

    def last_successful_run(
        self,
        *,
        source_kind: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Optional[RunRecord]:
        clauses = ["status = 'completed'"]
        params: List[Any] = []
        if source_kind:
            clauses.append("source_kind = ?")
            params.append(str(source_kind))
        if source_id:
            clauses.append("source_id = ?")
            params.append(str(source_id))
        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM runs
                WHERE {where_sql}
                ORDER BY finished_at DESC, started_at DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error_class=row["error_class"],
            artifact_dir=row["artifact_dir"],
            checkpoint_id=row["checkpoint_id"],
            provider_summary_json=row["provider_summary_json"],
            cost_summary_json=row["cost_summary_json"],
            retry_of_run_id=row["retry_of_run_id"],
            replay_of_run_id=row["replay_of_run_id"],
            summary=row["summary"],
            metadata_json=row["metadata_json"],
        )


def _load_json_object(raw_value: str) -> Dict[str, Any]:
    try:
        loaded = json.loads(raw_value or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}
