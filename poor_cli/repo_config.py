"""
Repository-level configuration and history management for poor-cli

Manages .poor-cli directory in the current repository for:
- Local chat history
- Repo-specific preferences
- Permission settings
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict, field

from .exceptions import ConfigurationError, FileOperationError, setup_logger

logger = setup_logger(__name__)


@dataclass
class RepoPreferences:
    """Repository-level preferences"""
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

    # Tracking
    created_at: str = ""
    updated_at: str = ""
    total_sessions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RepoPreferences':
        """Create from dictionary"""
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
    PREFERENCES_FILE = "preferences.json"

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize repo config

        Args:
            repo_path: Path to repository (defaults to current directory)
        """
        self.repo_path = repo_path or Path.cwd()
        self.config_dir = self.repo_path / self.REPO_DIR_NAME
        self.history_file = self.config_dir / self.HISTORY_FILE
        self.preferences_file = self.config_dir / self.PREFERENCES_FILE

        # In-memory state
        self.preferences: RepoPreferences = RepoPreferences()
        self.sessions: List[ChatSession] = []
        self.current_session: Optional[ChatSession] = None

        # Initialize
        self._ensure_config_dir()
        self._load_preferences()
        self._load_history()

    def _ensure_config_dir(self) -> None:
        """Create .poor-cli directory if it doesn't exist"""
        try:
            self.config_dir.mkdir(exist_ok=True)

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
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.sessions = [ChatSession.from_dict(session) for session in data.get("sessions", [])]
                logger.info(f"Loaded {len(self.sessions)} sessions from history")
            else:
                self.sessions = []
                self._save_history()
                logger.info("Created new history file")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in history file: {e}")
            raise ConfigurationError("Invalid history file format")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            raise FileOperationError("Failed to load history", str(e))

    def _save_history(self) -> None:
        """Save chat history to file"""
        try:
            data = {
                "sessions": [session.to_dict() for session in self.sessions],
                "total_sessions": len(self.sessions),
                "last_updated": datetime.now().isoformat()
            }
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self.sessions)} sessions to history")
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
            raise FileOperationError("Failed to save history", str(e))

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

        # Auto-save after each message
        self._save_history()
        logger.debug(f"Added {role} message to session")

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

    def get_recent_messages(self, count: int = 10) -> List[ChatMessage]:
        """Get recent messages from current session"""
        if not self.current_session:
            return []
        return self.current_session.messages[-count:]


# Global repo config instance
_repo_config: Optional[RepoConfig] = None


def get_repo_config(repo_path: Optional[Path] = None) -> RepoConfig:
    """Get global repo config instance"""
    global _repo_config
    if _repo_config is None or (repo_path and repo_path != _repo_config.repo_path):
        _repo_config = RepoConfig(repo_path)
    return _repo_config
