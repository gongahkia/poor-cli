"""
Audit logging framework for poor-cli

Comprehensive logging of all file operations, bash commands, and API calls
for security and compliance purposes.
"""

import gzip
import contextlib
import os
import re
import json
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable
from dataclasses import dataclass
from enum import Enum

from poor_cli.exceptions import setup_logger
from poor_cli.persisted import run_sqlite_migrations

logger = setup_logger(__name__)

AUDIT_COLUMNS = (
    "event_id",
    "event_type",
    "severity",
    "timestamp",
    "user",
    "operation",
    "target",
    "details",
    "success",
    "error_message",
)

DEFAULT_MAX_SIZE_MB = 100
DEFAULT_MAX_ROWS_LIVE = 100_000
DEFAULT_MAX_AGE_DAYS_LIVE = 90
DEFAULT_ARCHIVE_CHUNK_SIZE = 10_000
DEFAULT_ROTATION_RUNTIME_SECONDS = 5.0


class AuditEventType(Enum):
    """Types of auditable events"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    BASH_COMMAND = "bash_command"
    API_CALL = "api_call"
    CONFIG_CHANGE = "config_change"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    CHECKPOINT_CREATE = "checkpoint_create"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    TOOL_EXECUTION = "tool_execution"
    HOOK_ALLOW = "hook_allow"
    HOOK_DENY = "hook_deny"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_INVALIDATE = "cache_invalidate"
    RPC_RATE_LIMIT_EXCEEDED = "rpc.rate_limit.exceeded"


class AuditSeverity(Enum):
    """Severity levels for audit events"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Represents a single audit event"""
    event_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: str
    user: str
    operation: str
    target: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp,
            "user": self.user,
            "operation": self.operation,
            "target": self.target,
            "details": json.dumps(self.details) if self.details else None,
            "success": self.success,
            "error_message": self.error_message
        }


