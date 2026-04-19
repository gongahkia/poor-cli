"""multi-session manager for parallel independent agent sessions."""

import copy
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from .exceptions import setup_logger, ValidationError

if TYPE_CHECKING:
    from .core import PoorCLICore

logger = setup_logger(__name__)

MAX_SESSIONS_DEFAULT = 8


@dataclass
class SessionState:
    """state for a single agent session."""
    session_id: str
    core: "PoorCLICore"
    label: str = ""
    working_directory: str = ""
    status: str = "active" # active | paused | completed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    branch_name: str = "" # non-empty when branch-per-session is active

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "sessionId": self.session_id,
            "label": self.label,
            "workingDirectory": self.working_directory,
            "status": self.status,
            "createdAt": self.created_at,
        }
        if self.branch_name:
            d["branchName"] = self.branch_name
        return d


class SessionManager:
    """manages multiple independent PoorCLICore instances."""

    def __init__(
        self,
        max_sessions: int = MAX_SESSIONS_DEFAULT,
        config_path: Optional[Path] = None,
        branch_per_session: bool = False,
    ):
        self._sessions: Dict[str, SessionState] = {}
        self._default_session_id: Optional[str] = None
        self._max_sessions = max_sessions
        self._config_path = config_path
        self._permission_callback: Optional[Callable[..., Any]] = None
        self._branch_per_session = branch_per_session
        self._original_branch: str = "" # stashed when branching

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
        branch: bool = False,
    ) -> SessionState:
        """create a new independent session, optionally on its own git branch."""
        if len(self._sessions) >= self._max_sessions:
            raise ValidationError(
                f"max sessions ({self._max_sessions}) reached; destroy one first"
            )
        from .core import PoorCLICore

        sid = f"sess-{uuid.uuid4().hex[:8]}"
        core = PoorCLICore(config_path=self._config_path)
        if self._permission_callback:
            core.permission_callback = self._permission_callback

        branch_name = ""
        use_branch = branch or self._branch_per_session
        if use_branch:
            branch_name = self._create_session_branch(sid, cwd)

        state = SessionState(
            session_id=sid,
            core=core,
            label=label or sid,
            working_directory=cwd or str(Path.cwd()),
            branch_name=branch_name,
        )
        self._sessions[sid] = state
        if make_default or self._default_session_id is None:
            self._default_session_id = sid
        logger.info("session created: %s (%s) branch=%s", sid, label, branch_name or "none")
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
        session = self._sessions[session_id]
        # if session had a branch, switch back to original
        if session.branch_name and self._original_branch:
            self._checkout_branch(self._original_branch, session.working_directory)
        del self._sessions[session_id]
        if self._default_session_id == session_id:
            self._default_session_id = next(iter(self._sessions), None)
        logger.info("session destroyed: %s", session_id)

    def switch_default(self, session_id: str) -> SessionState:
        """switch the default session."""
        if session_id not in self._sessions:
            raise ValidationError(f"unknown session: {session_id}")
        self._default_session_id = session_id
        # if target session has a branch, switch to it
        target = self._sessions[session_id]
        if target.branch_name:
            self._checkout_branch(target.branch_name, target.working_directory)
        return target

    def list_sessions(self) -> List[Dict[str, Any]]:
        """return metadata for all sessions."""
        result = []
        for s in self._sessions.values():
            info = s.to_dict()
            info["isDefault"] = s.session_id == self._default_session_id
            result.append(info)
        return result

    def fork_session(self, source_id: str, label: str = "", copy_history: bool = True) -> SessionState:
        """create a new session forking from source, optionally copying conversation history."""
        if source_id not in self._sessions:
            raise ValidationError(f"unknown session: {source_id}")
        src = self._sessions[source_id]
        new = self.create_session(
            label=label or f"fork-{src.label}",
            cwd=src.working_directory,
        )
        if copy_history and src.core.provider:
            try:
                history = src.core.provider.get_history()
                if history:
                    new.core._fork_history = copy.deepcopy(history)
                    logger.info("forked %d history messages from %s to %s", len(history), source_id, new.session_id)
            except Exception as exc:
                logger.warning("failed to copy history during fork: %s", exc)
        return new

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    # ── git branch helpers ───────────────────────────────────────────────

    def _create_session_branch(self, session_id: str, cwd: Optional[str] = None) -> str:
        """Create a git branch for this session."""
        repo = cwd or str(Path.cwd())
        # save original branch
        if not self._original_branch:
            self._original_branch = self._current_branch(repo)
        branch = f"poor-cli/session/{session_id}"
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch],
                cwd=repo, capture_output=True, text=True, check=True,
            )
            logger.info("created session branch: %s", branch)
            return branch
        except subprocess.CalledProcessError as exc:
            logger.warning("failed to create session branch: %s", exc.stderr.strip())
            return ""

    @staticmethod
    def _checkout_branch(branch: str, cwd: str) -> bool:
        try:
            subprocess.run(
                ["git", "checkout", branch],
                cwd=cwd, capture_output=True, text=True, check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def _current_branch(cwd: str) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=cwd, capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, OSError):
            return "main"
