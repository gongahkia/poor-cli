# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class AutomationsHandlersMixin:
    def _automation_manager_instance(self) -> AutomationManager:
        if self._automation_manager is None:
            self._automation_manager = AutomationManager(
                Path.cwd(),
                task_manager=self._task_manager_instance(),
            )
        return self._automation_manager

    async def handle_create_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a durable scheduled automation backed by the task runner."""
        self._ensure_initialized()
        prompt = str(params.get("prompt", "") or "").strip()
        if not prompt:
            raise InvalidParamsError("Missing prompt")
        schedule = params.get("schedule")
        if not isinstance(schedule, dict):
            raise InvalidParamsError("schedule must be an object")

        name = str(params.get("name", "") or "").strip()
        metadata = params.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        base_execution = metadata.get("execution")
        if base_execution is not None and not isinstance(base_execution, dict):
            raise InvalidParamsError("metadata.execution must be an object")
        execution = dict(base_execution) if isinstance(base_execution, dict) else {}
        execution.update(self._coerce_task_execution_metadata(params.get("execution")))
        if execution:
            metadata["execution"] = execution

        sandbox_preset = normalize_preset(
            params.get("sandboxPreset"),
            fallback_permission_mode=self.permission_mode,
        )
        automation = self._automation_manager_instance().create_automation(
            name=name or prompt.splitlines()[0][:80],
            prompt=prompt,
            schedule=schedule,
            sandbox_preset=sandbox_preset,
            enabled=bool(params.get("enabled", True)),
            requires_approval=bool(params.get("requiresApproval", False)),
            metadata=metadata,
            auto_approve=bool(params.get("autoApprove", False)),
        )
        return {"automation": automation.to_dict()}

    async def handle_list_automations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List scheduled automations."""
        self._ensure_initialized()
        enabled_param = params.get("enabled")
        enabled = None if enabled_param is None else bool(enabled_param)
        limit = self._clamp_count(params.get("limit"), default=100, min_value=1, max_value=500)
        automations = self._automation_manager_instance().list_automations(
            enabled=enabled,
            limit=limit,
        )
        return {"automations": [automation.to_dict() for automation in automations]}

    async def handle_get_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return one automation record."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        automation = self._automation_manager_instance().get_automation(automation_id)
        if automation is None:
            raise InvalidParamsError(f"Unknown automation: {automation_id}")
        return {"automation": automation.to_dict()}

    async def handle_set_automation_enabled(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Enable or disable an automation."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        if "enabled" not in params:
            raise InvalidParamsError("Missing enabled")
        automation = self._automation_manager_instance().set_enabled(
            automation_id,
            bool(params.get("enabled")),
        )
        return {"automation": automation.to_dict()}

    async def handle_run_automation_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Launch one automation immediately and return the resulting task."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        task = self._automation_manager_instance().run_now(automation_id)
        return {"task": task.to_dict()}

    async def handle_run_due_automations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run all automations currently due."""
        self._ensure_initialized()
        limit = self._clamp_count(params.get("limit"), default=20, min_value=1, max_value=200)
        tasks = self._automation_manager_instance().run_due(limit=limit)
        return {"tasks": [task.to_dict() for task in tasks]}

    async def handle_get_automation_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return recent run history for one automation."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        limit = self._clamp_count(params.get("limit"), default=25, min_value=1, max_value=200)
        history = self._automation_manager_instance().history(automation_id, limit=limit)
        return {"runs": history}

    async def handle_replay_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Launch an automation replay task."""
        self._ensure_initialized()
        automation_id = str(params.get("automationId", "")).strip()
        if not automation_id:
            raise InvalidParamsError("Missing automationId")
        task = self._automation_manager_instance().replay(automation_id)
        return {"task": task.to_dict()}

@register('poor-cli/createAutomation')
async def _rpc_65(ctx, params):
    return await ctx.handle_create_automation(params)

@register('poor-cli/listAutomations')
async def _rpc_66(ctx, params):
    return await ctx.handle_list_automations(params)

@register('poor-cli/getAutomation')
async def _rpc_67(ctx, params):
    return await ctx.handle_get_automation(params)

@register('poor-cli/setAutomationEnabled')
async def _rpc_68(ctx, params):
    return await ctx.handle_set_automation_enabled(params)

@register('poor-cli/runAutomationNow')
async def _rpc_69(ctx, params):
    return await ctx.handle_run_automation_now(params)

@register('poor-cli/runDueAutomations')
async def _rpc_70(ctx, params):
    return await ctx.handle_run_due_automations(params)

@register('poor-cli/getAutomationHistory')
async def _rpc_71(ctx, params):
    return await ctx.handle_get_automation_history(params)

@register('poor-cli/replayAutomation')
async def _rpc_72(ctx, params):
    return await ctx.handle_replay_automation(params)
