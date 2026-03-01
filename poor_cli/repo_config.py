"""
Repository-level configuration and history management for poor-cli

Manages .poor-cli directory in the current repository for:
- Local chat history
- Repo-specific preferences
- Permission settings
"""

import os
import json
import tempfile
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Iterator, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict, field

from .config import PermissionMode
from .exceptions import ConfigurationError, FileOperationError, setup_logger

logger = setup_logger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None


@dataclass
class RepoPreferences:
    """Repository-level preferences"""
    permission_mode: PermissionMode = PermissionMode.PROMPT

    # Auto-approve settings (per repo)
    auto_approve_read: bool = False
    auto_approve_write: bool = False
    auto_approve_edit: bool = False
    auto_approve_bash: bool = False

    # Safe command patterns that don't need approval
    safe_bash_commands: List[str] = field(default_factory=lambda: [
        "pwd", "ls", "echo", "cat", "head", "tail",
        "grep", "find", "which", "whoami", "date"
    ])

    # Retention controls
    max_sessions: int = 100
    max_messages_per_session: int = 200

    # Tracking
    created_at: str = ""
    updated_at: str = ""
    total_sessions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["permission_mode"] = self.permission_mode.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RepoPreferences':
        """Create from dictionary"""
        data = data.copy()
        raw_mode = data.get("permission_mode", PermissionMode.PROMPT)

        if isinstance(raw_mode, PermissionMode):
            mode = raw_mode
        elif isinstance(raw_mode, str):
            try:
                mode = PermissionMode(raw_mode)
            except ValueError as e:
                raise ConfigurationError(
                    "Invalid preferences.permission_mode value. "
                    "Expected one of: prompt, auto-safe, danger-full-access."
                ) from e
        else:
            raise ConfigurationError(
                "Invalid preferences.permission_mode type. Expected a string."
            )

        max_sessions = data.get("max_sessions", 100)
        if int(max_sessions) < 1:
            raise ConfigurationError("preferences.max_sessions must be at least 1")

        max_messages = data.get("max_messages_per_session", 200)
        if int(max_messages) < 1:
            raise ConfigurationError("preferences.max_messages_per_session must be at least 1")

        data["permission_mode"] = mode
        return cls(**data)


