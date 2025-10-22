"""
Conversation history management for poor-cli

Handles storing, retrieving, and managing conversation history with
token counting and persistence.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from poor_cli.exceptions import FileOperationError, setup_logger

logger = setup_logger(__name__)


@dataclass
class Message:
    """Represents a single message in conversation history"""
    role: str  # 'user', 'model', 'tool'
    content: str
    timestamp: str
    tokens: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create message from dictionary"""
        return cls(**data)


@dataclass
class Session:
    """Represents a conversation session"""
    session_id: str
    started_at: str
    ended_at: Optional[str] = None
    messages: List[Message] = None
    total_tokens: int = 0
    model: str = "gemini-2.0-flash-exp"

    def __post_init__(self):
        if self.messages is None:
            self.messages = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary"""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "messages": [msg.to_dict() for msg in self.messages],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """Create session from dictionary"""
        messages = [Message.from_dict(msg) for msg in data.pop("messages", [])]
        return cls(messages=messages, **data)


class TokenCounter:
    """Estimates token count for text

    This is a rough approximation. For accurate counting, use the
    model-specific tokenizer.
    """

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for text

        Uses a simple heuristic: ~4 characters per token on average

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        # Simple estimation: 4 chars ≈ 1 token
        # This is a rough approximation that works reasonably well for English
        return max(1, len(text) // 4)

    @staticmethod
    def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
        """Estimate total tokens for list of messages

        Args:
            messages: List of message dictionaries

        Returns:
            Total estimated tokens
        """
        total = 0
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "") or msg.get("parts", [""])[0]
            else:
                content = str(msg)

            total += TokenCounter.estimate_tokens(str(content))

        # Add overhead for message structure (~10 tokens per message)
        total += len(messages) * 10

        return total


class HistoryManager:
    """Manages conversation history with persistence"""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize history manager

        Args:
            db_path: Path to SQLite database (defaults to ~/.poor-cli/history.db)
        """
        default_dir = Path.home() / ".poor-cli"
        default_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path or (default_dir / "history.db")
        self.current_session: Optional[Session] = None
        self._init_database()

    def _init_database(self) -> None:
        """Initialize SQLite database with required tables"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    total_tokens INTEGER DEFAULT 0,
                    model TEXT DEFAULT 'gemini-2.0-flash-exp'
                )
            """)

            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tokens INTEGER,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            # Index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id)
            """)

            conn.commit()
            conn.close()
            logger.info(f"History database initialized at {self.db_path}")

        except Exception as e:
            raise FileOperationError(f"Failed to initialize history database: {e}")

    def start_session(self, model: str = "gemini-2.0-flash-exp") -> Session:
        """Start a new conversation session

        Args:
            model: Model name for this session

        Returns:
            New session object
        """
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        started_at = datetime.now().isoformat()

        self.current_session = Session(
            session_id=session_id,
            started_at=started_at,
            model=model
        )

        # Save session to database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (session_id, started_at, model)
                VALUES (?, ?, ?)
            """, (session_id, started_at, model))
            conn.commit()
            conn.close()

            logger.info(f"Started new session: {session_id}")

        except Exception as e:
            logger.error(f"Failed to save session to database: {e}")

        return self.current_session

    def end_session(self) -> None:
        """End the current session"""
        if not self.current_session:
            return

        ended_at = datetime.now().isoformat()
        self.current_session.ended_at = ended_at

        # Update database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions
                SET ended_at = ?, total_tokens = ?
                WHERE session_id = ?
            """, (ended_at, self.current_session.total_tokens,
                  self.current_session.session_id))
            conn.commit()
            conn.close()

            logger.info(f"Ended session: {self.current_session.session_id}")

        except Exception as e:
            logger.error(f"Failed to update session in database: {e}")

        self.current_session = None

    def add_message(self, role: str, content: str,
                   metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Add a message to current session

        Args:
            role: Message role (user, model, tool)
            content: Message content
            metadata: Optional metadata

        Returns:
            Created message object
        """
        if not self.current_session:
            self.start_session()

        timestamp = datetime.now().isoformat()
        tokens = TokenCounter.estimate_tokens(content)

        message = Message(
            role=role,
            content=content,
            timestamp=timestamp,
            tokens=tokens,
            metadata=metadata
        )

        self.current_session.messages.append(message)
        self.current_session.total_tokens += tokens

        # Save to database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (session_id, role, content, timestamp, tokens, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                self.current_session.session_id,
                role,
                content,
                timestamp,
                tokens,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to save message to database: {e}")

        return message

    def get_recent_messages(self, limit: Optional[int] = None) -> List[Message]:
        """Get recent messages from current session

        Args:
            limit: Maximum number of messages to return

        Returns:
            List of recent messages
        """
        if not self.current_session:
            return []

        messages = self.current_session.messages
        if limit:
            return messages[-limit:]
        return messages

    def get_session_history(self, session_id: str) -> Optional[Session]:
        """Load a session from database

        Args:
            session_id: Session ID to load

        Returns:
            Session object or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get session info
            cursor.execute("""
                SELECT session_id, started_at, ended_at, total_tokens, model
                FROM sessions
                WHERE session_id = ?
            """, (session_id,))

            row = cursor.fetchone()
            if not row:
                conn.close()
                return None

            session = Session(
                session_id=row[0],
                started_at=row[1],
                ended_at=row[2],
                total_tokens=row[3],
                model=row[4]
            )

            # Get messages
            cursor.execute("""
                SELECT role, content, timestamp, tokens, metadata
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
            """, (session_id,))

            for row in cursor.fetchall():
                metadata = json.loads(row[4]) if row[4] else None
                message = Message(
                    role=row[0],
                    content=row[1],
                    timestamp=row[2],
                    tokens=row[3],
                    metadata=metadata
                )
                session.messages.append(message)

            conn.close()
            logger.info(f"Loaded session {session_id} with {len(session.messages)} messages")
            return session

        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return None

    def list_sessions(self, limit: int = 10) -> List[Tuple[str, str, int]]:
        """List recent sessions

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of tuples (session_id, started_at, message_count)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT s.session_id, s.started_at, COUNT(m.id) as message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.started_at DESC
                LIMIT ?
            """, (limit,))

            sessions = cursor.fetchall()
            conn.close()

            return sessions

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def prune_history(self, max_tokens: int) -> int:
        """Remove oldest messages to stay within token limit

        Args:
            max_tokens: Maximum total tokens to keep

        Returns:
            Number of messages removed
        """
        if not self.current_session:
            return 0

        removed = 0
        while (self.current_session.total_tokens > max_tokens and
               len(self.current_session.messages) > 1):
            # Remove oldest message (keep at least 1)
            removed_msg = self.current_session.messages.pop(0)
            self.current_session.total_tokens -= removed_msg.tokens or 0
            removed += 1

        if removed > 0:
            logger.info(f"Pruned {removed} messages to stay within {max_tokens} tokens")

        return removed

    def clear_current_session(self) -> None:
        """Clear messages from current session"""
        if self.current_session:
            self.current_session.messages.clear()
            self.current_session.total_tokens = 0
            logger.info("Cleared current session messages")

    def export_session(self, session_id: str, output_path: Path) -> None:
        """Export session to JSON file

        Args:
            session_id: Session to export
            output_path: Output file path
        """
        session = self.get_session_history(session_id)
        if not session:
            raise FileOperationError(f"Session not found: {session_id}")

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2)

            logger.info(f"Exported session {session_id} to {output_path}")

        except Exception as e:
            raise FileOperationError(f"Failed to export session: {e}")

    def get_total_tokens(self) -> int:
        """Get total token count for current session

        Returns:
            Total tokens in current session
        """
        if not self.current_session:
            return 0
        return self.current_session.total_tokens

    def get_message_count(self) -> int:
        """Get message count for current session

        Returns:
            Number of messages in current session
        """
        if not self.current_session:
            return 0
        return len(self.current_session.messages)
