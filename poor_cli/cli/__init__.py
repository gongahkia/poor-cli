"""CLI subcommand handlers (lazy-exported)."""

from __future__ import annotations

from importlib import import_module

_EXPORT_MAP = {
    "run_checkpoint_mode": "state_cmds",
    "run_history_mode": "state_cmds",
    "run_session_mode": "state_cmds",
    "run_memory_mode": "state_cmds",
    "run_config_mode": "config_cmds",
    "run_profile_mode": "config_cmds",
    "run_trust_mode": "trust_cmds",
    "run_provider_mode": "config_cmds",
    "run_core_info_command": "config_cmds",
    "run_cost_mode": "config_cmds",
    "run_search_mode": "config_cmds",
    "run_context_mode": "config_cmds",
    "run_workflow_mode": "config_cmds",
    "run_services_mode": "config_cmds",
    "run_review_file_mode": "review_cmds",
    "run_commit_mode": "review_cmds",
    "run_audit_mode": "audit",
}

__all__ = list(_EXPORT_MAP.keys())


def __getattr__(name: str):
    module_name = _EXPORT_MAP.get(name)
    if module_name is None:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value
