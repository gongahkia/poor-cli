"""Case storage backends for the Stage-1 HTTP service."""
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, Protocol


CaseMutator = Callable[[dict[str, Any]], dict[str, Any]]


class CaseNotFound(Exception):
    """Raised when a request references an unknown case_id."""


class CaseStoreProtocol(Protocol):
    def create(self, case: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, case_id: str) -> dict[str, Any]: ...
    def replace(self, case: dict[str, Any]) -> dict[str, Any]: ...
    def update(self, case_id: str, mutator: CaseMutator) -> dict[str, Any]: ...


def _clone(case: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(case)


def _revision(case: dict[str, Any], default: int = 0) -> int:
    raw = case.get("revision", default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _prepare(case: dict[str, Any], revision: int) -> dict[str, Any]:
    stored = _clone(case)
    stored["revision"] = revision
    return stored


class CaseStore:
    """Process-local Case storage used by tests and in-memory demos."""

    def __init__(self) -> None:
        self._cases: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create(self, case: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            stored = _prepare(case, max(1, _revision(case, 1)))
            self._cases[str(stored["case_id"])] = stored
            return _clone(stored)

    def get(self, case_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                return _clone(self._cases[case_id])
            except KeyError as exc:
                raise CaseNotFound(case_id) from exc

    def replace(self, case: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            case_id = str(case["case_id"])
            previous = self._cases.get(case_id)
            next_revision = (_revision(previous, 0) if previous else _revision(case, 0)) + 1
            stored = _prepare(case, next_revision)
            self._cases[case_id] = stored
            return _clone(stored)

    def update(self, case_id: str, mutator: CaseMutator) -> dict[str, Any]:
        with self._lock:
            current = self.get(case_id)
            updated = mutator(current)
            if str(updated.get("case_id")) != case_id:
                raise ValueError("case_id cannot change during store update.")
            return self.replace(updated)


class SQLiteCaseStore:
    """SQLite-backed Case store with atomic per-process mutation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    payload TEXT NOT NULL
                )
                """
            )

    def create(self, case: dict[str, Any]) -> dict[str, Any]:
        stored = _prepare(case, max(1, _revision(case, 1)))
        payload = json.dumps(stored, sort_keys=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cases
                    (case_id, revision, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(stored["case_id"]),
                    stored["revision"],
                    stored.get("created_at"),
                    stored.get("updated_at"),
                    payload,
                ),
            )
        return _clone(stored)

    def get(self, case_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if row is None:
            raise CaseNotFound(case_id)
        payload = json.loads(str(row["payload"]))
        if not isinstance(payload, dict):
            raise CaseNotFound(case_id)
        return payload

    def replace(self, case: dict[str, Any]) -> dict[str, Any]:
        case_id = str(case["case_id"])
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT revision FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            previous_revision = int(row["revision"]) if row else _revision(case, 0)
            stored = _prepare(case, previous_revision + 1)
            conn.execute(
                """
                INSERT OR REPLACE INTO cases
                    (case_id, revision, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    stored["revision"],
                    stored.get("created_at"),
                    stored.get("updated_at"),
                    json.dumps(stored, sort_keys=True),
                ),
            )
            conn.commit()
        return _clone(stored)

    def update(self, case_id: str, mutator: CaseMutator) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT revision, payload FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if row is None:
                conn.rollback()
                raise CaseNotFound(case_id)
            current = json.loads(str(row["payload"]))
            if not isinstance(current, dict):
                conn.rollback()
                raise CaseNotFound(case_id)
            updated = mutator(current)
            if str(updated.get("case_id")) != case_id:
                conn.rollback()
                raise ValueError("case_id cannot change during store update.")
            stored = _prepare(updated, int(row["revision"]) + 1)
            conn.execute(
                """
                UPDATE cases
                SET revision = ?, updated_at = ?, payload = ?
                WHERE case_id = ?
                """,
                (
                    stored["revision"],
                    stored.get("updated_at"),
                    json.dumps(stored, sort_keys=True),
                    case_id,
                ),
            )
            conn.commit()
        return _clone(stored)
