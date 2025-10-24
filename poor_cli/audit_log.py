"""
Audit logging framework for poor-cli

Comprehensive logging of all file operations, bash commands, and API calls
for security and compliance purposes.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


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
        retention_days: int = 90
    ):
        """Initialize audit logger

        Args:
            audit_dir: Directory for audit logs (defaults to ~/.poor-cli/audit)
            enable_export: Enable JSON export functionality
            retention_days: Number of days to retain audit logs
        """
        self.audit_dir = audit_dir or (Path.home() / ".poor-cli" / "audit")
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.audit_dir / "audit.db"
        self.enable_export = enable_export
        self.retention_days = retention_days

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
        import hashlib

        # Generate event ID
        event_id = hashlib.sha256(
            f"{datetime.now().isoformat()}{operation}{target}".encode()
        ).hexdigest()[:16]

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
        try:
            conn = sqlite3.connect(self.db_path)
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
            conn.close()

            logger.debug(f"Logged audit event: {event_type.value} - {operation}")

        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

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
        # Truncate output if too long
        truncated_output = output[:500] if output else None

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
