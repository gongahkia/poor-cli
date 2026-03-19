"""Local scheduled automations backed by the durable task runner."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .run_history import RunHistoryManager
from .sandbox import normalize_preset
from .task_manager import APPROVAL_REQUIRED_PRESETS, TaskManager, TaskRecord

WEEKDAY_MAP = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now() -> str:
    return _utc_now_dt().isoformat()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def schedule_interval(minutes: int) -> Dict[str, Any]:
    minutes = int(minutes)
    if minutes <= 0:
        raise ValueError("Interval minutes must be positive.")
    return {"kind": "interval", "minutes": minutes}


def parse_daily_schedule(value: str) -> Dict[str, Any]:
    hour, minute = _parse_clock(value)
    return {"kind": "daily", "hour": hour, "minute": minute}


def parse_weekly_schedule(value: str) -> Dict[str, Any]:
    days_part, _, time_part = str(value).partition("@")
    if not days_part or not time_part:
        raise ValueError("Weekly schedule must look like `mon,wed@09:30`.")
    weekdays = []
    for raw_day in days_part.split(","):
        day = raw_day.strip().lower()
        if day not in WEEKDAY_MAP:
            raise ValueError(f"Unknown weekday: {raw_day}")
        weekday = WEEKDAY_MAP[day]
        if weekday not in weekdays:
            weekdays.append(weekday)
    if not weekdays:
        raise ValueError("Weekly schedule must include at least one weekday.")
    hour, minute = _parse_clock(time_part)
    return {"kind": "weekly", "weekdays": weekdays, "hour": hour, "minute": minute}


def format_schedule(schedule: Dict[str, Any]) -> str:
    kind = str(schedule.get("kind", ""))
    if kind == "interval":
        minutes = int(schedule["minutes"])
        return f"every {minutes} minute(s)"
    if kind == "daily":
        return f"daily at {int(schedule['hour']):02d}:{int(schedule['minute']):02d} UTC"
    if kind == "weekly":
        reverse_map = {value: key for key, value in WEEKDAY_MAP.items()}
        weekdays = ",".join(reverse_map[int(day)] for day in schedule.get("weekdays", []))
        return (
            f"weekly on {weekdays} at "
            f"{int(schedule['hour']):02d}:{int(schedule['minute']):02d} UTC"
        )
    raise ValueError(f"Unknown schedule kind: {kind}")


def next_run_after(schedule: Dict[str, Any], now: Optional[datetime] = None) -> datetime:
    current = (now or _utc_now_dt()).astimezone(timezone.utc)
    kind = str(schedule.get("kind", ""))
    if kind == "interval":
        return current + timedelta(minutes=int(schedule["minutes"]))

    if kind == "daily":
        candidate = current.replace(
            hour=int(schedule["hour"]),
            minute=int(schedule["minute"]),
            second=0,
            microsecond=0,
        )
        if candidate <= current:
            candidate += timedelta(days=1)
        return candidate

    if kind == "weekly":
        weekdays = [int(day) for day in schedule.get("weekdays", [])]
        target_time = clock_time(
            hour=int(schedule["hour"]),
            minute=int(schedule["minute"]),
            tzinfo=timezone.utc,
        )
        for delta in range(0, 15):
            candidate_day = (current + timedelta(days=delta)).date()
            if candidate_day.weekday() not in weekdays:
                continue
            candidate = datetime.combine(candidate_day, target_time)
            if candidate > current:
                return candidate
        raise ValueError("Unable to compute next weekly run.")

    raise ValueError(f"Unknown schedule kind: {kind}")


def _parse_clock(value: str) -> tuple[int, int]:
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError("Expected time in HH:MM format.")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Expected time in HH:MM format.")
    return hour, minute


@dataclass(frozen=True)
class AutomationRecord:
    automation_id: str
    name: str
    prompt: str
    schedule_json: str
    sandbox_preset: str
    enabled: bool
    requires_approval: bool
    created_at: str
    updated_at: str
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_task_id: Optional[str] = None
    metadata_json: str = "{}"

    @property
    def schedule(self) -> Dict[str, Any]:
        loaded = json.loads(self.schedule_json)
        return loaded if isinstance(loaded, dict) else {}

    @property
    def metadata(self) -> Dict[str, Any]:
        loaded = json.loads(self.metadata_json)
        return loaded if isinstance(loaded, dict) else {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "automationId": self.automation_id,
            "name": self.name,
            "prompt": self.prompt,
            "schedule": self.schedule,
            "scheduleSummary": format_schedule(self.schedule),
            "sandboxPreset": self.sandbox_preset,
            "enabled": self.enabled,
            "requiresApproval": self.requires_approval,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "lastRunAt": self.last_run_at,
            "nextRunAt": self.next_run_at,
            "lastTaskId": self.last_task_id,
            "metadata": self.metadata,
        }


class AutomationManager:
    def __init__(self, repo_root: Optional[Path] = None, task_manager: Optional[TaskManager] = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.task_manager = task_manager or TaskManager(self.repo_root)
        self.tasks_dir = self.repo_root / ".poor-cli" / "tasks"
        self.db_path = self.tasks_dir / "automations.db"
        self.run_history = RunHistoryManager(self.repo_root)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automations (
                    automation_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    schedule_json TEXT NOT NULL,
                    sandbox_preset TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    requires_approval INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT,
                    last_task_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def create_automation(
        self,
        *,
        name: str,
        prompt: str,
        schedule: Dict[str, Any],
        sandbox_preset: str = "read-only",
        enabled: bool = True,
        requires_approval: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        auto_approve: bool = False,
    ) -> AutomationRecord:
        name = str(name).strip() or "Automation"
        prompt = str(prompt).strip()
        if not prompt:
            raise ValueError("Automation prompt cannot be empty.")
        validated_schedule = self._validate_schedule(schedule)
        current = _utc_now_dt()
        preset = normalize_preset(sandbox_preset)
        metadata_payload = dict(metadata or {})
        effective_auto_approve = bool(
            auto_approve or metadata_payload.get("autoApprove", False)
        )
        if effective_auto_approve or "autoApprove" in metadata_payload or auto_approve:
            metadata_payload["autoApprove"] = effective_auto_approve
        record = AutomationRecord(
            automation_id=uuid.uuid4().hex[:12],
            name=name,
            prompt=prompt,
            schedule_json=json.dumps(validated_schedule, ensure_ascii=False),
            sandbox_preset=preset,
            enabled=bool(enabled),
            requires_approval=bool(
                requires_approval or (preset in APPROVAL_REQUIRED_PRESETS and not effective_auto_approve)
            ),
            created_at=current.isoformat(),
            updated_at=current.isoformat(),
            next_run_at=next_run_after(validated_schedule, current).isoformat() if enabled else None,
            metadata_json=json.dumps(metadata_payload, ensure_ascii=False),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automations (
                    automation_id, name, prompt, schedule_json, sandbox_preset,
                    enabled, requires_approval, created_at, updated_at,
                    last_run_at, next_run_at, last_task_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.automation_id,
                    record.name,
                    record.prompt,
                    record.schedule_json,
                    record.sandbox_preset,
                    int(record.enabled),
                    int(record.requires_approval),
                    record.created_at,
                    record.updated_at,
                    record.last_run_at,
                    record.next_run_at,
                    record.last_task_id,
                    record.metadata_json,
                ),
            )
        return record

    def list_automations(self, *, enabled: Optional[bool] = None, limit: int = 100) -> List[AutomationRecord]:
        clauses: List[str] = []
        params: List[Any] = []
        if enabled is not None:
            clauses.append("enabled = ?")
            params.append(1 if enabled else 0)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM automations
                {where_sql}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_automation(self, automation_id: str) -> Optional[AutomationRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM automations WHERE automation_id = ?",
                (str(automation_id).strip(),),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def set_enabled(self, automation_id: str, enabled: bool) -> AutomationRecord:
        record = self._require_automation(automation_id)
        updates: Dict[str, Any] = {"enabled": int(bool(enabled))}
        if enabled:
            updates["next_run_at"] = next_run_after(record.schedule).isoformat()
        else:
            updates["next_run_at"] = None
        self._update_automation(automation_id, **updates)
        return self._require_automation(automation_id)

    def run_now(self, automation_id: str) -> TaskRecord:
        record = self._require_automation(automation_id)
        return self._launch_task(record, now=_utc_now_dt())

    def run_due(self, *, limit: int = 20, now: Optional[datetime] = None) -> List[TaskRecord]:
        current = (now or _utc_now_dt()).astimezone(timezone.utc)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM automations
                WHERE enabled = 1
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at ASC
                LIMIT ?
                """,
                (current.isoformat(), max(1, min(int(limit), 200))),
            ).fetchall()
        tasks: List[TaskRecord] = []
        for row in rows:
            tasks.append(self._launch_task(self._row_to_record(row), now=current))
        return tasks

    def history(self, automation_id: str, *, limit: int = 25) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        scan_limit = max(limit * 6, 50)
        for record in self.run_history.list_runs(source_kind="task", limit=scan_limit):
            metadata = record.metadata
            if str(metadata.get("automationId", "")).strip() != str(automation_id).strip():
                continue
            matches.append(record.to_dict())
            if len(matches) >= limit:
                break
        return matches

    def replay(self, automation_id: str) -> TaskRecord:
        record = self._require_automation(automation_id)
        history = self.history(automation_id, limit=25)
        replay_of_run_id = ""
        for entry in history:
            if entry.get("status") == "completed":
                replay_of_run_id = str(entry.get("runId", "")).strip()
                break
        if not replay_of_run_id and history:
            replay_of_run_id = str(history[0].get("runId", "")).strip()

        metadata = dict(record.metadata)
        if replay_of_run_id:
            metadata["replayOfRunId"] = replay_of_run_id
        metadata["automationReplay"] = True
        return self._launch_task(record, now=_utc_now_dt(), metadata_override=metadata)

    def serve_forever(self, *, poll_seconds: int = 30) -> None:
        interval = max(5, int(poll_seconds))
        while True:
            self.run_due()
            time.sleep(interval)

    def _launch_task(
        self,
        record: AutomationRecord,
        *,
        now: datetime,
        metadata_override: Optional[Dict[str, Any]] = None,
    ) -> TaskRecord:
        metadata = dict(metadata_override or record.metadata)
        metadata.update(
            {
                "automationId": record.automation_id,
                "automationName": record.name,
                "schedule": record.schedule,
            }
        )
        task = self.task_manager.create_task(
            title=record.name,
            prompt=record.prompt,
            sandbox_preset=record.sandbox_preset,
            source="automation",
            metadata=metadata,
            auto_start=not record.requires_approval,
            requires_approval=record.requires_approval,
            auto_approve=bool(metadata.get("autoApprove", False)),
        )
        self._update_automation(
            record.automation_id,
            last_run_at=now.isoformat(),
            last_task_id=task.task_id,
            next_run_at=next_run_after(record.schedule, now).isoformat() if record.enabled else None,
        )
        return task

    def _validate_schedule(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(schedule, dict):
            raise ValueError("Schedule must be an object.")
        kind = str(schedule.get("kind", "")).strip().lower()
        if kind == "interval":
            return schedule_interval(int(schedule.get("minutes", 0)))
        if kind == "daily":
            return parse_daily_schedule(f"{int(schedule.get('hour', -1)):02d}:{int(schedule.get('minute', -1)):02d}")
        if kind == "weekly":
            weekdays = schedule.get("weekdays", [])
            if not isinstance(weekdays, Sequence) or not weekdays:
                raise ValueError("Weekly schedule must include weekdays.")
            rendered_days = ",".join(
                key for key, value in WEEKDAY_MAP.items() if value in {int(day) for day in weekdays}
            )
            return parse_weekly_schedule(
                f"{rendered_days}@{int(schedule.get('hour', -1)):02d}:{int(schedule.get('minute', -1)):02d}"
            )
        raise ValueError(f"Unknown schedule kind: {kind}")

    def _update_automation(self, automation_id: str, **updates: Any) -> None:
        if not updates:
            return
        updates["updated_at"] = _utc_now()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        params = list(updates.values()) + [automation_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE automations SET {assignments} WHERE automation_id = ?",
                params,
            )

    def _require_automation(self, automation_id: str) -> AutomationRecord:
        record = self.get_automation(automation_id)
        if record is None:
            raise FileNotFoundError(f"Unknown automation: {automation_id}")
        return record

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AutomationRecord:
        return AutomationRecord(
            automation_id=row["automation_id"],
            name=row["name"],
            prompt=row["prompt"],
            schedule_json=row["schedule_json"],
            sandbox_preset=row["sandbox_preset"],
            enabled=bool(row["enabled"]),
            requires_approval=bool(row["requires_approval"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_run_at=row["last_run_at"],
            next_run_at=row["next_run_at"],
            last_task_id=row["last_task_id"],
            metadata_json=row["metadata_json"],
        )
