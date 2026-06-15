from __future__ import annotations

import re
import shlex
from pathlib import Path


class SandboxDenied(RuntimeError):
    pass


NETWORK_COMMANDS = {"curl", "wget", "ssh", "scp", "sftp", "ftp", "nc", "telnet"}
GIT_NETWORK_COMMANDS = {"clone", "fetch", "pull", "push"}
PATH_WRITE_COMMANDS = {"touch", "mkdir", "rm", "rmdir", "cp", "mv"}
REDIRECT_TOKENS = {">", ">>", "1>", "1>>", "2>", "2>>"}
SHELLS = {"bash", "sh", "zsh"}
WRAPPER_COMMANDS = {"env", "command"}
ALLOWLIST_COMMANDS = {"rg", "sed", "python", "python3", "git", "printf", "cat", "ls", "pwd", "true", "false"}


def validate_shell_command(root: Path, command: str) -> None:
    _deny_unsupported_shell(command)
    parts = shlex.split(command)
    if not parts:
        raise SandboxDenied("shell command is empty")
    _deny_wrappers(parts)
    _deny_network(parts)
    _deny_outside_writes(root.resolve(), parts, command)


def _deny_network(parts: list[str]) -> None:
    names = {_command_name(part) for part in parts if part not in {"&&", "||", ";", "|"}}
    if names & NETWORK_COMMANDS:
        raise SandboxDenied("shell network command blocked")
    if parts[0] == "git" and len(parts) > 1 and parts[1] in GIT_NETWORK_COMMANDS:
        raise SandboxDenied("git network command blocked")
    if any("://" in part for part in parts):
        raise SandboxDenied("shell URL argument blocked")


def _deny_outside_writes(root: Path, parts: list[str], command: str) -> None:
    if parts[0] in PATH_WRITE_COMMANDS:
        for value in _path_args(parts[1:]):
            _require_inside(root, value)
    for index, part in enumerate(parts[:-1]):
        if part in REDIRECT_TOKENS:
            _require_inside(root, parts[index + 1])
    for value in _redirect_targets(command):
        _require_inside(root, value)


def _deny_unsupported_shell(command: str) -> None:
    if "$(" in command or "`" in command:
        raise SandboxDenied("shell command substitution blocked")
    if re.search(r"(^|\s)[<>]\(", command):
        raise SandboxDenied("shell process substitution blocked")
    if "<<" in command or "<<<" in command:
        raise SandboxDenied("shell heredoc blocked")
    if re.search(r"^\s*alias\s+\w+=", command):
        raise SandboxDenied("shell alias wrapper blocked")
    if re.search(r"^\s*(function\s+\w+|\w+\s*\(\s*\)\s*\{)", command):
        raise SandboxDenied("shell function wrapper blocked")


def _deny_wrappers(parts: list[str]) -> None:
    if _command_name(parts[0]) in SHELLS and "-c" in parts:
        raise SandboxDenied("shell -c wrapper blocked")
    if parts[0] in WRAPPER_COMMANDS and len(parts) > 1 and _command_name(parts[1]) not in ALLOWLIST_COMMANDS:
        raise SandboxDenied("shell command wrapper blocked")


def _path_args(parts: list[str]) -> list[str]:
    return [part for part in parts if not part.startswith("-") and part not in {"&&", "||", ";", "|"}]


def _require_inside(root: Path, value: str) -> None:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SandboxDenied(f"shell write outside workdir blocked: {value}") from None


def _command_name(value: str) -> str:
    return Path(value).name


def _redirect_targets(command: str) -> list[str]:
    targets = []
    for match in re.finditer(r"(?:^|\s)(?:\d?)(?:>>?|&>)\s*([^\s;&|]+)", command):
        targets.append(match.group(1))
    for match in re.finditer(r"(?:\S)(?:\d?)(?:>>?|&>)([^\s;&|]+)", command):
        targets.append(match.group(1))
    return [target for target in targets if target not in {"&1", "&2"}]
