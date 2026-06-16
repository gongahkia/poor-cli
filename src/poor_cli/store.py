from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import AgentInfo, Artifact, Event, TaskSpec, make_id, to_jsonable, utc_now

RECORD_SCHEMA_VERSION = "poor-cli-record-v1"
LEGACY_RECORD_SCHEMA_VERSION = "poor-cli-record-v0"
SECRET_KEY_NAMES = {"api_key", "apikey", "token", "secret", "password", "bearer", "authorization", "x_api_key"}
SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b((?:anthropic|openai|moonshot|openrouter)_api_key\s*=\s*)\S+"),
    re.compile(r"(?i)\b((?:authorization|x-api-key)\s*[:=]\s*)(?:bearer\s+)?[^\s,;}]+"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
)


class StoreError(RuntimeError):
    pass


class CAS:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, data: bytes) -> tuple[str, Path]:
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(f".{make_id('tmp')}.tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return digest, path

    def read(self, digest: str) -> bytes:
        path = self.root / digest[:2] / digest
        if not path.exists():
            raise StoreError(f"missing CAS blob: {digest}")
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest:
            raise StoreError(f"CAS hash mismatch: expected {digest}, got {actual}")
        return data


class RunStore:
    def __init__(self, root: Path | None = None):
        self.root = root or (Path.cwd() / ".poor-cli" / "v6")
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs_root = self.root / "runs"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.cas = CAS(self.root / "cas")
        self.db_path = self.root / "runs.sqlite3"
        self.conn = sqlite3.connect(self.db_path, timeout=5)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.migrate()

    def close(self) -> None:
        self.conn.close()

    def migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              schema_version TEXT NOT NULL DEFAULT 'poor-cli-record-v1',
              created_at TEXT NOT NULL,
              repo_path TEXT NOT NULL,
              git_commit_start TEXT,
              user_goal TEXT NOT NULL,
              mode TEXT NOT NULL,
              budget_json TEXT NOT NULL,
              plan_id TEXT,
              status TEXT NOT NULL,
              final_summary TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
            CREATE INDEX IF NOT EXISTS idx_runs_goal ON runs(user_goal);
            CREATE TABLE IF NOT EXISTS tasks (
              task_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
              parent_task_id TEXT,
              title TEXT NOT NULL,
              objective TEXT NOT NULL,
              task_type TEXT NOT NULL,
              complexity TEXT NOT NULL,
              risk TEXT NOT NULL,
              required_context TEXT NOT NULL,
              dependencies_json TEXT NOT NULL,
              validation_json TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              assigned_agent TEXT,
              status TEXT NOT NULL,
              context_packet_id TEXT,
              result_artifact_id TEXT,
              ordinal INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_run_ordinal ON tasks(run_id, ordinal);
            CREATE TABLE IF NOT EXISTS events (
              event_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
              task_id TEXT,
              type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_run_created ON events(run_id, created_at, event_id);
            CREATE TABLE IF NOT EXISTS artifacts (
              artifact_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
              task_id TEXT,
              kind TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              size INTEGER NOT NULL,
              media_type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              path TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id, kind);
            CREATE INDEX IF NOT EXISTS idx_artifacts_sha ON artifacts(sha256);
            CREATE TABLE IF NOT EXISTS agents (
              agent_id TEXT NOT NULL,
              run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
              name TEXT NOT NULL,
              command TEXT NOT NULL,
              version TEXT NOT NULL,
              provider TEXT NOT NULL,
              capabilities_json TEXT NOT NULL,
              default_model TEXT,
              context_window_hint INTEGER,
              cost_profile_json TEXT NOT NULL,
              invocation_adapter TEXT NOT NULL,
              detected_at TEXT NOT NULL,
              PRIMARY KEY(agent_id, run_id)
            );
            """
        )
        self._ensure_column("runs", "schema_version", f"TEXT NOT NULL DEFAULT '{LEGACY_RECORD_SCHEMA_VERSION}'")
        self._ensure_column("tasks", "validation_json", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column("tasks", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
        self.conn.commit()

    def create_run(
        self,
        *,
        user_goal: str,
        repo_path: Path,
        git_commit_start: str | None,
        mode: str,
        budget: dict[str, Any],
    ) -> str:
        run_id = make_id("run")
        created_at = utc_now()
        self.conn.execute(
            """
            INSERT INTO runs(run_id, schema_version, created_at, repo_path, git_commit_start, user_goal, mode, budget_json, status)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, RECORD_SCHEMA_VERSION, created_at, str(repo_path), git_commit_start, user_goal, mode, self._json(budget), "created"),
        )
        self.conn.commit()
        self._run_dir(run_id).mkdir(parents=True, exist_ok=True)
        self._write_run_meta(run_id)
        return run_id

    def append_event(self, run_id: str, event_type: str, payload: dict[str, Any], task_id: str | None = None) -> Event:
        event = Event(make_id("evt"), run_id, task_id, event_type, utc_now(), payload)
        self.conn.execute(
            "INSERT INTO events(event_id, run_id, task_id, type, created_at, payload_json) VALUES(?, ?, ?, ?, ?, ?)",
            (event.event_id, run_id, task_id, event.type, event.created_at, self._json(event.payload)),
        )
        self.conn.commit()
        self._append_event_file(event)
        return event

    def put_artifact(
        self,
        *,
        run_id: str,
        kind: str,
        data: bytes | str | dict[str, Any] | list[Any],
        task_id: str | None = None,
        media_type: str = "application/json",
    ) -> Artifact:
        raw = self._artifact_bytes(data)
        digest, path = self.cas.write(raw)
        self._mirror_run_blob(run_id, digest, raw)
        artifact = Artifact(make_id("art"), run_id, task_id, kind, digest, len(raw), media_type, utc_now(), str(path))
        self.conn.execute(
            """
            INSERT INTO artifacts(artifact_id, run_id, task_id, kind, sha256, size, media_type, created_at, path)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                artifact.run_id,
                artifact.task_id,
                artifact.kind,
                artifact.sha256,
                artifact.size,
                artifact.media_type,
                artifact.created_at,
                artifact.path,
            ),
        )
        self.conn.commit()
        return artifact

    def insert_agents(self, run_id: str, agents: Iterable[AgentInfo]) -> None:
        now = utc_now()
        rows = []
        for agent in agents:
            rows.append(
                (
                    agent.agent_id,
                    run_id,
                    agent.name,
                    agent.command,
                    agent.version,
                    agent.provider,
                    self._json(agent.capabilities),
                    agent.default_model,
                    agent.context_window_hint,
                    self._json(agent.cost_profile),
                    agent.invocation_adapter,
                    now,
                )
            )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO agents(
              agent_id, run_id, name, command, version, provider, capabilities_json, default_model,
              context_window_hint, cost_profile_json, invocation_adapter, detected_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def insert_tasks(self, run_id: str, tasks: list[TaskSpec]) -> None:
        rows = []
        for index, task in enumerate(tasks):
            rows.append(
                (
                    task.task_id,
                    run_id,
                    None,
                    task.title,
                    task.objective,
                    task.task_type,
                    task.complexity,
                    task.risk,
                    task.required_context,
                    self._json(task.dependencies),
                    self._json(task.validation),
                    self._json(task.metadata),
                    task.suggested_agent,
                    "pending",
                    None,
                    None,
                    index,
                )
            )
        self.conn.executemany(
            """
            INSERT INTO tasks(
              task_id, run_id, parent_task_id, title, objective, task_type, complexity, risk, required_context,
              dependencies_json, validation_json, metadata_json, assigned_agent, status, context_packet_id, result_artifact_id, ordinal
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def set_run_status(self, run_id: str, status: str, final_summary: str | None = None) -> None:
        self.conn.execute(
            "UPDATE runs SET status = ?, final_summary = COALESCE(?, final_summary) WHERE run_id = ?",
            (status, final_summary, run_id),
        )
        self.conn.commit()
        self._write_run_meta(run_id)

    def set_run_plan(self, run_id: str, plan_id: str) -> None:
        self.conn.execute("UPDATE runs SET plan_id = ? WHERE run_id = ?", (plan_id, run_id))
        self.conn.commit()
        self._write_run_meta(run_id)

    def set_task_status(
        self,
        task_id: str,
        status: str,
        *,
        assigned_agent: str | None = None,
        context_packet_id: str | None = None,
        result_artifact_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE tasks
            SET status = ?,
                assigned_agent = COALESCE(?, assigned_agent),
                context_packet_id = COALESCE(?, context_packet_id),
                result_artifact_id = COALESCE(?, result_artifact_id)
            WHERE task_id = ?
            """,
            (status, assigned_agent, context_packet_id, result_artifact_id, task_id),
        )
        self.conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise StoreError(f"unknown run: {run_id}")
        return self._row(row)

    def list_runs(self, failed_only: bool = False, prompt_prefix: str | None = None) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        if failed_only:
            filters.append("status = ?")
            params.append("failed")
        if prompt_prefix:
            filters.append("user_goal LIKE ?")
            params.append(f"{prompt_prefix}%")
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        rows = self.conn.execute(f"SELECT * FROM runs{where} ORDER BY created_at DESC", params).fetchall()
        return [self._row(row) for row in rows]

    def list_tasks(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM tasks WHERE run_id = ? ORDER BY ordinal", (run_id,)).fetchall()
        return [self._row(row) for row in rows]

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM events WHERE run_id = ? ORDER BY rowid", (run_id,)).fetchall()
        return [self._row(row) for row in rows]

    def list_artifacts(self, run_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        if kind:
            rows = self.conn.execute("SELECT * FROM artifacts WHERE run_id = ? AND kind = ? ORDER BY created_at", (run_id, kind)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()
        return [self._row(row) for row in rows]

    def list_agents(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM agents WHERE run_id = ? ORDER BY name", (run_id,)).fetchall()
        return [self._row(row) for row in rows]

    def artifact_payload(self, artifact_id: str) -> bytes:
        row = self.conn.execute("SELECT sha256 FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
        if row is None:
            raise StoreError(f"unknown artifact: {artifact_id}")
        return self.cas.read(str(row["sha256"]))

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key, value in list(item.items()):
            if key.endswith("_json") and isinstance(value, str):
                item[key[:-5]] = json.loads(value)
                del item[key]
        return item

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        if column not in {str(row["name"]) for row in rows}:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _run_dir(self, run_id: str) -> Path:
        return self.runs_root / run_id

    def _write_run_meta(self, run_id: str) -> None:
        path = self._run_dir(run_id) / "meta.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(self._json(self.get_run(run_id)) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _append_event_file(self, event: Event) -> None:
        path = self._run_dir(event.run_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(self._json(event) + "\n")

    def _mirror_run_blob(self, run_id: str, digest: str, raw: bytes) -> None:
        path = self._run_dir(run_id) / "cas" / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(f".{make_id('tmp')}.tmp")
            tmp.write_bytes(raw)
            tmp.replace(path)

    def _artifact_bytes(self, data: bytes | str | dict[str, Any] | list[Any]) -> bytes:
        if isinstance(data, bytes):
            try:
                return _redact_text(data.decode()).encode()
            except UnicodeDecodeError:
                return data
        if isinstance(data, str):
            return _redact_text(data).encode()
        return self._json(data).encode()

    def _json(self, value: Any) -> str:
        if hasattr(value, "__dataclass_fields__"):
            value = asdict(value)
        return json.dumps(_redact_secrets(to_jsonable(value)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            secret_key = normalized in SECRET_KEY_NAMES or normalized.endswith(("_api_key", "_token", "_secret", "_password"))
            out[key] = "[redacted]" if secret_key else _redact_secrets(item)
        return out
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(text: str) -> str:
    for pattern in SECRET_TEXT_PATTERNS[:2]:
        text = pattern.sub(r"\1[redacted]", text)
    return SECRET_TEXT_PATTERNS[2].sub("[redacted]", text)
