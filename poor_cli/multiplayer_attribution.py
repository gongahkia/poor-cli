"""Author attribution helpers for multiplayer chat notifications."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from typing import Any, Dict, Optional

AUTHOR_KEYS = ("authorConnectionId", "authorDisplayName", "authorRole")
LOCAL_AUTHOR_CONNECTION_ID = "local"

_CURRENT_AUTHOR_TAG: ContextVar[Optional[Dict[str, str]]] = ContextVar(
    "poor_cli_current_author_tag",
    default=None,
)


def _local_display_name(session: Any = None) -> str:
    state = getattr(session, "state", session)
    configured = str(getattr(state, "owner_name", "") or "").strip()
    if configured:
        return configured
    for key in ("POOR_CLI_AUTHOR_NAME", "POOR_CLI_OWNER_NAME", "USER", "LOGNAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return LOCAL_AUTHOR_CONNECTION_ID


def local_author_tag(session: Any = None) -> Dict[str, str]:
    return {
        "authorConnectionId": LOCAL_AUTHOR_CONNECTION_ID,
        "authorDisplayName": _local_display_name(session),
        "authorRole": LOCAL_AUTHOR_CONNECTION_ID,
    }


def author_tag_for(connection_id: str, session: Any = None) -> Dict[str, str]:
    """Return {authorConnectionId, authorDisplayName, authorRole}."""
    normalized = str(connection_id or "").strip()
    if not normalized or normalized == LOCAL_AUTHOR_CONNECTION_ID:
        return local_author_tag(session)

    state = getattr(session, "state", session)
    members = getattr(state, "members", {}) if state is not None else {}
    member = members.get(normalized) if isinstance(members, dict) else None
    if member is None:
        return {
            "authorConnectionId": normalized,
            "authorDisplayName": normalized,
            "authorRole": "unknown",
        }

    display_name = str(getattr(member, "client_name", "") or "").strip() or normalized
    role = str(getattr(member, "role", "") or "").strip() or "unknown"
    return {
        "authorConnectionId": normalized,
        "authorDisplayName": display_name,
        "authorRole": role,
    }


def set_current_author_tag(author: Optional[Dict[str, Any]]) -> Token[Optional[Dict[str, str]]]:
    tag: Optional[Dict[str, str]] = None
    if isinstance(author, dict):
        tag = {
            "authorConnectionId": str(author.get("authorConnectionId", "") or "").strip()
            or LOCAL_AUTHOR_CONNECTION_ID,
            "authorDisplayName": str(author.get("authorDisplayName", "") or "").strip()
            or LOCAL_AUTHOR_CONNECTION_ID,
            "authorRole": str(author.get("authorRole", "") or "").strip() or "unknown",
        }
    return _CURRENT_AUTHOR_TAG.set(tag)


def reset_current_author_tag(token: Token[Optional[Dict[str, str]]]) -> None:
    _CURRENT_AUTHOR_TAG.reset(token)


def current_author_tag(session: Any = None) -> Dict[str, str]:
    tag = _CURRENT_AUTHOR_TAG.get()
    if tag is not None:
        return dict(tag)
    return local_author_tag(session)


def add_author_tag(payload: Dict[str, Any], author: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tagged = dict(payload)
    tagged.update(current_author_tag() if author is None else normalize_author_tag(author))
    return tagged


def normalize_author_tag(author: Dict[str, Any]) -> Dict[str, str]:
    return {
        "authorConnectionId": str(author.get("authorConnectionId", "") or "").strip()
        or LOCAL_AUTHOR_CONNECTION_ID,
        "authorDisplayName": str(author.get("authorDisplayName", "") or "").strip()
        or LOCAL_AUTHOR_CONNECTION_ID,
        "authorRole": str(author.get("authorRole", "") or "").strip() or "unknown",
    }


def attribution_explicitly_disabled(client_capabilities: Any) -> bool:
    current = client_capabilities
    for key in ("multiplayer", "features", "messageAttribution"):
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    return current is False