class AuditLogger:
    """Main audit logging system"""

    def __init__(
        self,
        audit_dir: Optional[Path] = None,
        enable_export: bool = True,
        retention_days: int = 90,
        max_size_mb: float = DEFAULT_MAX_SIZE_MB,
        max_rows_live: int = DEFAULT_MAX_ROWS_LIVE,
        max_age_days_live: int = DEFAULT_MAX_AGE_DAYS_LIVE,
        archive_chunk_size: int = DEFAULT_ARCHIVE_CHUNK_SIZE,
        archive_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
        rotation_runtime_seconds: float = DEFAULT_ROTATION_RUNTIME_SECONDS,
    ):
        """Initialize audit logger

        Args:
            audit_dir: Directory for audit logs (defaults to ~/.poor-cli/audit)
            enable_export: Enable JSON export functionality
            retention_days: Number of days to retain audit logs
        """
        self.audit_dir = audit_dir or (Path.home() / ".poor-cli")
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or (self.audit_dir / "audit.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir = archive_dir or (self.audit_dir / "audit" / "archive")
        self.enable_export = enable_export
        self.retention_days = retention_days
        self.max_size_mb = max_size_mb
        self.max_rows_live = max_rows_live
        self.max_age_days_live = max_age_days_live
        self.archive_chunk_size = archive_chunk_size
        self.rotation_runtime_seconds = rotation_runtime_seconds

        self._init_database()
        logger.info(f"Initialized audit logger at {self.audit_dir}")

    def _init_database(self):
        """Initialize audit database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    target TEXT,
                    details TEXT,
                    success INTEGER DEFAULT 1,
                    error_message TEXT
                )
            """)

            # Indexes for efficient querying
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_events(timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type ON audit_events(event_type)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user ON audit_events(user)
            """)

            run_sqlite_migrations(conn, "audit")
            conn.commit()
            conn.close()
            logger.debug("Audit database initialized")

        except Exception as e:
            logger.error(f"Failed to initialize audit database: {e}")

    def log_event(
        self,
        event_type: AuditEventType,
        operation: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> str:
        """Log an audit event

        Args:
            event_type: Type of event
            operation: Description of operation
            target: Target file/resource
            details: Additional details
            severity: Event severity
            success: Whether operation succeeded
            error_message: Error message if failed

        Returns:
            Event ID
        """
        import os
        import uuid

        # Generate event ID
        event_id = uuid.uuid4().hex[:16]

        # Get current user
        user = os.getenv("USER", os.getenv("USERNAME", "unknown"))

        # Create audit event
        event = AuditEvent(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now().isoformat(),
            user=user,
            operation=operation,
            target=target,
            details=details,
            success=success,
            error_message=error_message
        )

        # Save to database
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            event_dict = event.to_dict()
            cursor.execute("""
                INSERT INTO audit_events
                (event_id, event_type, severity, timestamp, user, operation,
                 target, details, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_dict["event_id"],
                event_dict["event_type"],
                event_dict["severity"],
                event_dict["timestamp"],
                event_dict["user"],
                event_dict["operation"],
                event_dict["target"],
                event_dict["details"],
                1 if event_dict["success"] else 0,
                event_dict["error_message"]
            ))
            conn.commit()
            logger.debug(f"Logged audit event: {event_type.value} - {operation}")
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            raise
        finally:
            conn.close()

        return event_id

    def log_file_operation(
        self,
        operation: str,
        file_path: str,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log a file operation

        Args:
            operation: Operation type (read, write, edit, delete)
            file_path: Path to file
            success: Whether operation succeeded
            details: Additional details
        """
        event_type_map = {
            "read": AuditEventType.FILE_READ,
            "write": AuditEventType.FILE_WRITE,
            "edit": AuditEventType.FILE_EDIT,
            "delete": AuditEventType.FILE_DELETE
        }

        event_type = event_type_map.get(operation.lower(), AuditEventType.FILE_WRITE)
        severity = AuditSeverity.INFO if success else AuditSeverity.WARNING

        self.log_event(
            event_type=event_type,
            operation=f"File {operation}",
            target=file_path,
            details=details,
            severity=severity,
            success=success
        )

    _SECRET_PATTERNS = [
        re.compile(r'sk-proj-[A-Za-z0-9_-]+'),  # OpenAI project keys
        re.compile(r'sk-[A-Za-z0-9]{20,}'),  # OpenAI legacy keys
        re.compile(r'sk-ant-[A-Za-z0-9_-]+'),  # Anthropic keys
        re.compile(r'AIzaSy[A-Za-z0-9_-]+'),  # Google API keys
        re.compile(r'Bearer\s+[A-Za-z0-9._\-/+=]+', re.IGNORECASE),  # bearer tokens
        re.compile(r'(?:api_key|password|secret|token)\s*[=:]\s*\S+', re.IGNORECASE),  # generic assignments
    ]

    @staticmethod
    def _redact_secrets(text: str) -> str:
        """Redact known credential patterns from text"""
        if not text:
            return text
        for pat in AuditLogger._SECRET_PATTERNS:
            text = pat.sub("[REDACTED]", text)
        return text

    def log_bash_command(
        self,
        command: str,
        exit_code: int = 0,
        output: Optional[str] = None
    ):
        """Log a bash command execution

        Args:
            command: Command that was executed
            exit_code: Exit code from command
            output: Command output (truncated if long)
        """
        command = self._redact_secrets(command)
        truncated_output = self._redact_secrets(output[:500]) if output else None

        self.log_event(
            event_type=AuditEventType.BASH_COMMAND,
            operation="Execute bash command",
            target=command,
            details={"exit_code": exit_code, "output": truncated_output},
            severity=AuditSeverity.WARNING if exit_code != 0 else AuditSeverity.INFO,
            success=exit_code == 0
        )

    def log_api_call(
        self,
        provider: str,
        model: str,
        tokens: int,
        success: bool = True
    ):
        """Log an API call to AI provider

        Args:
            provider: Provider name (gemini, openai, etc.)
            model: Model name
            tokens: Number of tokens used
            success: Whether call succeeded
        """
        self.log_event(
            event_type=AuditEventType.API_CALL,
            operation=f"API call to {provider}",
            target=model,
            details={"tokens": tokens},
            severity=AuditSeverity.INFO,
            success=success
        )

    def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        user: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query audit events

        Args:
            event_type: Filter by event type
            start_time: Start timestamp (ISO format)
            end_time: End timestamp (ISO format)
            user: Filter by user
            limit: Maximum number of results

        Returns:
            List of audit events
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = "SELECT * FROM audit_events WHERE 1=1"
            params = []

            if event_type:
                query += " AND event_type = ?"
                params.append(event_type.value)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            if user:
                query += " AND user = ?"
                params.append(user)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Convert to dicts
            columns = [desc[0] for desc in cursor.description]
            events = [dict(zip(columns, row)) for row in rows]

            conn.close()
            return events

        except Exception as e:
            logger.error(f"Failed to query audit events: {e}")
            return []

    def rotate_if_needed(
        self,
        *,
        now: Optional[datetime] = None,
        max_runtime_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Archive old/excess audit rows without changing the audit table schema."""
        runtime_limit = self.rotation_runtime_seconds if max_runtime_seconds is None else max_runtime_seconds
        deadline = time.monotonic() + max(float(runtime_limit), 0.0)
        archived = 0
        chunks = 0
        vacuum_needed = False

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            while True:
                if runtime_limit is not None and time.monotonic() >= deadline and chunks > 0:
                    break
                rows = self._rotation_chunk(conn, now=now)
                if not rows:
                    break
                self._archive_rows_and_delete(conn, rows)
                archived += len(rows)
                chunks += 1
                vacuum_needed = True

        if vacuum_needed:
            self._vacuum_best_effort()

        return {"archived": archived, "chunks": chunks, "db_path": str(self.db_path)}

    rotate = rotate_if_needed

    def archive(
        self,
        *,
        before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> int:
        """Archive rows older than `before`; mainly used by scheduled rotation/tests."""
        archived = 0
        chunk_limit = max(1, int(limit or self.archive_chunk_size))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            while True:
                where = ""
                params: list[Any] = []
                if before:
                    where = "WHERE timestamp < ?"
                    params.append(before)
                rows = self._fetch_rows(
                    conn,
                    where=where,
                    params=params,
                    limit=chunk_limit,
                )
                if not rows:
                    break
                self._archive_rows_and_delete(conn, rows)
                archived += len(rows)
                if len(rows) < chunk_limit:
                    break
        if archived:
            self._vacuum_best_effort()
        return archived

    def export_range(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> int:
        """Export live DB + archives as JSONL, sorted by timestamp."""
        if not self.enable_export:
            logger.warning("Export is disabled")
            return 0

        rows = list(self.iter_export_rows(start_time=start_time, end_time=end_time))
        if output_path is None:
            for row in rows:
                print(json.dumps(row, sort_keys=True), file=sys.stdout)
            return len(rows)

        output_path = output_path.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True))
                handle.write("\n")
        return len(rows)

    def export_range_to_string(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> str:
        return "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in self.iter_export_rows(start_time=start_time, end_time=end_time)
        )

    def iter_export_rows(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Iterable[Dict[str, Any]]:
        by_id: dict[str, Dict[str, Any]] = {}
        for row in self._iter_archive_rows(start_time=start_time, end_time=end_time):
            event_id = str(row.get("event_id", ""))
            if event_id:
                by_id[event_id] = row

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            where_parts = []
            params: list[Any] = []
            if start_time:
                where_parts.append("timestamp >= ?")
                params.append(start_time)
            if end_time:
                where_parts.append("timestamp <= ?")
                params.append(end_time)
            where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
            for row in self._fetch_rows(conn, where=where, params=params, limit=None):
                by_id[str(row["event_id"])] = row

        yield from sorted(by_id.values(), key=lambda row: (str(row.get("timestamp", "")), str(row.get("event_id", ""))))

    def _rotation_chunk(self, conn: sqlite3.Connection, *, now: Optional[datetime]) -> List[Dict[str, Any]]:
        row_count = int(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])
        if row_count <= 0:
            return []

        age_cutoff = None
        age_count = 0
        if self.max_age_days_live and self.max_age_days_live > 0:
            current = now or datetime.now()
            age_cutoff = (current - timedelta(days=self.max_age_days_live)).isoformat()
            age_count = int(conn.execute(
                "SELECT COUNT(*) FROM audit_events WHERE timestamp < ?",
                (age_cutoff,),
            ).fetchone()[0])

        excess_rows = max(0, row_count - max(int(self.max_rows_live or 0), 0)) if self.max_rows_live else 0
        size_exceeded = self._size_cap_exceeded()
        if age_count <= 0 and excess_rows <= 0 and not size_exceeded:
            return []

        if age_count > 0 and age_cutoff is not None:
            oldest = conn.execute(
                "SELECT timestamp FROM audit_events WHERE timestamp < ? ORDER BY timestamp ASC LIMIT 1",
                (age_cutoff,),
            ).fetchone()
            if oldest is None:
                return []
            month_start, month_end = self._month_bounds(str(oldest["timestamp"]))
            return self._fetch_rows(
                conn,
                where="WHERE timestamp < ? AND timestamp >= ? AND timestamp < ?",
                params=[age_cutoff, month_start, month_end],
                limit=min(self.archive_chunk_size, age_count),
            )

        oldest = conn.execute("SELECT timestamp FROM audit_events ORDER BY timestamp ASC LIMIT 1").fetchone()
        if oldest is None:
            return []
        month_start, month_end = self._month_bounds(str(oldest["timestamp"]))
        limit = min(self.archive_chunk_size, excess_rows) if excess_rows > 0 else self.archive_chunk_size
        return self._fetch_rows(
            conn,
            where="WHERE timestamp >= ? AND timestamp < ?",
            params=[month_start, month_end],
            limit=limit,
        )

    def _fetch_rows(
        self,
        conn: sqlite3.Connection,
        *,
        where: str,
        params: list[Any],
        limit: Optional[int],
    ) -> List[Dict[str, Any]]:
        select_cols = ", ".join(AUDIT_COLUMNS)
        query = f"SELECT rowid AS _rowid, {select_cols} FROM audit_events {where} ORDER BY timestamp ASC, event_id ASC"
        query_params = list(params)
        if limit is not None:
            query += " LIMIT ?"
            query_params.append(max(1, int(limit)))
        rows = conn.execute(query, query_params).fetchall()
        return [dict(row) for row in rows]

    def _archive_rows_and_delete(self, conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        archive_rows = [{key: row.get(key) for key in AUDIT_COLUMNS} for row in rows]
        rowids = [int(row["_rowid"]) for row in rows]
        conn.execute("BEGIN")
        try:
            self._append_archive_atomic(archive_rows)
            conn.executemany("DELETE FROM audit_events WHERE rowid = ?", [(rowid,) for rowid in rowids])
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _append_archive_atomic(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        month = self._archive_month(str(rows[0].get("timestamp", "")))
        if any(self._archive_month(str(row.get("timestamp", ""))) != month for row in rows):
            raise ValueError("Archive chunks must not span months")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        path = self.archive_dir / f"{month}.jsonl.gz"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{month}.", suffix=".jsonl.gz.tmp", dir=self.archive_dir)
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            with gzip.open(tmp_path, "wt", encoding="utf-8") as out:
                if path.exists():
                    with gzip.open(path, "rt", encoding="utf-8") as existing:
                        for line in existing:
                            out.write(line)
                for row in rows:
                    out.write(json.dumps(row, sort_keys=True))
                    out.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(Exception):
                tmp_path.unlink()
            raise

    def _iter_archive_rows(
        self,
        *,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> Iterable[Dict[str, Any]]:
        if not self.archive_dir.exists():
            return
        for path in sorted(self.archive_dir.glob("*.jsonl.gz")):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        timestamp = str(row.get("timestamp", ""))
                        if start_time and timestamp < start_time:
                            continue
                        if end_time and timestamp > end_time:
                            continue
                        yield row
            except Exception as e:
                logger.warning(f"Failed to read audit archive {path}: {e}")

    def _size_cap_exceeded(self) -> bool:
        if not self.max_size_mb or self.max_size_mb <= 0:
            return False
        try:
            return self.db_path.stat().st_size > int(float(self.max_size_mb) * 1024 * 1024)
        except FileNotFoundError:
            return False

    def _vacuum_best_effort(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("VACUUM")
        except Exception as e:
            logger.debug(f"Audit DB vacuum skipped: {e}")

    @staticmethod
    def _archive_month(timestamp: str) -> str:
        if len(timestamp) >= 7:
            return timestamp[:7]
        return datetime.now().strftime("%Y-%m")

    @classmethod
    def _month_bounds(cls, timestamp: str) -> tuple[str, str]:
        month = cls._archive_month(timestamp)
        year, raw_month = month.split("-", 1)
        year_int = int(year)
        month_int = int(raw_month)
        if month_int == 12:
            return month, f"{year_int + 1:04d}-01"
        return month, f"{year_int:04d}-{month_int + 1:02d}"

    def export_to_json(
        self,
        output_path: Path,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ):
        """Export audit log to JSON

        Args:
            output_path: Output file path
            start_time: Start timestamp
            end_time: End timestamp
        """
        if not self.enable_export:
            logger.warning("Export is disabled")
            return

        events = self.query_events(
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )

        try:
            with open(output_path, 'w') as f:
                json.dump({
                    "export_time": datetime.now().isoformat(),
                    "total_events": len(events),
                    "events": events
                }, f, indent=2)

            logger.info(f"Exported {len(events)} audit events to {output_path}")

        except Exception as e:
            logger.error(f"Failed to export audit log: {e}")

    def cleanup_old_logs(self):
        """Remove audit logs older than retention period"""
        from datetime import timedelta

        cutoff_date = (datetime.now() - timedelta(days=self.retention_days)).isoformat()

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM audit_events WHERE timestamp < ?
            """, (cutoff_date,))

            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old audit events")

        except Exception as e:
            logger.error(f"Failed to cleanup old logs: {e}")


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def audit_export(
    since: Optional[str] = None,
    to: Optional[Path | str] = None,
    *,
    until: Optional[str] = None,
    audit_dir: Optional[Path] = None,
) -> str:
    logger_instance = AuditLogger(audit_dir=audit_dir) if audit_dir else get_audit_logger()
    if to is not None:
        logger_instance.export_range(start_time=since, end_time=until, output_path=Path(to))
        return str(to)
    return logger_instance.export_range_to_string(start_time=since, end_time=until)
