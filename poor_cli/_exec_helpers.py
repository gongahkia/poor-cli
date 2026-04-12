"""Shared helpers for exec-mode permission callbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .sandbox import evaluate_tool_access


def _trusted_workspace_roots(security_cfg: Any) -> list[Path]:
    roots: list[Path] = []
    raw_roots = getattr(security_cfg, "trusted_roots", []) if security_cfg is not None else []
    if isinstance(raw_roots, list):
        for raw_root in raw_roots:
            if not isinstance(raw_root, str) or not raw_root.strip():
                continue
            root_path = Path(raw_root).expanduser()
            if not root_path.is_absolute():
                root_path = Path.cwd() / root_path
            roots.append(root_path.resolve())
    if not roots:
        roots.append(Path.cwd().resolve())
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def build_exec_permission_callback(
    core: Any,
    allow_tools: set[str],
    deny_tools: set[str],
    *,
    plan_only: bool,
    permission_mode: str,
    sandbox_preset: str,
    auto_approve: bool,
):
    async def _callback(tool_name: str, tool_args: dict[str, Any], preview: Optional[dict[str, Any]] = None):
        if plan_only:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if tool_name in deny_tools:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if allow_tools and tool_name not in allow_tools:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if not core.tool_registry:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        mutation_paths = list(preview.get("paths") or []) if isinstance(preview, dict) else []
        if not mutation_paths:
            mutation_paths = core.tool_registry.inspect_mutation_targets(tool_name, tool_args)
        security_cfg = getattr(core.config, "security", None)
        trusted_roots = _trusted_workspace_roots(security_cfg)
        enforce_trusted_workspace = bool(
            getattr(security_cfg, "enforce_trusted_workspace", True)
        ) if security_cfg is not None else True
        safe_commands = getattr(security_cfg, "safe_commands", None) if security_cfg is not None else None
        decision = evaluate_tool_access(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_capabilities=core.tool_registry.get_tool_capabilities(tool_name),
            permission_mode=permission_mode,
            sandbox_preset=sandbox_preset,
            trusted_roots=trusted_roots,
            mutation_paths=mutation_paths,
            enforce_trusted_workspace=enforce_trusted_workspace,
            safe_process_commands=safe_commands,
        )
        if not decision.allowed:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if decision.requires_approval and not auto_approve:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        return {"allowed": True, "approvedPaths": [], "approvedChunks": []}
    return _callback
