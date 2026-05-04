"""Shared lifecycle event envelope used by task and agent workers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .policy_hooks import HOOK_EVENTS


LIFECYCLE_HOOK_EVENTS: tuple[str, ...] = HOOK_EVENTS


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_lifecycle_event(
    *,
    stream: str,
    entity_id: str,
    stage: str,
    status: str,
    reason_code: str = "",
    run_id: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "stream": str(stream or "").strip() or "unknown",
        "entityId": str(entity_id or "").strip() or "unknown",
        "stage": str(stage or "").strip() or "unknown",
        "status": str(status or "").strip() or "unknown",
        "reasonCode": str(reason_code or "").strip() or "",
        "at": utc_now_iso(),
    }
    if run_id:
        data["runId"] = str(run_id)
    if details:
        data["details"] = dict(details)
    return {"type": "lifecycle", "data": data}
