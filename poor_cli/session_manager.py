"""multi-session manager for parallel independent agent sessions."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from .core import PoorCLICore
from .exceptions import setup_logger, ValidationError

logger = setup_logger(__name__)

MAX_SESSIONS_DEFAULT = 8


@dataclass
class SessionState:
    """state for a single agent session."""
    session_id: str
    core: PoorCLICore
    label: str = ""
    working_directory: str = ""
    status: str = "active" # active | paused | completed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "label": self.label,
            "workingDirectory": self.working_directory,
            "status": self.status,
            "createdAt": self.created_at,
        }


class SessionManager:
    """manages multiple independent PoorCLICore instances."""

    def __init__(
        self,
        max_sessions: int = MAX_SESSIONS_DEFAULT,
        config_path: Optional[Path] = None,
    ):
        self._sessions: Dict[str, SessionState] = {}
        self._default_session_id: Optional[str] = None
        self._max_sessions = max_sessions
        self._config_path = config_path
        self._permission_callback: Optional[Callable[..., Any]] = None

    @property
    def default_session(self) -> Optional[SessionState]:
        if self._default_session_id and self._default_session_id in self._sessions:
            return self._sessions[self._default_session_id]
        return None

    def set_permission_callback(self, cb: Optional[Callable[..., Any]]) -> None:
        """set permission callback applied to all sessions."""
        self._permission_callback = cb
        for s in self._sessions.values():
            s.core.permission_callback = cb

    def create_session(
        self,
        label: str = "",
        cwd: Optional[str] = None,
        make_default: bool = False,
    ) -> SessionState:
        """create a new independent session."""
        if len(self._sessions) >= self._max_sessions:
            raise ValidationError(
                f"max sessions ({self._max_sessions}) reached; destroy one first"
            )
        sid = f"sess-{uuid.uuid4().hex[:8]}"
        core = PoorCLICore(config_path=self._config_path)
        if self._permission_callback:
            core.permission_callback = self._permission_callback
        state = SessionState(
            session_id=sid,
            core=core,
            label=label or sid,
            working_directory=cwd or str(Path.cwd()),
        )
        self._sessions[sid] = state
        if make_default or self._default_session_id is None:
            self._default_session_id = sid
        logger.info("session created: %s (%s)", sid, label)
        return state

    def get_session(self, session_id: Optional[str] = None) -> SessionState:
        """resolve a session by id, falling back to default."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        if self._default_session_id and self._default_session_id in self._sessions:
            return self._sessions[self._default_session_id]
        raise ValidationError("no active session")

    def destroy_session(self, session_id: str) -> None:
        """destroy a session and release resources."""
        if session_id not in self._sessions:
            raise ValidationError(f"unknown session: {session_id}")
        del self._sessions[session_id]
        if self._default_session_id == session_id:
            self._default_session_id = next(iter(self._sessions), None)
        logger.info("session destroyed: %s", session_id)

    def switch_default(self, session_id: str) -> SessionState:
        """switch the default session."""
        if session_id not in self._sessions:
            raise ValidationError(f"unknown session: {session_id}")
        self._default_session_id = session_id
        return self._sessions[session_id]

    def list_sessions(self) -> List[Dict[str, Any]]:
        """return metadata for all sessions."""
        result = []
        for s in self._sessions.values():
            info = s.to_dict()
            info["isDefault"] = s.session_id == self._default_session_id
            result.append(info)
        return result

    def fork_session(self, source_id: str, label: str = "") -> SessionState:
        """create a new session copying config from source (not history)."""
        if source_id not in self._sessions:
            raise ValidationError(f"unknown session: {source_id}")
        src = self._sessions[source_id]
        new = self.create_session(
            label=label or f"fork-{src.label}",
            cwd=src.working_directory,
        )
        return new

    @property
    def session_count(self) -> int:
        return len(self._sessions)
