# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class TasksHandlersMixin:
    def _normalize_string_list(raw_values: Any, *, field_name: str) -> List[str]:
        if raw_values is None:
            return []
        if not isinstance(raw_values, list):
            raise InvalidParamsError(f"{field_name} must be an array")

        values: List[str] = []
        for raw_value in raw_values:
            value = str(raw_value or "").strip()
            if value:
                values.append(value)
        return values

    def _coerce_task_execution_metadata(self, raw_execution: Any) -> Dict[str, Any]:
        if raw_execution is None:
            return {}
        if not isinstance(raw_execution, dict):
            raise InvalidParamsError("execution must be an object")

        execution: Dict[str, Any] = {}

        provider = str(raw_execution.get("provider", "") or "").strip()
        if provider:
            execution["provider"] = provider

        model = str(raw_execution.get("model", "") or "").strip()
        if model:
            execution["model"] = model

        routing_mode = str(raw_execution.get("routingMode", "") or "").strip()
        if routing_mode:
            execution["routingMode"] = routing_mode

        config_path = str(raw_execution.get("configPath", "") or "").strip()
        if config_path:
            execution["configPath"] = config_path

        execution_mode = str(raw_execution.get("executionMode", "") or "").strip().lower()
        if execution_mode:
            if execution_mode not in {"worktree", "local"}:
                raise InvalidParamsError("execution.executionMode must be `worktree` or `local`")
            execution["executionMode"] = execution_mode

        reasoning_effort = str(raw_execution.get("reasoningEffort", "") or "").strip().lower()
        if reasoning_effort:
            if reasoning_effort not in {"low", "medium", "high"}:
                raise InvalidParamsError(
                    "execution.reasoningEffort must be `low`, `medium`, or `high`"
                )
            execution["reasoningEffort"] = reasoning_effort

        context_files = self._normalize_string_list(
            raw_execution.get("contextFiles"),
            field_name="execution.contextFiles",
        )
        if context_files:
            execution["contextFiles"] = context_files

        pinned_context_files = self._normalize_string_list(
            raw_execution.get("pinnedContextFiles"),
            field_name="execution.pinnedContextFiles",
        )
        if pinned_context_files:
            execution["pinnedContextFiles"] = pinned_context_files

        raw_context_budget = raw_execution.get("contextBudgetTokens")
        if raw_context_budget is not None:
            try:
                context_budget = int(raw_context_budget)
            except (TypeError, ValueError) as error:
                raise InvalidParamsError("execution.contextBudgetTokens must be an integer") from error
            if context_budget <= 0:
                raise InvalidParamsError("execution.contextBudgetTokens must be greater than zero")
            execution["contextBudgetTokens"] = context_budget

        return execution

    def _task_manager_instance(self) -> TaskManager:
        if self._task_manager is None:
            self._task_manager = TaskManager(Path.cwd())
        return self._task_manager

    async def handle_create_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a durable task and optionally start a background worker."""
        self._ensure_initialized()
        prompt = str(params.get("prompt", "") or "").strip()
        if not prompt:
            raise InvalidParamsError("Missing prompt")
        title = str(params.get("title", "") or "").strip()
        source = str(params.get("source", "manual") or "manual")
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
        auto_start = bool(params.get("autoStart", False))
        requires_approval = bool(params.get("requiresApproval", False))
        auto_approve = bool(params.get("autoApprove", False))
        if self.core.config is not None and getattr(self.core.config, "tasks", None) is not None:
            if sandbox_preset in {"read-only", "review-only"} and "autoStart" not in params:
                auto_start = bool(self.core.config.tasks.auto_start_read_only)
            if sandbox_preset == "workspace-write" and "autoStart" not in params:
                auto_start = bool(self.core.config.tasks.auto_start_workspace_write)
        task = self._task_manager_instance().create_task(
            title=title or prompt.splitlines()[0][:80],
            prompt=prompt,
            sandbox_preset=sandbox_preset,
            source=source,
            metadata=metadata,
            auto_start=auto_start and not requires_approval,
            requires_approval=requires_approval,
            auto_approve=auto_approve,
        )
        return {"task": task.to_dict()}

    async def handle_list_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List durable task records or inbox items."""
        self._ensure_initialized()
        statuses = params.get("statuses")
        if not isinstance(statuses, list):
            statuses = None
        limit = self._clamp_count(params.get("limit"), default=50, min_value=1, max_value=500)
        inbox_only = bool(params.get("inboxOnly", False))
        tasks = self._task_manager_instance().list_tasks(
            statuses=[str(status) for status in statuses] if statuses else None,
            limit=limit,
            inbox_only=inbox_only,
        )
        return {"tasks": [task.to_dict() for task in tasks]}

    async def handle_get_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a single task record."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        task = self._task_manager_instance().get_task(task_id)
        if task is None:
            raise InvalidParamsError(f"Unknown task: {task_id}")
        return {"task": task.to_dict()}

    async def handle_start_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a queued or approved task worker."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        task = self._task_manager_instance().start_task_process(task_id)
        return {"task": task.to_dict()}

    async def handle_approve_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Approve a queued task and optionally start it."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        auto_start = bool(params.get("autoStart", True))
        task = self._task_manager_instance().approve_task(task_id, auto_start=auto_start)
        return {"task": task.to_dict()}

    async def handle_cancel_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel a task."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        task = self._task_manager_instance().cancel_task(task_id)
        return {"task": task.to_dict()}

    async def handle_retry_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create and optionally start a retry task."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        auto_start = params.get("autoStart")
        task = self._task_manager_instance().retry_task(
            task_id,
            auto_start=None if auto_start is None else bool(auto_start),
        )
        return {
            "task": task.to_dict(),
            "runs": self._task_manager_instance().task_runs(task.task_id, limit=10),
        }

    async def handle_replay_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create and optionally start a replay task."""
        self._ensure_initialized()
        task_id = str(params.get("taskId", "")).strip()
        if not task_id:
            raise InvalidParamsError("Missing taskId")
        auto_start = params.get("autoStart")
        task = self._task_manager_instance().replay_task(
            task_id,
            auto_start=None if auto_start is None else bool(auto_start),
        )
        return {
            "task": task.to_dict(),
            "runs": self._task_manager_instance().task_runs(task.task_id, limit=10),
        }

@register('poor-cli/createTask')
async def _rpc_57(ctx, params):
    return await ctx.handle_create_task(params)

@register('poor-cli/listTasks')
async def _rpc_58(ctx, params):
    return await ctx.handle_list_tasks(params)

@register('poor-cli/getTask')
async def _rpc_59(ctx, params):
    return await ctx.handle_get_task(params)

@register('poor-cli/startTask')
async def _rpc_60(ctx, params):
    return await ctx.handle_start_task(params)

@register('poor-cli/approveTask')
async def _rpc_61(ctx, params):
    return await ctx.handle_approve_task(params)

@register('poor-cli/cancelTask')
async def _rpc_62(ctx, params):
    return await ctx.handle_cancel_task(params)

@register('poor-cli/retryTask')
async def _rpc_63(ctx, params):
    return await ctx.handle_retry_task(params)

@register('poor-cli/replayTask')
async def _rpc_64(ctx, params):
    return await ctx.handle_replay_task(params)