@dataclass
class ChatMessage:
    """Single chat message"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class ChatSession:
    """Single chat session"""
    session_id: str
    started_at: str
    ended_at: Optional[str] = None
    model: str = "gemini-2.5-flash"
    messages: List[ChatMessage] = field(default_factory=list)
    total_tokens_estimate: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "model": self.model,
            "messages": [msg.to_dict() for msg in self.messages],
            "total_tokens_estimate": self.total_tokens_estimate
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatSession':
        """Create from dictionary"""
        messages = [ChatMessage.from_dict(msg) for msg in data.get("messages", [])]
        return cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            ended_at=data.get("ended_at"),
            model=data.get("model", "gemini-2.5-flash"),
            messages=messages,
            total_tokens_estimate=data.get("total_tokens_estimate", 0)
        )


class RepoConfig:
    """Manages repository-level configuration and history"""

    REPO_DIR_NAME = ".poor-cli"
    HISTORY_FILE = "history.json"
    HISTORY_BACKUP_DIR = "history_backups"
    HISTORY_LOCK_FILE = "history.lock"
    HISTORY_MIGRATION_MARKER_FILE = "history_migration_marker.json"
    PREFERENCES_FILE = "preferences.json"

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        enable_legacy_history_migration: bool = True,
    ):
        """
        Initialize repo config

        Args:
            repo_path: Path to repository (defaults to current directory)
            enable_legacy_history_migration: Import ~/.poor-cli/history.db once when enabled.
        """
        self.repo_path = repo_path or Path.cwd()
        self.enable_legacy_history_migration = enable_legacy_history_migration
        self.config_dir = self.repo_path / self.REPO_DIR_NAME
        self.history_file = self.config_dir / self.HISTORY_FILE
        self.history_backup_dir = self.config_dir / self.HISTORY_BACKUP_DIR
        self.history_lock_file = self.config_dir / self.HISTORY_LOCK_FILE
        self.history_migration_marker_file = self.config_dir / self.HISTORY_MIGRATION_MARKER_FILE
        self.preferences_file = self.config_dir / self.PREFERENCES_FILE

        # In-memory state
        self.preferences: RepoPreferences = RepoPreferences()
        self.sessions: List[ChatSession] = []
        self.current_session: Optional[ChatSession] = None

        # Initialize
        self._ensure_config_dir()
        self._load_preferences()
        self._load_history()
        if self.enable_legacy_history_migration:
            self._maybe_migrate_legacy_history()

    def _ensure_config_dir(self) -> None:
        """Create .poor-cli directory if it doesn't exist"""
        try:
            self.config_dir.mkdir(exist_ok=True)
            self.history_backup_dir.mkdir(exist_ok=True)

            # Create .gitignore to exclude sensitive data
            gitignore_path = self.config_dir / ".gitignore"
            if not gitignore_path.exists():
                with open(gitignore_path, 'w') as f:
                    f.write("# Ignore chat history (may contain sensitive info)\n")
                    f.write("history.json\n")
                    f.write("# Keep preferences (can be committed)\n")
                    f.write("!preferences.json\n")

            logger.info(f"Repo config directory ensured at {self.config_dir}")
        except Exception as e:
            logger.error(f"Failed to create config directory: {e}")
            raise FileOperationError(f"Failed to create {self.REPO_DIR_NAME} directory", str(e))

    def _load_preferences(self) -> None:
        """Load preferences from file"""
        try:
            if self.preferences_file.exists():
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.preferences = RepoPreferences.from_dict(data)
                logger.info(f"Loaded preferences from {self.preferences_file}")
            else:
                # Create default preferences
                self.preferences = RepoPreferences(
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat()
                )
                self._save_preferences()
                logger.info("Created default preferences")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in preferences file: {e}")
            raise ConfigurationError("Invalid preferences file format")
        except Exception as e:
            logger.error(f"Failed to load preferences: {e}")
            raise FileOperationError("Failed to load preferences", str(e))

    def _save_preferences(self) -> None:
        """Save preferences to file"""
        try:
            self.preferences.updated_at = datetime.now().isoformat()
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self.preferences.to_dict(), f, indent=2)
            logger.info(f"Saved preferences to {self.preferences_file}")
        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")
            raise FileOperationError("Failed to save preferences", str(e))

    def _load_history(self) -> None:
        """Load chat history from file"""
        try:
            if not self.history_file.exists():
                self.sessions = []
                self._save_history()
                logger.info("Created new history file")
                return

            with self._history_file_lock(exclusive=False):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.sessions = [ChatSession.from_dict(session) for session in data.get("sessions", [])]
                logger.info(f"Loaded {len(self.sessions)} sessions from history")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in history file: {e}")
            if self._restore_history_from_backup():
                logger.warning("Recovered corrupted history from backup snapshot")
                return
            raise ConfigurationError("Invalid history file format")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            raise FileOperationError("Failed to load history", str(e))

    def _save_history(self) -> None:
        """Save chat history to file"""
        with self._history_file_lock(exclusive=True):
            temp_path: Optional[str] = None
            try:
                self._apply_retention_limits()
                data = {
                    "sessions": [session.to_dict() for session in self.sessions],
                    "total_sessions": len(self.sessions),
                    "last_updated": datetime.now().isoformat()
                }
                fd, temp_path = tempfile.mkstemp(
                    prefix=f"{self.HISTORY_FILE}.",
                    suffix=".tmp",
                    dir=self.config_dir,
                )
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, self.history_file)
                self._write_history_backup()
                logger.debug(f"Saved {len(self.sessions)} sessions to history")
            except Exception as e:
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                logger.error(f"Failed to save history: {e}")
                raise FileOperationError("Failed to save history", str(e))

    def _write_history_backup(self) -> None:
        """Persist a timestamped backup snapshot of history."""
        try:
            self.history_backup_dir.mkdir(exist_ok=True)
            backup_name = f"history-{datetime.now().strftime('%Y%m%d%H%M%S%f')}.json"
            backup_path = self.history_backup_dir / backup_name
            shutil.copy2(self.history_file, backup_path)
        except Exception as e:
            logger.warning(f"Failed to create history backup: {e}")

    def _restore_history_from_backup(self) -> bool:
        """Restore history from the latest valid backup snapshot."""
        if not self.history_backup_dir.exists():
            return False

        backup_files = sorted(
            self.history_backup_dir.glob("history-*.json"),
            reverse=True,
        )
        for backup_file in backup_files:
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                recovered_sessions = [
                    ChatSession.from_dict(session)
                    for session in data.get("sessions", [])
                ]
            except Exception as e:
                logger.warning(f"Skipping invalid history backup {backup_file}: {e}")
                continue

            temp_path: Optional[str] = None
            try:
                with self._history_file_lock(exclusive=True):
                    fd, temp_path = tempfile.mkstemp(
                        prefix=f"{self.HISTORY_FILE}.",
                        suffix=".tmp",
                        dir=self.config_dir,
                    )
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(temp_path, self.history_file)
                self.sessions = recovered_sessions
                logger.warning(f"Restored history from backup snapshot: {backup_file.name}")
                return True
            except Exception as e:
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                logger.error(f"Failed to restore history backup {backup_file}: {e}")
                return False

        return False

    def _maybe_migrate_legacy_history(self) -> None:
        """One-time import of legacy ~/.poor-cli/history.db into repo history."""
        if self.history_migration_marker_file.exists():
            return

        legacy_db_path = Path.home() / ".poor-cli" / "history.db"
        marker_payload: Dict[str, Any] = {
            "ran_at": datetime.now().isoformat(),
            "legacy_db_path": str(legacy_db_path),
            "status": "source_missing",
            "migrated_sessions": 0,
        }

        try:
            if legacy_db_path.exists():
                migrated_sessions = self._migrate_legacy_history_db(legacy_db_path)
                marker_payload["status"] = "migrated" if migrated_sessions else "no_new_data"
                marker_payload["migrated_sessions"] = migrated_sessions
            self._write_migration_marker(marker_payload)
        except Exception as e:
            marker_payload["status"] = "failed"
            marker_payload["error"] = str(e)
            self._write_migration_marker(marker_payload)
            logger.warning(f"Legacy history migration failed: {e}")

    def _migrate_legacy_history_db(self, legacy_db_path: Path) -> int:
        """Import sessions/messages from legacy SQLite history database."""
        existing_session_ids = {session.session_id for session in self.sessions}
        migrated_sessions = 0

        conn = sqlite3.connect(legacy_db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, started_at, ended_at, model
                FROM sessions
                ORDER BY started_at ASC
                """
            )
            session_rows = cursor.fetchall()

            for session_id, started_at, ended_at, model in session_rows:
                if session_id in existing_session_ids:
                    continue

                cursor.execute(
                    """
                    SELECT role, content, timestamp
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id ASC
                    """,
                    (session_id,),
                )
                message_rows = cursor.fetchall()

                messages: List[ChatMessage] = []
                total_tokens_estimate = 0
                for role, content, timestamp in message_rows:
                    text = content if isinstance(content, str) else str(content)
                    normalized_role = "assistant" if role in {"model", "assistant"} else str(role)
                    messages.append(
                        ChatMessage(
                            role=normalized_role,
                            content=text,
                            timestamp=timestamp or datetime.now().isoformat(),
                        )
                    )
                    total_tokens_estimate += len(text) // 4

                self.sessions.append(
                    ChatSession(
                        session_id=str(session_id),
                        started_at=started_at or datetime.now().isoformat(),
                        ended_at=ended_at,
                        model=model or "gemini-2.5-flash",
                        messages=messages,
                        total_tokens_estimate=total_tokens_estimate,
                    )
                )
                existing_session_ids.add(str(session_id))
                migrated_sessions += 1
        finally:
            conn.close()

        if migrated_sessions:
            self._save_history()
            logger.info(f"Migrated {migrated_sessions} legacy sessions from {legacy_db_path}")

        return migrated_sessions

    def _write_migration_marker(self, marker_payload: Dict[str, Any]) -> None:
        """Persist migration status marker so migration runs only once."""
        try:
            with open(self.history_migration_marker_file, 'w', encoding='utf-8') as f:
                json.dump(marker_payload, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist history migration marker: {e}")

    @contextmanager
    def _history_file_lock(self, exclusive: bool) -> Iterator[None]:
        """Synchronize history file access across concurrent processes."""
        self.history_lock_file.touch(exist_ok=True)

        if fcntl is None:  # pragma: no cover - non-Unix fallback
            yield
            return

        lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        with open(self.history_lock_file, 'a+', encoding='utf-8') as lock_file:
            fcntl.flock(lock_file.fileno(), lock_mode)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def start_session(self, model: str = "gemini-2.5-flash") -> ChatSession:
        """Start a new chat session"""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_session = ChatSession(
            session_id=session_id,
            started_at=datetime.now().isoformat(),
            model=model
        )
        logger.info(f"Started new session: {session_id}")
        return self.current_session

    def end_session(self) -> None:
        """End the current session"""
        if self.current_session:
            self.current_session.ended_at = datetime.now().isoformat()
            self.sessions.append(self.current_session)
            self._apply_retention_limits()
            self.preferences.total_sessions += 1
            self._save_history()
            self._save_preferences()
            logger.info(f"Ended session: {self.current_session.session_id}")
            self.current_session = None

    def add_message(self, role: str, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        """Add a message to current session"""
        if not self.current_session:
            logger.warning("No active session, creating new one")
            self.start_session()

        message = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            tool_calls=tool_calls
        )
        self.current_session.messages.append(message)

        # Estimate tokens (rough: ~4 chars per token)
        self.current_session.total_tokens_estimate += len(content) // 4
        self._apply_retention_limits()

        # Auto-save after each message
        self._save_history()
        logger.debug(f"Added {role} message to session")

    def _apply_retention_limits(self) -> None:
        """Prune sessions/messages to configured retention limits."""
        max_messages = max(int(self.preferences.max_messages_per_session), 1)
        max_sessions = max(int(self.preferences.max_sessions), 1)

        for session in self.sessions:
            if len(session.messages) > max_messages:
                session.messages = session.messages[-max_messages:]
                self._recalculate_token_estimate(session)

        if self.current_session and len(self.current_session.messages) > max_messages:
            self.current_session.messages = self.current_session.messages[-max_messages:]
            self._recalculate_token_estimate(self.current_session)

        if len(self.sessions) > max_sessions:
            self.sessions = sorted(self.sessions, key=lambda session: session.started_at)[-max_sessions:]

    @staticmethod
    def _recalculate_token_estimate(session: ChatSession) -> None:
        """Recompute token estimate after message pruning."""
        session.total_tokens_estimate = sum(len(msg.content) // 4 for msg in session.messages)

    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about current session"""
        if not self.current_session:
            return {}

        return {
            "session_id": self.current_session.session_id,
            "started_at": self.current_session.started_at,
            "message_count": len(self.current_session.messages),
            "tokens_estimate": self.current_session.total_tokens_estimate,
            "model": self.current_session.model
        }

    def list_sessions(self, limit: int = 10) -> List[ChatSession]:
        """List recent sessions, including active session first when present."""
        completed_sessions = sorted(
            self.sessions,
            key=lambda session: session.started_at,
            reverse=True,
        )
        ordered_sessions = list(completed_sessions)
        if self.current_session:
            ordered_sessions.insert(0, self.current_session)
        return ordered_sessions[:limit]

    def get_all_sessions_stats(self) -> Dict[str, Any]:
        """Get statistics about all sessions"""
        total_messages = sum(len(s.messages) for s in self.sessions)
        if self.current_session:
            total_messages += len(self.current_session.messages)

        total_tokens = sum(s.total_tokens_estimate for s in self.sessions)
        if self.current_session:
            total_tokens += self.current_session.total_tokens_estimate

        return {
            "total_sessions": len(self.sessions) + (1 if self.current_session else 0),
            "total_messages": total_messages,
            "total_tokens_estimate": total_tokens,
            "repo_path": str(self.repo_path)
        }

    def update_preference(self, key: str, value: Any) -> None:
        """Update a preference value"""
        if not hasattr(self.preferences, key):
            raise ConfigurationError(f"Unknown preference: {key}")

        setattr(self.preferences, key, value)
        self._save_preferences()
        logger.info(f"Updated preference: {key} = {value}")

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a preference value"""
        return getattr(self.preferences, key, default)

    def should_auto_approve(self, operation: str) -> bool:
        """Check if operation should be auto-approved"""
        pref_map = {
            "read": "auto_approve_read",
            "write": "auto_approve_write",
            "edit": "auto_approve_edit",
            "bash": "auto_approve_bash"
        }
        pref_key = pref_map.get(operation.lower())
        if pref_key:
            return getattr(self.preferences, pref_key, False)
        return False

    def export_history(self, output_file: Path) -> None:
        """Export history to a different file"""
        try:
            data = {
                "sessions": [session.to_dict() for session in self.sessions],
                "preferences": self.preferences.to_dict(),
                "exported_at": datetime.now().isoformat(),
                "repo_path": str(self.repo_path)
            }
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Exported history to {output_file}")
        except Exception as e:
            raise FileOperationError(f"Failed to export history", str(e))

    def clear_history(self) -> None:
        """Clear all chat history"""
        self.sessions = []
        if self.current_session:
            self.current_session.messages = []
        self._save_history()
        logger.info("Cleared chat history")

    def clear_current_session(self) -> None:
        """Clear only the active session messages."""
        if not self.current_session:
            return
        self.current_session.messages = []
        self.current_session.total_tokens_estimate = 0
        self._save_history()
        logger.info("Cleared current repo session messages")

    def get_recent_messages(self, count: int = 10) -> List[ChatMessage]:
        """Get recent messages from current session"""
        if not self.current_session:
            return []
        return self.current_session.messages[-count:]


# Global repo config instance
_repo_config: Optional[RepoConfig] = None


def get_repo_config(
    repo_path: Optional[Path] = None,
    enable_legacy_history_migration: bool = True,
) -> RepoConfig:
    """Get global repo config instance"""
    global _repo_config
    if (
        _repo_config is None
        or (repo_path and repo_path != _repo_config.repo_path)
        or _repo_config.enable_legacy_history_migration != enable_legacy_history_migration
    ):
        _repo_config = RepoConfig(
            repo_path=repo_path,
            enable_legacy_history_migration=enable_legacy_history_migration,
        )
    return _repo_config
