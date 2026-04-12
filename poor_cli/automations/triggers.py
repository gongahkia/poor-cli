"""Unified automation triggers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Union


@dataclass(frozen=True)
class CronTrigger:
    expression: str
    type: Literal["cron"] = "cron"

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "expression": self.expression}


@dataclass(frozen=True)
class EventTrigger:
    event: str
    filter: Optional[Dict[str, Any]] = None
    type: Literal["event"] = "event"

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"type": self.type, "event": self.event}
        if self.filter:
            payload["filter"] = dict(self.filter)
        return payload


@dataclass(frozen=True)
class SlashTrigger:
    command: str
    description: str = ""
    type: Literal["slash"] = "slash"

    def to_dict(self) -> Dict[str, Any]:
        payload = {"type": self.type, "command": self.command}
        if self.description:
            payload["description"] = self.description
        return payload


Trigger = Union[CronTrigger, EventTrigger, SlashTrigger]


def trigger_from_dict(raw: Dict[str, Any]) -> Trigger:
    kind = str(raw.get("type") or raw.get("kind") or "").strip().lower()
    if kind == "cron":
        return CronTrigger(expression=str(raw.get("expression") or raw.get("cron") or "").strip())
    if kind == "event":
        raw_filter = raw.get("filter")
        return EventTrigger(
            event=str(raw.get("event") or "").strip(),
            filter=dict(raw_filter) if isinstance(raw_filter, dict) else None,
        )
    if kind == "slash":
        return SlashTrigger(
            command=_normalize_slash_command(str(raw.get("command") or raw.get("name") or "").strip()),
            description=str(raw.get("description") or "").strip(),
        )
    raise ValueError(f"Unknown trigger type: {kind}")


def _normalize_slash_command(command: str) -> str:
    cleaned = command.strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith("/") else f"/{cleaned}"


def schedule_to_cron_expression(schedule: Dict[str, Any]) -> str:
    kind = str(schedule.get("kind") or "").strip().lower()
    if kind == "interval":
        return f"@every {int(schedule.get('minutes', 0))}m"
    if kind == "daily":
        return f"{int(schedule.get('minute', 0))} {int(schedule.get('hour', 0))} * * *"
    if kind == "weekly":
        weekdays = ",".join(str(int(day)) for day in schedule.get("weekdays", []))
        return f"{int(schedule.get('minute', 0))} {int(schedule.get('hour', 0))} * * {weekdays}"
    raw = str(schedule.get("cron") or schedule.get("expression") or "").strip()
    return raw or "@manual"
