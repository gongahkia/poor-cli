from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def trusted_workspace_enabled(core: Any) -> bool:
    security_cfg = getattr(getattr(core, "config", None), "security", None)
    if security_cfg is None:
        return True
    return bool(getattr(security_cfg, "enforce_trusted_workspace", True))


def trusted_workspace_roots(core: Any) -> List[Path]:
    security_cfg = getattr(getattr(core, "config", None), "security", None)
    roots: List[Path] = []
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
    deduped: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _visible_tool_declarations(core: Any, permission_rules: Any) -> List[Dict[str, Any]]:
    declarations = core.get_available_tools()
    hidden = set()
    for declaration in declarations:
        tool_name = str(declaration.get("name") or "").strip().lower()
        if not tool_name:
            continue
        if permission_rules.is_tool_blanket_denied(tool_name):
            hidden.add(tool_name)
    if not hidden:
        return declarations
    visible: List[Dict[str, Any]] = []
    for declaration in declarations:
        tool_name = str(declaration.get("name") or "").strip().lower()
        if tool_name and tool_name in hidden:
            continue
        visible.append(declaration)
    return visible


async def sync_provider_tool_visibility(
    *,
    core: Any,
    initialized: bool,
    permission_rules: Any,
    logger: Any,
) -> None:
    if not initialized:
        return
    try:
        await core.refresh_provider_tools(_visible_tool_declarations(core, permission_rules))
    except Exception as error:
        logger.warning("Failed to sync provider tool visibility: %s", error)
