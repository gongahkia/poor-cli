"""Durable multiplayer session primitives.

This module intentionally models collaboration state without owning transport.
The stdio server, a future socket host, and the TUI can all build on the same
repo-local store.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .exceptions import ValidationError
from .persisted import run_sqlite_migrations


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load_dict(value: str) -> Dict[str, Any]:
    try:
        loaded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _json_load_list(value: str) -> List[Any]:
    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


@dataclass(frozen=True)
class Participant:
    participant_id: str
    display_name: str
    is_host: bool
    joined_at: str
    last_seen_at: str
    removed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "participantId": self.participant_id,
            "displayName": self.display_name,
            "isHost": self.is_host,
            "joinedAt": self.joined_at,
            "lastSeenAt": self.last_seen_at,
            "removedAt": self.removed_at or None,
        }


@dataclass(frozen=True)
class QueueItem:
    item_id: str
    author_id: str
    prompt: str
    status: str
    position: int
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "itemId": self.item_id,
            "authorId": self.author_id,
            "prompt": self.prompt,
            "status": self.status,
            "position": self.position,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class TaskThread:
    thread_id: str
    title: str
    description: str
    creator_id: str
    status: str
    summary: str
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "threadId": self.thread_id,
            "title": self.title,
            "description": self.description,
            "creatorId": self.creator_id,
            "status": self.status,
            "summary": self.summary,
            "metadata": self.metadata,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class MergeRequest:
    merge_id: str
    thread_id: str
    author_id: str
    status: str
    summary: str
    context_summary: str
    workspace_diff: str
    template_id: str
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mergeId": self.merge_id,
            "threadId": self.thread_id,
            "authorId": self.author_id,
            "status": self.status,
            "summary": self.summary,
            "contextSummary": self.context_summary,
            "workspaceDiff": self.workspace_diff,
            "templateId": self.template_id or None,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class ApprovalTemplate:
    template_id: str
    name: str
    applies_to: List[str]
    required_count: int
    required_people: List[str]
    created_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "templateId": self.template_id,
            "name": self.name,
            "appliesTo": self.applies_to,
            "requiredCount": self.required_count,
            "requiredPeople": self.required_people,
            "createdBy": self.created_by,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


class MultiplayerStore:
    """Repo-local state for one hosted multiplayer session."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.base_dir = self.repo_root / ".poor-cli"
        self.db_path = self.base_dir / "multiplayer.db"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
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
            run_sqlite_migrations(conn, "multiplayer")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS participants (
                    participant_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    is_host INTEGER NOT NULL DEFAULT 0,
                    joined_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    removed_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS prompt_queue (
                    item_id TEXT PRIMARY KEY,
                    author_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_threads (
                    thread_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    creator_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS thread_events (
                    event_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS merge_requests (
                    merge_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    context_summary TEXT NOT NULL,
                    workspace_diff TEXT NOT NULL,
                    template_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approval_templates (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    applies_to_json TEXT NOT NULL,
                    required_count INTEGER NOT NULL,
                    required_people_json TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    participant_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(target_type, target_id, participant_id)
                );
                """
            )

    def host_session(self, display_name: str) -> Participant:
        name = display_name.strip() or "Host"
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM participants WHERE is_host = 1 AND removed_at = '' LIMIT 1"
            ).fetchone()
            if existing is not None:
                return self._participant_from_row(existing)
            participant_id = f"host-{uuid.uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO participants (
                    participant_id, display_name, is_host, joined_at, last_seen_at
                ) VALUES (?, ?, 1, ?, ?)
                """,
                (participant_id, name, now, now),
            )
            row = conn.execute(
                "SELECT * FROM participants WHERE participant_id = ?",
                (participant_id,),
            ).fetchone()
        return self._participant_from_row(row)

    def join_session(self, display_name: str) -> Participant:
        name = display_name.strip() or "Peer"
        now = _utc_now()
        participant_id = f"peer-{uuid.uuid4().hex[:8]}"
        with self._connect() as conn:
            self._require_host_exists(conn)
            conn.execute(
                """
                INSERT INTO participants (
                    participant_id, display_name, is_host, joined_at, last_seen_at
                ) VALUES (?, ?, 0, ?, ?)
                """,
                (participant_id, name, now, now),
            )
            row = conn.execute(
                "SELECT * FROM participants WHERE participant_id = ?",
                (participant_id,),
            ).fetchone()
        return self._participant_from_row(row)

    def list_participants(self, *, include_removed: bool = False) -> List[Participant]:
        where = "" if include_removed else "WHERE removed_at = ''"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM participants {where} ORDER BY is_host DESC, joined_at ASC"
            ).fetchall()
        return [self._participant_from_row(row) for row in rows]

    def remove_participant(self, actor_id: str, participant_id: str) -> Participant:
        now = _utc_now()
        with self._connect() as conn:
            self._require_host(conn, actor_id)
            target = self._get_participant(conn, participant_id)
            if target["is_host"]:
                raise ValidationError("host cannot be removed")
            conn.execute(
                "UPDATE participants SET removed_at = ?, last_seen_at = ? WHERE participant_id = ?",
                (now, now, participant_id),
            )
            row = self._get_participant(conn, participant_id, include_removed=True)
        return self._participant_from_row(row)

    def enqueue_prompt(self, author_id: str, prompt: str) -> QueueItem:
        text = prompt.strip()
        if not text:
            raise ValidationError("prompt is required")
        now = _utc_now()
        item_id = f"q-{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            self._require_active_participant(conn, author_id)
            position = self._next_queue_position(conn)
            conn.execute(
                """
                INSERT INTO prompt_queue (
                    item_id, author_id, prompt, status, position, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?)
                """,
                (item_id, author_id, text, position, now, now),
            )
            row = self._get_queue_item(conn, item_id)
        return self._queue_from_row(row)

    def list_queue(self, statuses: Optional[Sequence[str]] = None) -> List[QueueItem]:
        query = "SELECT * FROM prompt_queue"
        params: List[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            params.extend(str(status) for status in statuses)
        query += " ORDER BY position ASC, created_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._queue_from_row(row) for row in rows]

    def update_queued_prompt(self, actor_id: str, item_id: str, prompt: str) -> QueueItem:
        text = prompt.strip()
        if not text:
            raise ValidationError("prompt is required")
        now = _utc_now()
        with self._connect() as conn:
            actor = self._require_active_participant(conn, actor_id)
            item = self._get_queue_item(conn, item_id)
            if item["status"] != "queued":
                raise ValidationError("only queued prompts can be edited")
            if not actor["is_host"] and item["author_id"] != actor_id:
                raise ValidationError("only the author or host can edit this prompt")
            conn.execute(
                "UPDATE prompt_queue SET prompt = ?, updated_at = ? WHERE item_id = ?",
                (text, now, item_id),
            )
            row = self._get_queue_item(conn, item_id)
        return self._queue_from_row(row)

    def move_queue_item(self, actor_id: str, item_id: str, direction: str) -> QueueItem:
        step = direction.strip().lower()
        if step not in {"up", "down"}:
            raise ValidationError("direction must be 'up' or 'down'")
        now = _utc_now()
        with self._connect() as conn:
            self._require_host(conn, actor_id)
            item = self._get_queue_item(conn, item_id)
            if item["status"] != "queued":
                raise ValidationError("only queued prompts can be moved")
            comparator = "<" if step == "up" else ">"
            ordering = "DESC" if step == "up" else "ASC"
            neighbor = conn.execute(
                f"""
                SELECT * FROM prompt_queue
                WHERE status = 'queued' AND position {comparator} ?
                ORDER BY position {ordering}
                LIMIT 1
                """,
                (int(item["position"]),),
            ).fetchone()
            if neighbor is None:
                return self._queue_from_row(item)
            conn.execute(
                "UPDATE prompt_queue SET position = ?, updated_at = ? WHERE item_id = ?",
                (int(neighbor["position"]), now, item_id),
            )
            conn.execute(
                "UPDATE prompt_queue SET position = ?, updated_at = ? WHERE item_id = ?",
                (int(item["position"]), now, str(neighbor["item_id"])),
            )
            row = self._get_queue_item(conn, item_id)
        return self._queue_from_row(row)

    def cancel_queue_item(self, actor_id: str, item_id: str) -> QueueItem:
        now = _utc_now()
        with self._connect() as conn:
            actor = self._require_active_participant(conn, actor_id)
            item = self._get_queue_item(conn, item_id)
            if item["status"] not in {"queued", "running"}:
                raise ValidationError("prompt is already terminal")
            if not actor["is_host"] and item["author_id"] != actor_id:
                raise ValidationError("only the author or host can cancel this prompt")
            conn.execute(
                "UPDATE prompt_queue SET status = 'cancelled', updated_at = ? WHERE item_id = ?",
                (now, item_id),
            )
            row = self._get_queue_item(conn, item_id)
        return self._queue_from_row(row)

    def create_thread(
        self,
        creator_id: str,
        title: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskThread:
        clean_title = title.strip()
        if not clean_title:
            raise ValidationError("title is required")
        now = _utc_now()
        thread_id = f"thr-{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            self._require_active_participant(conn, creator_id)
            conn.execute(
                """
                INSERT INTO task_threads (
                    thread_id, title, description, creator_id, status, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    thread_id,
                    clean_title,
                    description.strip(),
                    creator_id,
                    _json_dump(metadata or {}),
                    now,
                    now,
                ),
            )
            row = self._get_thread(conn, thread_id)
        return self._thread_from_row(row)

    def list_threads(self, statuses: Optional[Sequence[str]] = None) -> List[TaskThread]:
        query = "SELECT * FROM task_threads"
        params: List[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            params.extend(str(status) for status in statuses)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._thread_from_row(row) for row in rows]

    def add_thread_event(
        self,
        thread_id: str,
        author_id: str,
        event_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        text = content.strip()
        if not text:
            raise ValidationError("content is required")
        now = _utc_now()
        event_id = f"evt-{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            self._require_active_participant(conn, author_id)
            self._get_thread(conn, thread_id)
            conn.execute(
                """
                INSERT INTO thread_events (
                    event_id, thread_id, author_id, event_type, content, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    thread_id,
                    author_id,
                    event_type.strip() or "comment",
                    text,
                    _json_dump(metadata or {}),
                    now,
                ),
            )
            conn.execute(
                "UPDATE task_threads SET updated_at = ? WHERE thread_id = ?",
                (now, thread_id),
            )
        return {
            "eventId": event_id,
            "threadId": thread_id,
            "authorId": author_id,
            "eventType": event_type.strip() or "comment",
            "content": text,
            "metadata": metadata or {},
            "createdAt": now,
        }

    def create_merge_request(
        self,
        thread_id: str,
        author_id: str,
        summary: str,
        context_summary: str = "",
        workspace_diff: str = "",
        template_id: str = "",
    ) -> MergeRequest:
        clean_summary = summary.strip()
        if not clean_summary:
            raise ValidationError("summary is required")
        now = _utc_now()
        merge_id = f"merge-{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            self._require_active_participant(conn, author_id)
            self._get_thread(conn, thread_id)
            if template_id:
                self._get_template(conn, template_id)
            conn.execute(
                """
                INSERT INTO merge_requests (
                    merge_id, thread_id, author_id, status, summary, context_summary,
                    workspace_diff, template_id, created_at, updated_at
                ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)
                """,
                (
                    merge_id,
                    thread_id,
                    author_id,
                    clean_summary,
                    context_summary.strip(),
                    workspace_diff,
                    template_id.strip(),
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE task_threads SET status = 'merge_requested', updated_at = ? WHERE thread_id = ?",
                (now, thread_id),
            )
            row = self._get_merge(conn, merge_id)
        return self._merge_from_row(row)

    def merge_thread(self, actor_id: str, merge_id: str) -> MergeRequest:
        now = _utc_now()
        with self._connect() as conn:
            self._require_host(conn, actor_id)
            merge = self._get_merge(conn, merge_id)
            if merge["status"] != "open":
                raise ValidationError("merge request is not open")
            if not self._merge_approval_satisfied(conn, merge):
                raise ValidationError("merge request approval requirements are not satisfied")
            conn.execute(
                "UPDATE merge_requests SET status = 'merged', updated_at = ? WHERE merge_id = ?",
                (now, merge_id),
            )
            conn.execute(
                "UPDATE task_threads SET status = 'merged', summary = ?, updated_at = ? WHERE thread_id = ?",
                (merge["summary"], now, merge["thread_id"]),
            )
            row = self._get_merge(conn, merge_id)
        return self._merge_from_row(row)

    def upsert_approval_template(
        self,
        actor_id: str,
        name: str,
        applies_to: Sequence[str],
        required_count: int = 1,
        required_people: Optional[Sequence[str]] = None,
        template_id: str = "",
    ) -> ApprovalTemplate:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("name is required")
        clean_applies = [str(item).strip() for item in applies_to if str(item).strip()]
        if not clean_applies:
            raise ValidationError("appliesTo is required")
        clean_people = [str(item).strip() for item in (required_people or ()) if str(item).strip()]
        required = max(0, int(required_count))
        if required == 0 and not clean_people:
            raise ValidationError("template must require a count or named people")
        now = _utc_now()
        target_id = template_id.strip() or f"tmpl-{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            self._require_host(conn, actor_id)
            conn.execute(
                """
                INSERT INTO approval_templates (
                    template_id, name, applies_to_json, required_count,
                    required_people_json, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(template_id) DO UPDATE SET
                    name = excluded.name,
                    applies_to_json = excluded.applies_to_json,
                    required_count = excluded.required_count,
                    required_people_json = excluded.required_people_json,
                    updated_at = excluded.updated_at
                """,
                (
                    target_id,
                    clean_name,
                    _json_dump(clean_applies),
                    required,
                    _json_dump(clean_people),
                    actor_id,
                    now,
                    now,
                ),
            )
            row = self._get_template(conn, target_id)
        return self._template_from_row(row)

    def list_approval_templates(self) -> List[ApprovalTemplate]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_templates ORDER BY name ASC"
            ).fetchall()
        return [self._template_from_row(row) for row in rows]

    def record_approval(
        self,
        participant_id: str,
        target_type: str,
        target_id: str,
        template_id: str,
        decision: str = "approved",
    ) -> Dict[str, Any]:
        clean_decision = decision.strip().lower() or "approved"
        if clean_decision not in {"approved", "rejected"}:
            raise ValidationError("decision must be approved or rejected")
        now = _utc_now()
        approval_id = f"appr-{uuid.uuid4().hex[:10]}"
        with self._connect() as conn:
            self._require_active_participant(conn, participant_id)
            template = self._get_template(conn, template_id)
            if target_type == "merge":
                self._get_merge(conn, target_id)
            if not self._participant_eligible_for_template(template, participant_id):
                raise ValidationError("participant is not eligible for this approval template")
            conn.execute(
                """
                INSERT INTO approvals (
                    approval_id, target_type, target_id, template_id,
                    participant_id, decision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_type, target_id, participant_id) DO UPDATE SET
                    template_id = excluded.template_id,
                    decision = excluded.decision,
                    created_at = excluded.created_at
                """,
                (
                    approval_id,
                    target_type.strip(),
                    target_id.strip(),
                    template_id.strip(),
                    participant_id,
                    clean_decision,
                    now,
                ),
            )
        return {
            "targetType": target_type.strip(),
            "targetId": target_id.strip(),
            "templateId": template_id.strip(),
            "participantId": participant_id,
            "decision": clean_decision,
            "createdAt": now,
        }

    def approval_status(self, target_type: str, target_id: str, template_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            template = self._get_template(conn, template_id)
            rows = conn.execute(
                """
                SELECT * FROM approvals
                WHERE target_type = ? AND target_id = ? AND template_id = ?
                ORDER BY created_at ASC
                """,
                (target_type.strip(), target_id.strip(), template_id.strip()),
            ).fetchall()
        approvals = [dict(row) for row in rows]
        approved_people = [
            str(row["participant_id"])
            for row in approvals
            if str(row["decision"]) == "approved"
        ]
        required_people = _json_load_list(str(template["required_people_json"]))
        required_count = int(template["required_count"])
        named_ok = all(person in approved_people for person in required_people)
        count_ok = len(set(approved_people)) >= required_count
        return {
            "targetType": target_type.strip(),
            "targetId": target_id.strip(),
            "template": self._template_from_row(template).to_dict(),
            "approvals": approvals,
            "approvedPeople": approved_people,
            "satisfied": named_ok and count_ok,
        }

    def _merge_approval_satisfied(self, conn: sqlite3.Connection, merge: sqlite3.Row) -> bool:
        template_id = str(merge["template_id"] or "")
        if not template_id:
            return True
        template = self._get_template(conn, template_id)
        rows = conn.execute(
            """
            SELECT participant_id, decision FROM approvals
            WHERE target_type = 'merge' AND target_id = ? AND template_id = ?
            """,
            (str(merge["merge_id"]), template_id),
        ).fetchall()
        approved_people = {
            str(row["participant_id"])
            for row in rows
            if str(row["decision"]) == "approved"
        }
        required_people = {str(person) for person in _json_load_list(str(template["required_people_json"]))}
        return required_people.issubset(approved_people) and len(approved_people) >= int(template["required_count"])

    def _participant_eligible_for_template(self, template: sqlite3.Row, participant_id: str) -> bool:
        required_people = [str(person) for person in _json_load_list(str(template["required_people_json"]))]
        return not required_people or participant_id in required_people

    @staticmethod
    def _participant_from_row(row: sqlite3.Row) -> Participant:
        return Participant(
            participant_id=str(row["participant_id"]),
            display_name=str(row["display_name"]),
            is_host=bool(row["is_host"]),
            joined_at=str(row["joined_at"]),
            last_seen_at=str(row["last_seen_at"]),
            removed_at=str(row["removed_at"] or ""),
        )

    @staticmethod
    def _queue_from_row(row: sqlite3.Row) -> QueueItem:
        return QueueItem(
            item_id=str(row["item_id"]),
            author_id=str(row["author_id"]),
            prompt=str(row["prompt"]),
            status=str(row["status"]),
            position=int(row["position"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _thread_from_row(row: sqlite3.Row) -> TaskThread:
        return TaskThread(
            thread_id=str(row["thread_id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            creator_id=str(row["creator_id"]),
            status=str(row["status"]),
            summary=str(row["summary"]),
            metadata=_json_load_dict(str(row["metadata_json"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _merge_from_row(row: sqlite3.Row) -> MergeRequest:
        return MergeRequest(
            merge_id=str(row["merge_id"]),
            thread_id=str(row["thread_id"]),
            author_id=str(row["author_id"]),
            status=str(row["status"]),
            summary=str(row["summary"]),
            context_summary=str(row["context_summary"]),
            workspace_diff=str(row["workspace_diff"]),
            template_id=str(row["template_id"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _template_from_row(row: sqlite3.Row) -> ApprovalTemplate:
        return ApprovalTemplate(
            template_id=str(row["template_id"]),
            name=str(row["name"]),
            applies_to=[str(item) for item in _json_load_list(str(row["applies_to_json"]))],
            required_count=int(row["required_count"]),
            required_people=[str(item) for item in _json_load_list(str(row["required_people_json"]))],
            created_by=str(row["created_by"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _get_participant(
        self,
        conn: sqlite3.Connection,
        participant_id: str,
        *,
        include_removed: bool = False,
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM participants WHERE participant_id = ?",
            (participant_id.strip(),),
        ).fetchone()
        if row is None or (not include_removed and str(row["removed_at"] or "")):
            raise ValidationError(f"unknown participant: {participant_id}")
        return row

    def _require_active_participant(self, conn: sqlite3.Connection, participant_id: str) -> sqlite3.Row:
        return self._get_participant(conn, participant_id)

    def _require_host(self, conn: sqlite3.Connection, participant_id: str) -> sqlite3.Row:
        row = self._require_active_participant(conn, participant_id)
        if not bool(row["is_host"]):
            raise ValidationError("host privileges required")
        return row

    @staticmethod
    def _require_host_exists(conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT participant_id FROM participants WHERE is_host = 1 AND removed_at = '' LIMIT 1"
        ).fetchone()
        if row is None:
            raise ValidationError("no hosted multiplayer session exists")

    @staticmethod
    def _next_queue_position(conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM prompt_queue WHERE status = 'queued'"
        ).fetchone()
        return int(row["next_position"] if row is not None else 1)

    @staticmethod
    def _get_queue_item(conn: sqlite3.Connection, item_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM prompt_queue WHERE item_id = ?",
            (item_id.strip(),),
        ).fetchone()
        if row is None:
            raise ValidationError(f"unknown queue item: {item_id}")
        return row

    @staticmethod
    def _get_thread(conn: sqlite3.Connection, thread_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM task_threads WHERE thread_id = ?",
            (thread_id.strip(),),
        ).fetchone()
        if row is None:
            raise ValidationError(f"unknown task thread: {thread_id}")
        return row

    @staticmethod
    def _get_merge(conn: sqlite3.Connection, merge_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM merge_requests WHERE merge_id = ?",
            (merge_id.strip(),),
        ).fetchone()
        if row is None:
            raise ValidationError(f"unknown merge request: {merge_id}")
        return row

    @staticmethod
    def _get_template(conn: sqlite3.Connection, template_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM approval_templates WHERE template_id = ?",
            (template_id.strip(),),
        ).fetchone()
        if row is None:
            raise ValidationError(f"unknown approval template: {template_id}")
        return row
