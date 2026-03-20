"""
Capability-based sandbox presets for tool execution.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .command_capabilities import inspect_shell_command
from .command_validator import CommandRisk, get_command_validator
from .config import PermissionMode
from .exceptions import PermissionDeniedError


class SandboxPreset(str, Enum):
    READ_ONLY = "read-only"
    REVIEW_ONLY = "review-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


class ToolCapability(str, Enum):
    FILESYSTEM_READ = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    PROCESS_EXECUTE = "process:execute"
    NETWORK_ACCESS = "network:access"
    GIT_READ = "git:read"
    GIT_WRITE = "git:write"


LEGACY_PERMISSION_MODE_TO_PRESET = {
    PermissionMode.PROMPT.value: SandboxPreset.WORKSPACE_WRITE.value,
    PermissionMode.AUTO_SAFE.value: SandboxPreset.WORKSPACE_WRITE.value,
    PermissionMode.DANGER_FULL_ACCESS.value: SandboxPreset.FULL_ACCESS.value,
}

PRESET_DESCRIPTION = {
    SandboxPreset.READ_ONLY.value: "Read files and inspect git state. No mutations or shell execution.",
    SandboxPreset.REVIEW_ONLY.value: "Read files, inspect git state, and run commands for analysis only.",
    SandboxPreset.WORKSPACE_WRITE.value: "Allow workspace mutations with approval gates and trusted-root enforcement.",
    SandboxPreset.FULL_ACCESS.value: "Allow all capabilities without approval prompts.",
}

SAFE_PROCESS_COMMANDS = {
    "pwd",
    "ls",
    "echo",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "which",
    "whoami",
    "date",
}


@dataclass(frozen=True)
class SandboxDecision:
    allowed: bool
    reason: str = ""
    requires_approval: bool = False
    capabilities: List[str] = field(default_factory=list)


def preset_from_permission_mode(raw_mode: str) -> str:
    try:
        mode = PermissionMode(str(raw_mode))
    except ValueError:
        return SandboxPreset.WORKSPACE_WRITE.value
    return LEGACY_PERMISSION_MODE_TO_PRESET.get(mode.value, SandboxPreset.WORKSPACE_WRITE.value)


def permission_mode_from_preset(preset: str) -> str:
    normalized = str(preset).strip().lower()
    if normalized == SandboxPreset.FULL_ACCESS.value:
        return PermissionMode.DANGER_FULL_ACCESS.value
    if normalized == SandboxPreset.READ_ONLY.value:
        return PermissionMode.PROMPT.value
    if normalized == SandboxPreset.REVIEW_ONLY.value:
        return PermissionMode.AUTO_SAFE.value
    return PermissionMode.PROMPT.value


def normalize_preset(raw_preset: Optional[str], *, fallback_permission_mode: str = "prompt") -> str:
    candidate = str(raw_preset or "").strip().lower()
    if candidate in {preset.value for preset in SandboxPreset}:
        return candidate
    return preset_from_permission_mode(fallback_permission_mode)


def allowed_capabilities_for_preset(preset: str) -> Set[str]:
    normalized = normalize_preset(preset)
    if normalized == SandboxPreset.FULL_ACCESS.value:
        return {cap.value for cap in ToolCapability}
    if normalized == SandboxPreset.WORKSPACE_WRITE.value:
        return {
            ToolCapability.FILESYSTEM_READ.value,
            ToolCapability.FILESYSTEM_WRITE.value,
            ToolCapability.PROCESS_EXECUTE.value,
            ToolCapability.GIT_READ.value,
            ToolCapability.GIT_WRITE.value,
        }
    if normalized == SandboxPreset.REVIEW_ONLY.value:
        return {
            ToolCapability.FILESYSTEM_READ.value,
            ToolCapability.PROCESS_EXECUTE.value,
            ToolCapability.GIT_READ.value,
        }
    return {
        ToolCapability.FILESYSTEM_READ.value,
        ToolCapability.GIT_READ.value,
    }


def approval_capabilities_for_preset(preset: str) -> Set[str]:
    normalized = normalize_preset(preset)
    if normalized == SandboxPreset.WORKSPACE_WRITE.value:
        return {
            ToolCapability.FILESYSTEM_WRITE.value,
            ToolCapability.PROCESS_EXECUTE.value,
            ToolCapability.NETWORK_ACCESS.value,
            ToolCapability.GIT_WRITE.value,
        }
    return set()


def requires_safe_process_mode(permission_mode: str, preset: str) -> bool:
    normalized_preset = normalize_preset(preset, fallback_permission_mode=permission_mode)
    if normalized_preset == SandboxPreset.REVIEW_ONLY.value:
        return True
    return str(permission_mode).strip().lower() == PermissionMode.AUTO_SAFE.value


def summarize_capabilities(capabilities: Sequence[str]) -> str:
    if not capabilities:
        return "none"
    return ", ".join(sorted(dict.fromkeys(str(cap) for cap in capabilities)))


def tool_capability_metadata(
    capabilities: Iterable[str],
    *,
    mutating: bool = False,
) -> Dict[str, Any]:
    rendered = [str(capability) for capability in capabilities]
    return {
        "x-poor-cli": {
            "capabilities": rendered,
            "mutating": bool(mutating),
        }
    }


def declaration_capabilities(declaration: Dict[str, Any]) -> List[str]:
    metadata = declaration.get("x-poor-cli")
    if not isinstance(metadata, dict):
        return []
    capabilities = metadata.get("capabilities")
    if not isinstance(capabilities, list):
        return []
    return [str(cap) for cap in capabilities if str(cap).strip()]


def evaluate_tool_access(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_capabilities: Sequence[str],
    permission_mode: str,
    sandbox_preset: str,
    trusted_roots: Sequence[Path],
    mutation_paths: Sequence[str],
    enforce_trusted_workspace: bool = True,
    safe_process_commands: Optional[Sequence[str]] = None,
) -> SandboxDecision:
    normalized_preset = normalize_preset(sandbox_preset, fallback_permission_mode=permission_mode)
    inferred = inspect_shell_command(tool_name, tool_args)
    normalized_caps = _dedupe_capabilities(
        [*tool_capabilities, *inferred.capabilities]
    )
    effective_mutation_paths = _dedupe_paths([*mutation_paths, *inferred.mutation_paths])
    if not normalized_caps:
        return SandboxDecision(allowed=True, capabilities=[])

    if normalized_preset == SandboxPreset.FULL_ACCESS.value:
        return SandboxDecision(allowed=True, capabilities=normalized_caps)

    allowed_capabilities = allowed_capabilities_for_preset(normalized_preset)
    denied = [cap for cap in normalized_caps if cap not in allowed_capabilities]
    if denied:
        return SandboxDecision(
            allowed=False,
            capabilities=normalized_caps,
            reason=f"`{tool_name}` requires {summarize_capabilities(denied)}, not allowed by `{normalized_preset}`",
        )

    if enforce_trusted_workspace and ToolCapability.FILESYSTEM_WRITE.value in normalized_caps:
        trusted_denial = _check_trusted_roots(effective_mutation_paths, trusted_roots)
        if trusted_denial is not None:
            return SandboxDecision(
                allowed=False,
                capabilities=normalized_caps,
                reason=trusted_denial,
            )

    if ToolCapability.PROCESS_EXECUTE.value in normalized_caps and requires_safe_process_mode(
        permission_mode,
        normalized_preset,
    ):
        if not _is_safe_process_command(tool_name, tool_args, safe_process_commands):
            return SandboxDecision(
                allowed=False,
                capabilities=normalized_caps,
                reason=f"`{tool_name}` is blocked by safe-process mode",
            )

    requires_approval = bool(
        set(normalized_caps).intersection(approval_capabilities_for_preset(normalized_preset))
    ) and str(permission_mode).strip().lower() != PermissionMode.AUTO_SAFE.value
    return SandboxDecision(
        allowed=True,
        capabilities=normalized_caps,
        requires_approval=requires_approval,
    )


def raise_for_denial(tool_name: str, permission_mode: str, decision: SandboxDecision) -> None:
    if decision.allowed:
        return
    raise PermissionDeniedError(
        tool_name=tool_name,
        permission_mode=permission_mode,
        reason=decision.reason or "sandbox policy denied the operation",
    )


def _check_trusted_roots(paths: Sequence[str], trusted_roots: Sequence[Path]) -> Optional[str]:
    normalized_roots = [Path(root).expanduser().resolve() for root in trusted_roots]
    for raw_path in paths:
        candidate = Path(str(raw_path)).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        if any(_path_is_within_root(resolved, root) for root in normalized_roots):
            continue
        joined_roots = ", ".join(str(root) for root in normalized_roots)
        return f"requested mutation falls outside trusted workspace roots ({joined_roots})"
    return None


def _dedupe_capabilities(capabilities: Sequence[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for capability in capabilities:
        normalized = str(capability).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _dedupe_paths(paths: Sequence[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _path_is_within_root(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _is_safe_process_command(
    tool_name: str,
    tool_args: Dict[str, Any],
    safe_process_commands: Optional[Sequence[str]] = None,
) -> bool:
    if tool_name == "run_tests":
        return True
    command = str(tool_args.get("command", "")).strip()
    if not command:
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv:
        return False
    validation = get_command_validator(strict_mode=False).validate(command)
    if validation.risk_level != CommandRisk.SAFE:
        return False
    allowlist = {
        str(entry).strip()
        for entry in (safe_process_commands or SAFE_PROCESS_COMMANDS)
        if isinstance(entry, str) and str(entry).strip()
    }
    if argv[0] in allowlist:
        return True
    if len(argv) >= 2 and " ".join(argv[:2]) in allowlist:
        return True
    return command in allowlist
