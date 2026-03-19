"""Infer effective capabilities and mutation targets for shell commands."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


FILESYSTEM_WRITE = "filesystem:write"
NETWORK_ACCESS = "network:access"
GIT_READ = "git:read"
GIT_WRITE = "git:write"

_NETWORK_COMMANDS = {"curl", "wget"}
_GIT_NETWORK_SUBCOMMANDS = {"push", "pull", "fetch", "clone", "ls-remote"}
_GIT_WRITE_SUBCOMMANDS = {
    "add",
    "am",
    "apply",
    "branch",
    "checkout",
    "cherry-pick",
    "commit",
    "merge",
    "mv",
    "push",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "switch",
    "tag",
}
_WRITE_COMMANDS = {"cp", "mkdir", "mv", "rm", "touch", "truncate"}
_REDIRECT_TOKENS = {">", ">>", "1>", "1>>", "2>", "2>>"}


@dataclass(frozen=True)
class CommandInspection:
    capabilities: List[str] = field(default_factory=list)
    mutation_paths: List[str] = field(default_factory=list)


def inspect_shell_command(tool_name: str, tool_args: Dict[str, Any]) -> CommandInspection:
    """Infer additional capabilities and mutation paths for shell tools."""
    if tool_name != "bash":
        return CommandInspection()

    command = str(tool_args.get("command", "") or "").strip()
    if not command:
        return CommandInspection()

    try:
        argv = shlex.split(command)
    except ValueError:
        return CommandInspection()
    if not argv:
        return CommandInspection()

    capabilities: List[str] = []
    mutation_paths = _infer_mutation_paths(argv)

    executable = argv[0]
    if executable in _NETWORK_COMMANDS or executable == "gh":
        capabilities.append(NETWORK_ACCESS)
    if executable == "git":
        subcommand = argv[1] if len(argv) > 1 else ""
        if subcommand:
            capabilities.append(GIT_WRITE if subcommand in _GIT_WRITE_SUBCOMMANDS else GIT_READ)
        if subcommand in _GIT_NETWORK_SUBCOMMANDS:
            capabilities.append(NETWORK_ACCESS)

    if mutation_paths:
        capabilities.append(FILESYSTEM_WRITE)

    return CommandInspection(
        capabilities=_dedupe(capabilities),
        mutation_paths=_dedupe(mutation_paths),
    )


def _infer_mutation_paths(argv: List[str]) -> List[str]:
    executable = argv[0]
    mutation_paths: List[str] = []

    if executable in _WRITE_COMMANDS:
        start_index = 1
        if executable in {"cp", "mv"}:
            start_index = max(1, len(argv) - 1)
        mutation_paths.extend(_iter_path_tokens(argv[start_index:]))

    if executable == "git":
        subcommand = argv[1] if len(argv) > 1 else ""
        if subcommand in {"apply", "checkout", "mv", "restore", "rm"}:
            mutation_paths.extend(_iter_path_tokens(argv[2:]))

    for index, token in enumerate(argv[:-1]):
        if token in _REDIRECT_TOKENS:
            mutation_paths.extend(_iter_path_tokens([argv[index + 1]]))
        if token == "tee":
            mutation_paths.extend(_iter_path_tokens(argv[index + 1 :]))

    return [str(_resolve_path(path_token)) for path_token in mutation_paths]


def _iter_path_tokens(tokens: Iterable[str]) -> List[str]:
    paths: List[str] = []
    for token in tokens:
        stripped = str(token).strip()
        if not stripped or stripped in {"|", "&&", "||"}:
            continue
        if stripped.startswith("-"):
            continue
        if "://" in stripped:
            continue
        paths.append(stripped)
    return paths


def _resolve_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def _dedupe(values: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped
