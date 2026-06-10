import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)

RTK_COMMANDS = frozenset({
    "git", "gh", "cargo", "npm", "pnpm", "yarn", "pytest", "ruff",
    "docker", "kubectl", "aws", "curl", "ls", "cat", "grep", "find",
    "eslint", "prettier", "tsc", "go", "make", "cmake",
})
_SHELL_OPERATORS = ("&&", "||", ";", "|", "\n", "\r")
_missing_warning_emitted = False


@dataclass(frozen=True)
class RTKState:
    enabled: bool = True
    tee_on_failure: bool = True
    binary_path: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.binary_path is not None


def detect_rtk(enabled: bool = True, tee_on_failure: bool = True) -> RTKState:
    global _missing_warning_emitted
    binary_path = shutil.which("rtk") if enabled else None
    if enabled and binary_path is None and not _missing_warning_emitted:
        logger.warning("rtk enabled but not found on PATH; install with: brew install rtk")
        _missing_warning_emitted = True
    return RTKState(
        enabled=enabled,
        tee_on_failure=tee_on_failure,
        binary_path=binary_path,
    )


def command_prefix(command: str) -> Optional[str]:
    stripped = command.strip()
    if not stripped or any(op in stripped for op in _SHELL_OPERATORS):
        return None
    try:
        parts = shlex.split(stripped, posix=True)
    except ValueError:
        return None
    if not parts:
        return None
    first = Path(parts[0]).name
    if first == "rtk":
        return None
    return first


def is_rtk_supported(command: str) -> bool:
    prefix = command_prefix(command)
    return prefix in RTK_COMMANDS if prefix else False


def wrap_shell_command(command: str, state: RTKState) -> str:
    if not state.enabled or not state.available or not is_rtk_supported(command):
        return command
    return f"{shlex.quote(state.binary_path or 'rtk')} {command}"
