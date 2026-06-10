"""Unified extension model: AutomationRule plus skills."""

from __future__ import annotations

from .rules import (
    AutomationRule,
    automation_rule_from_dict,
    rule_from_automation_payload,
    rule_from_custom_command,
    rule_from_workflow_template,
    rule_matches_trigger,
)
from .steps import PromptStep, ShellStep, Step, ToolCallStep, execute_step, step_from_dict
from .triggers import (
    CronTrigger,
    EventTrigger,
    SlashTrigger,
    Trigger,
    schedule_to_cron_expression,
    trigger_from_dict,
)


def __getattr__(name: str):
    if name in {"MigrationResult", "migrate_extensions", "restore_migration"}:
        from . import migration

        return getattr(migration, name)
    if name in {
        "AutomationManager",
        "AutomationRecord",
        "format_schedule",
        "next_run_after",
        "parse_daily_schedule",
        "parse_weekly_schedule",
        "schedule_interval",
    }:
        from .. import automation_manager

        return getattr(automation_manager, name)
    if name in {"CustomCommand", "CustomCommandRegistry", "default_command_search_paths"}:
        from .. import custom_commands

        return getattr(custom_commands, name)
    if name in {"WorkflowTemplate", "get_workflow_template", "list_workflow_templates", "workflow_names"}:
        from .. import workflow_templates

        return getattr(workflow_templates, name)
    raise AttributeError(name)


__all__ = [
    "AutomationRule",
    "AutomationManager",
    "AutomationRecord",
    "CustomCommand",
    "CustomCommandRegistry",
    "CronTrigger",
    "EventTrigger",
    "MigrationResult",
    "PromptStep",
    "ShellStep",
    "SlashTrigger",
    "Step",
    "ToolCallStep",
    "Trigger",
    "WorkflowTemplate",
    "automation_rule_from_dict",
    "default_command_search_paths",
    "execute_step",
    "format_schedule",
    "get_workflow_template",
    "list_workflow_templates",
    "migrate_extensions",
    "next_run_after",
    "parse_daily_schedule",
    "parse_weekly_schedule",
    "restore_migration",
    "rule_from_automation_payload",
    "rule_from_custom_command",
    "rule_from_workflow_template",
    "rule_matches_trigger",
    "schedule_to_cron_expression",
    "schedule_interval",
    "step_from_dict",
    "trigger_from_dict",
    "workflow_names",
]
