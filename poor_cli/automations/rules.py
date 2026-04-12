"""Unified automation rule model."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from .steps import PromptStep, Step, step_from_dict
from .triggers import (
    CronTrigger,
    EventTrigger,
    SlashTrigger,
    Trigger,
    schedule_to_cron_expression,
    trigger_from_dict,
)


@dataclass(frozen=True)
class AutomationRule:
    id: str
    name: str
    triggers: List[Trigger]
    steps: List[Step]
    enabled: bool = True
    scope: Literal["repo", "user"] = "repo"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "triggers": [trigger.to_dict() for trigger in self.triggers],
            "steps": [step.to_dict() for step in self.steps],
            "enabled": self.enabled,
            "scope": self.scope,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def automation_rule_from_dict(raw: Dict[str, Any]) -> AutomationRule:
    triggers = raw.get("triggers")
    steps = raw.get("steps")
    metadata = raw.get("metadata")
    return AutomationRule(
        id=str(raw.get("id") or raw.get("automationId") or _stable_id("rule", raw)).strip(),
        name=str(raw.get("name") or raw.get("title") or "Automation").strip(),
        triggers=[trigger_from_dict(item) for item in triggers if isinstance(item, dict)]
        if isinstance(triggers, list)
        else [],
        steps=[step_from_dict(item) for item in steps if isinstance(item, dict)]
        if isinstance(steps, list)
        else [],
        enabled=bool(raw.get("enabled", True)),
        scope="user" if str(raw.get("scope") or "").strip() == "user" else "repo",
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


def rule_from_custom_command(raw: Dict[str, Any]) -> AutomationRule:
    name = str(raw.get("name") or Path(str(raw.get("path") or "command")).stem).strip()
    description = str(raw.get("description") or "").strip()
    template = str(raw.get("template") or raw.get("prompt") or raw.get("content") or "").strip()
    scope = "user" if str(raw.get("scope") or "").strip() == "user" else "repo"
    return AutomationRule(
        id=str(raw.get("id") or _stable_id("command", {"name": name, "scope": scope})),
        name=name,
        triggers=[SlashTrigger(command=name, description=description)],
        steps=[PromptStep(prompt=template)],
        enabled=bool(raw.get("enabled", True)),
        scope=scope,
        metadata={"legacyType": "custom_command", **_legacy_metadata(raw, ("path",))},
    )


def rule_from_workflow_template(raw: Dict[str, Any]) -> AutomationRule:
    name = str(raw.get("name") or raw.get("id") or "workflow").strip()
    description = str(raw.get("description") or "").strip()
    prompt = str(raw.get("promptScaffold") or raw.get("starterPrompt") or raw.get("prompt") or "").strip()
    follow_ups = raw.get("followUpCommands")
    metadata = _legacy_metadata(
        raw,
        ("title", "sandboxPreset", "contextStrategy", "category", "icon", "followUpCommands"),
    )
    if isinstance(follow_ups, list):
        metadata["followUpCommands"] = [str(item) for item in follow_ups]
    return AutomationRule(
        id=str(raw.get("id") or _stable_id("workflow", {"name": name})),
        name=name,
        triggers=[SlashTrigger(command=name, description=description)],
        steps=[PromptStep(prompt=prompt)] if prompt else [],
        enabled=bool(raw.get("enabled", True)),
        scope="repo",
        metadata={"legacyType": "workflow_template", **metadata},
    )


def rule_from_automation_payload(raw: Dict[str, Any]) -> AutomationRule:
    schedule = raw.get("schedule")
    metadata = raw.get("metadata")
    if not isinstance(schedule, dict):
        schedule = {}
    return AutomationRule(
        id=str(raw.get("id") or raw.get("automationId") or _stable_id("automation", raw)),
        name=str(raw.get("name") or "Automation").strip(),
        triggers=[CronTrigger(expression=schedule_to_cron_expression(schedule))],
        steps=[PromptStep(prompt=str(raw.get("prompt") or "").strip())],
        enabled=bool(raw.get("enabled", True)),
        scope="repo",
        metadata={
            "legacyType": "automation",
            "schedule": dict(schedule),
            **(dict(metadata) if isinstance(metadata, dict) else {}),
        },
    )


def rule_matches_trigger(rule: AutomationRule, trigger_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    data = payload or {}
    normalized = trigger_type.strip().lower()
    for trigger in rule.triggers:
        if isinstance(trigger, CronTrigger) and normalized == "cron":
            expression = str(data.get("expression") or "").strip()
            if not expression or expression == trigger.expression:
                return True
        if isinstance(trigger, SlashTrigger) and normalized == "slash":
            command = str(data.get("command") or data.get("name") or "").strip()
            if command and not command.startswith("/"):
                command = f"/{command}"
            if command == trigger.command:
                return True
        if isinstance(trigger, EventTrigger) and normalized == "event":
            if str(data.get("event") or "").strip() != trigger.event:
                continue
            if not trigger.filter:
                return True
            if all(data.get(key) == value for key, value in trigger.filter.items()):
                return True
    return False


def _legacy_metadata(raw: Dict[str, Any], keys: tuple[str, ...]) -> Dict[str, Any]:
    return {key: raw[key] for key in keys if key in raw}


def _stable_id(prefix: str, raw: Dict[str, Any]) -> str:
    digest = hashlib.sha256(repr(sorted(raw.items())).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"
