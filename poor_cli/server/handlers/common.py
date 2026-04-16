# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *


class CommonHandlersMixin:
    def _init_handler_state(self) -> None:
        self.initialized = False
        self._needs_provider_init = False
        self._pending_init_params: Dict[str, Any] = {}
        self.permission_mode: str = PermissionMode.DEFAULT.value
        self._client_streaming = False
        self._client_capabilities: Dict[str, Any] = {}
        self._pending_permissions: Dict[str, asyncio.Future] = {}
        self._pending_plans: Dict[str, asyncio.Future] = {}
        self._tool_stream_session: Optional[Any] = None
        from poor_cli.tool_events import TimelineStore
        self._tool_events = TimelineStore()
        self._conversation_branches = None
        self._service_lock: Optional[asyncio.Lock] = None
        self._managed_services: Dict[str, ManagedServiceRuntime] = {}
        self._service_logs_dir = Path.home() / ".poor-cli" / "services"
        self._task_manager: Optional[TaskManager] = None
        self._automation_manager: Optional[AutomationManager] = None
        self._sandbox_preset: str = "workspace-write"
        self._permission_rules = PermissionRuleEngine(Path.cwd())

    def _normalize_client_capabilities(self, raw_capabilities: Any) -> Dict[str, Any]:
        if isinstance(raw_capabilities, dict):
            return dict(raw_capabilities)
        return {}

    def _client_supports(self, *path: str, default: bool = True) -> bool:
        if not self._client_capabilities:
            return default
        current: Any = self._client_capabilities
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        if isinstance(current, bool):
            return current
        return default

    def _current_sandbox_preset(self) -> str:
        config = getattr(self.core, "config", None)
        if config is not None and getattr(config, "sandbox", None) is not None:
            configured = str(getattr(config.sandbox, "default_preset", "")).strip()
            if configured:
                self._sandbox_preset = normalize_preset(
                    configured,
                    fallback_permission_mode=self.permission_mode,
                )
        else:
            self._sandbox_preset = preset_from_permission_mode(self.permission_mode)
        return self._sandbox_preset

    def _skill_registry(self) -> SkillRegistry:
        search_paths: List[str] = []
        config = getattr(self.core, "config", None)
        if config is not None and getattr(config, "skills", None) is not None:
            raw_paths = getattr(config.skills, "search_paths", [])
            if isinstance(raw_paths, list):
                search_paths = [str(path) for path in raw_paths if str(path).strip()]
        return SkillRegistry(Path.cwd(), search_paths=search_paths)

    def _command_registry(self) -> CustomCommandRegistry:
        return CustomCommandRegistry(Path.cwd())

    def _get_service_lock(self) -> asyncio.Lock:
        if self._service_lock is None:
            self._service_lock = asyncio.Lock()
        return self._service_lock

    def _track_background_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        self._background_tasks.add(task)

        def _discard(done_task: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(done_task)

        task.add_done_callback(_discard)
        return task

    def _resolve_pending_review_requests(self) -> None:
        denied_permission = {
            "allowed": False,
            "approvedPaths": [],
            "approvedChunks": [],
        }
        for future in list(self._pending_permissions.values()):
            if not future.done():
                future.set_result(dict(denied_permission))
        self._pending_permissions.clear()

        for future in list(self._pending_plans.values()):
            if not future.done():
                future.set_result(False)
        self._pending_plans.clear()

    async def _shutdown_background_tasks(self) -> None:
        tasks = [task for task in self._background_tasks if not task.done()]
        if not tasks:
            self._background_tasks.clear()
            return

        for task in tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def _server_permission_callback(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        preview: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Server-side permission callback for core tool execution."""
        decision = self._evaluate_tool_access(tool_name, tool_args, preview)
        if not decision.allowed:
            if "outside trusted workspace roots" in decision.reason:
                raise_for_denial(tool_name, self.permission_mode, decision)
            return False
        return not decision.requires_approval

    def _ensure_initialized(self) -> None:
        """Ensure the server is initialized."""
        if not self.initialized:
            raise Exception("Server not initialized. Call 'initialize' first.")
