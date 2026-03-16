"""
Tests for the JSON-RPC server.
"""

import asyncio
import json
import os
import subprocess
import sys
import pytest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.automation_manager import AutomationManager
from poor_cli.config import Config
from poor_cli.exceptions import PermissionDeniedError
from poor_cli.server import (
    PoorCLIServer,
    JsonRpcMessage,
    JsonRpcError,
    InvalidParamsError,
    _sanitize_exception_message,
    main,
)
from poor_cli.task_manager import TaskManager
from poor_cli.tools_async import ToolOutcome


def _init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.name", "Poor CLI Tests"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


class _FragmentedStdin:
    """Chunked stdin reader used to simulate transport fragmentation."""

    def __init__(self, fragments):
        self._fragments = deque(fragments)

    def read(self, size=-1):
        if not self._fragments:
            return ""
        if size is None or size < 0:
            return self._fragments.popleft()

        out = ""
        while self._fragments and len(out) < size:
            fragment = self._fragments[0]
            remaining = size - len(out)
            if len(fragment) <= remaining:
                out += self._fragments.popleft()
            else:
                out += fragment[:remaining]
                self._fragments[0] = fragment[remaining:]
                break
        return out


class _InlineEventLoop:
    async def run_in_executor(self, _executor, fn):
        return fn()


class _FakeMultiplayerHost:
    instances = []

    def __init__(
        self,
        *,
        bind_host,
        port,
        room_names,
        server_factory,
        message_cls,
        rpc_error_cls,
        default_permission_mode,
    ):
        self.bind_host = bind_host
        self.port = port
        self.room_names = list(room_names)
        self.server_factory = server_factory
        self.message_cls = message_cls
        self.rpc_error_cls = rpc_error_cls
        self.default_permission_mode = default_permission_mode
        self.started = False
        self.stopped = False
        self.room_members = {
            room: [
                {
                    "connectionId": f"{room}-viewer",
                    "role": "viewer",
                    "clientName": f"{room}-client",
                    "initialized": True,
                    "connected": True,
                    "active": False,
                    "joinedAt": "now",
                }
            ]
            for room in self.room_names
        }
        _FakeMultiplayerHost.instances.append(self)

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    def get_room_tokens(self):
        return {
            room: {
                "viewer": f"{room}-viewer-token",
                "prompter": f"{room}-prompter-token",
            }
            for room in self.room_names
        }

    def list_room_members(self, room_name=None):
        names = [room_name] if room_name else list(self.room_members.keys())
        payload = []
        for name in names:
            members = [dict(member) for member in self.room_members.get(name, [])]
            payload.append(
                {
                    "name": name,
                    "memberCount": len(members),
                    "members": members,
                    "queueDepth": 0,
                    "activeConnectionId": "",
                }
            )
        return payload

    async def remove_room_member(self, room_name, connection_id):
        members = self.room_members.get(room_name, [])
        before = len(members)
        self.room_members[room_name] = [
            member for member in members if member.get("connectionId") != connection_id
        ]
        return len(self.room_members[room_name]) != before

    async def set_room_member_role(self, room_name, connection_id, role):
        for member in self.room_members.get(room_name, []):
            if member.get("connectionId") == connection_id:
                member["role"] = role
                return True
        return False


class _FakeManagedProcess:
    def __init__(self, pid: int = 4321):
        self.pid = pid
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class TestJsonRpcMessage:
    """Test JsonRpcMessage parsing and serialization."""

    def test_from_dict_valid_request(self):
        """Test parsing a valid JSON-RPC request."""
        data = {"jsonrpc": "2.0", "id": 1, "method": "test", "params": {"key": "value"}}

        message = JsonRpcMessage.from_dict(data)

        assert message.jsonrpc == "2.0"
        assert message.id == 1
        assert message.method == "test"
        assert message.params == {"key": "value"}

    def test_from_dict_without_params(self):
        """Test parsing request without params."""
        data = {"jsonrpc": "2.0", "id": 1, "method": "test"}

        message = JsonRpcMessage.from_dict(data)

        assert message.params is None

    def test_from_dict_notification(self):
        """Test parsing notification (no id)."""
        data = {"jsonrpc": "2.0", "method": "notify"}

        message = JsonRpcMessage.from_dict(data)

        assert message.id is None
        assert message.method == "notify"

    def test_to_dict_success_response(self):
        """Test serializing success response."""
        message = JsonRpcMessage(id=1, result={"status": "ok"})

        data = message.to_dict()

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"] == {"status": "ok"}

    def test_to_dict_error_response(self):
        """Test serializing error response."""
        message = JsonRpcMessage(id=1, error={"code": -32600, "message": "Invalid request"})

        data = message.to_dict()

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "error" in data
        assert data["error"]["code"] == -32600

    def test_to_json(self):
        """Test JSON serialization."""
        message = JsonRpcMessage(id=1, result="ok")
        json_str = message.to_json()

        parsed = json.loads(json_str)
        assert parsed["id"] == 1
        assert parsed["result"] == "ok"

    def test_from_json(self):
        """Test JSON parsing."""
        json_str = '{"jsonrpc": "2.0", "id": 1, "method": "test"}'
        message = JsonRpcMessage.from_json(json_str)

        assert message.id == 1
        assert message.method == "test"


class TestJsonRpcError:
    """Test JsonRpcError error codes and helpers."""

    def test_error_code_values(self):
        """Test standard error code values."""
        assert JsonRpcError.PARSE_ERROR == -32700
        assert JsonRpcError.INVALID_REQUEST == -32600
        assert JsonRpcError.METHOD_NOT_FOUND == -32601
        assert JsonRpcError.INVALID_PARAMS == -32602
        assert JsonRpcError.INTERNAL_ERROR == -32603

    def test_make_error(self):
        """Test error object creation."""
        error = JsonRpcError.make_error(-32600, "Invalid request")

        assert error["code"] == -32600
        assert error["message"] == "Invalid request"

    def test_make_error_with_data(self):
        """Test error object creation with data."""
        error = JsonRpcError.make_error(-32600, "Invalid request", {"details": "missing field"})

        assert error["code"] == -32600
        assert error["message"] == "Invalid request"
        assert error["data"] == {"details": "missing field"}


class TestServerModuleEntrypoint:
    """Test server package module entrypoint wiring."""

    def test_server_package_has_main_module_entrypoint(self):
        """`python -m poor_cli.server` requires `poor_cli.server.__main__`."""
        import poor_cli.server.__main__ as server_main

        assert callable(server_main.main)


class TestErrorSanitization:
    """Test server-side error message cleanup helpers."""

    def test_sanitize_exception_message_extracts_useful_provider_error(self):
        raw = (
            "Failed to send message: Gemini API error: 400 Bad Request. "
            "{'message': '{\\n"
            '  "error": {\\n'
            '    "code": 400,\\n'
            '    "message": "API key not valid. Please pass a valid API key.",\\n'
            '    "status": "INVALID_ARGUMENT",\\n'
            '    "details": [{"reason": "API_KEY_INVALID"}]\\n'
            "  }\\n"
            "}', 'status': 'Bad Request'}"
        )

        cleaned = _sanitize_exception_message(Exception(raw))

        assert "Failed to send message: Gemini API error: 400 Bad Request." in cleaned
        assert "API key not valid. Please pass a valid API key." in cleaned
        assert "(API_KEY_INVALID)" in cleaned
        assert "{'message':" not in cleaned

    def test_sanitize_exception_message_truncates_very_long_text(self):
        cleaned = _sanitize_exception_message(Exception("x" * 800))
        assert len(cleaned) <= 360
        assert cleaned.endswith("...")


class TestPoorCLIServer:
    """Test PoorCLIServer class."""

    @pytest.fixture
    def server(self):
        """Create a server instance for testing."""
        return PoorCLIServer()

    def test_init(self, server):
        """Test server initialization."""
        assert server.core is not None
        assert server.core.permission_callback is not None
        assert server.initialized is False
        assert len(server.handlers) > 0

    @pytest.mark.asyncio
    async def test_server_callback_denies_sensitive_tools_in_prompt_mode(self, server):
        """Prompt mode denies mutating tools without an interactive confirmer."""
        server.permission_mode = "prompt"

        callback = server.core.permission_callback
        assert callback is not None
        assert await callback("write_file", {"file_path": "x"}) is False
        assert await callback("edit_file", {"file_path": "x"}) is False
        assert await callback("delete_file", {"file_path": "x"}) is False
        assert await callback("bash", {"command": "echo hi"}) is False

    @pytest.mark.asyncio
    async def test_server_callback_allows_non_sensitive_tools_in_prompt_mode(self, server):
        """Prompt mode still allows read-only tools."""
        server.permission_mode = "prompt"

        callback = server.core.permission_callback
        assert callback is not None
        assert await callback("read_file", {"file_path": "x"}) is True

    @pytest.mark.asyncio
    async def test_server_callback_auto_safe_allows_only_allowlisted_bash_commands(self, server):
        server.permission_mode = "auto-safe"
        server.core.config = Config()

        callback = server.core.permission_callback
        assert callback is not None
        assert await callback("bash", {"command": "pwd"}) is True
        assert await callback("bash", {"command": "touch demo.txt"}) is False

    @pytest.mark.asyncio
    async def test_server_callback_denies_out_of_workspace_mutations(
        self,
        server,
        monkeypatch,
        tmp_path,
    ):
        server.permission_mode = "prompt"
        server.core.config = Config()
        monkeypatch.chdir(tmp_path)

        callback = server.core.permission_callback
        assert callback is not None
        with pytest.raises(PermissionDeniedError) as exc_info:
            await callback("write_file", {"file_path": str(tmp_path.parent / "outside.txt")})

        assert "trusted workspace" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_enforce_server_tool_permission_denies_dict_result(self, server):
        async def _deny_with_payload(tool_name, tool_args):
            del tool_name, tool_args
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}

        server.core.permission_callback = _deny_with_payload

        with pytest.raises(PermissionDeniedError):
            await server._enforce_server_tool_permission("bash", {"command": "pwd"})

    @pytest.mark.asyncio
    async def test_dispatch_and_respond_returns_internal_error_when_dispatch_raises(self, server):
        server.write_message_stdio = AsyncMock()
        message = JsonRpcMessage(id=7, method="poor-cli/chat", params={})

        with patch.object(server, "dispatch", AsyncMock(side_effect=RuntimeError("boom"))):
            await server._dispatch_and_respond(message)

        server.write_message_stdio.assert_awaited_once()
        response = server.write_message_stdio.await_args.args[0]
        assert response.id == 7
        assert response.error is not None
        assert response.error["code"] == JsonRpcError.INTERNAL_ERROR
        assert response.error["data"]["error_code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_handle_create_task_supports_execution_metadata_and_auto_approve(
        self,
        server,
        tmp_path,
        monkeypatch,
    ):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        _init_git_repo(repo_root)
        monkeypatch.chdir(repo_root)

        server.initialized = True
        server.core.config = Config()

        result = await server.handle_create_task(
            {
                "title": "Review repo",
                "prompt": "Review the repository",
                "sandboxPreset": "workspace-write",
                "autoStart": False,
                "autoApprove": True,
                "execution": {
                    "provider": "openai",
                    "model": "gpt-5",
                    "configPath": ".poor-cli/task-config.yaml",
                    "contextFiles": ["README.md"],
                    "pinnedContextFiles": ["docs/PLAN.md"],
                    "contextBudgetTokens": 4096,
                },
            }
        )

        task = result["task"]
        assert task["status"] == "queued"
        assert task["approvedAt"] is not None
        assert task["metadata"]["execution"] == {
            "provider": "openai",
            "model": "gpt-5",
            "configPath": ".poor-cli/task-config.yaml",
            "contextFiles": ["README.md"],
            "pinnedContextFiles": ["docs/PLAN.md"],
            "contextBudgetTokens": 4096,
        }

    @pytest.mark.asyncio
    async def test_handle_start_task_starts_queued_task(self, server, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        _init_git_repo(repo_root)

        manager = TaskManager(repo_root)
        task = manager.create_task(
            title="Review repo",
            prompt="Review the repository",
            sandbox_preset="review-only",
            source="manual",
        )

        with patch.object(TaskManager, "_pid_is_running", return_value=True):
            running = manager.mark_running(task.task_id, worker_pid=321)
        server.initialized = True
        server._task_manager = manager

        with patch.object(manager, "start_task_process", return_value=running) as start_mock:
            result = await server.handle_start_task({"taskId": task.task_id})

        start_mock.assert_called_once_with(task.task_id)
        assert result["task"]["status"] == "running"
        assert result["task"]["workerPid"] == 321

    @pytest.mark.asyncio
    async def test_handle_approve_task_respects_auto_start_flag(self, server, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        _init_git_repo(repo_root)

        manager = TaskManager(repo_root)
        task = manager.create_task(
            title="Apply patch",
            prompt="Apply the requested patch",
            sandbox_preset="workspace-write",
            source="manual",
            requires_approval=True,
        )

        server.initialized = True
        server._task_manager = manager

        result = await server.handle_approve_task({"taskId": task.task_id, "autoStart": False})

        assert result["task"]["status"] == "queued"
        assert result["task"]["approvedAt"] is not None

    @pytest.mark.asyncio
    async def test_handle_shutdown_resolves_pending_reviews_and_shuts_core(self, server):
        server._running = True
        loop = asyncio.get_event_loop()
        permission_future = loop.create_future()
        plan_future = loop.create_future()
        server._pending_permissions["perm-1"] = permission_future
        server._pending_plans["plan-1"] = plan_future
        server.core.shutdown = AsyncMock()

        with (
            patch.object(server, "_shutdown_background_tasks", AsyncMock()) as bg_mock,
            patch.object(server, "_shutdown_host_server_locked", AsyncMock()) as host_mock,
            patch.object(server, "_shutdown_managed_services_locked", AsyncMock()) as svc_mock,
        ):
            await server.handle_shutdown({})

        assert permission_future.result() == {
            "allowed": False,
            "approvedPaths": [],
            "approvedChunks": [],
        }
        assert plan_future.result() is False
        assert server._pending_permissions == {}
        assert server._pending_plans == {}
        bg_mock.assert_awaited_once()
        host_mock.assert_awaited_once()
        svc_mock.assert_awaited_once()
        server.core.shutdown.assert_awaited_once()
        assert server._running is False

    @pytest.mark.asyncio
    async def test_handle_create_automation_supports_execution_metadata(
        self,
        server,
        tmp_path,
        monkeypatch,
    ):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        _init_git_repo(repo_root)
        monkeypatch.chdir(repo_root)

        server.initialized = True

        created = await server.handle_create_automation(
            {
                "name": "Daily QA",
                "prompt": "Run the QA checklist",
                "schedule": {"kind": "daily", "hour": 9, "minute": 30},
                "sandboxPreset": "workspace-write",
                "autoApprove": True,
                "execution": {
                    "provider": "openai",
                    "model": "gpt-5",
                    "contextFiles": ["README.md"],
                },
            }
        )
        automation_id = created["automation"]["automationId"]
        listed = await server.handle_list_automations({})
        fetched = await server.handle_get_automation({"automationId": automation_id})

        assert created["automation"]["requiresApproval"] is False
        assert created["automation"]["metadata"]["autoApprove"] is True
        assert created["automation"]["metadata"]["execution"] == {
            "provider": "openai",
            "model": "gpt-5",
            "contextFiles": ["README.md"],
        }
        assert any(item["automationId"] == automation_id for item in listed["automations"])
        assert fetched["automation"]["automationId"] == automation_id

    @pytest.mark.asyncio
    async def test_handle_set_automation_enabled_and_run_handlers(self, server, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        _init_git_repo(repo_root)

        task_manager = TaskManager(repo_root)
        automation_manager = AutomationManager(repo_root, task_manager=task_manager)
        automation = automation_manager.create_automation(
            name="Repo review",
            prompt="Inspect the repository",
            schedule={"kind": "interval", "minutes": 60},
            sandbox_preset="review-only",
            requires_approval=True,
        )

        server.initialized = True
        server._task_manager = task_manager
        server._automation_manager = automation_manager

        disabled = await server.handle_set_automation_enabled(
            {"automationId": automation.automation_id, "enabled": False}
        )
        enabled = await server.handle_set_automation_enabled(
            {"automationId": automation.automation_id, "enabled": True}
        )
        run_now = await server.handle_run_automation_now({"automationId": automation.automation_id})

        due_task = task_manager.create_task(
            title="Due task",
            prompt="Summarize the repo",
            sandbox_preset="review-only",
            source="automation",
            requires_approval=True,
        )
        with patch.object(automation_manager, "run_due", return_value=[due_task]) as run_due_mock:
            run_due = await server.handle_run_due_automations({"limit": 5})

        run_due_mock.assert_called_once_with(limit=5)
        assert disabled["automation"]["enabled"] is False
        assert enabled["automation"]["enabled"] is True
        assert run_now["task"]["source"] == "automation"
        assert run_due["tasks"][0]["taskId"] == due_task.task_id

    def test_has_required_handlers(self, server):
        """Test that required handlers are registered."""
        required = [
            "initialize",
            "shutdown",
            "poor-cli/chat",
            "poor-cli/previewContext",
            "poor-cli/inlineComplete",
            "poor-cli/getProviderInfo",
            "poor-cli/setApiKey",
            "poor-cli/getApiKeyStatus",
            "poor-cli/listSessions",
            "poor-cli/listCheckpoints",
            "poor-cli/exportConversation",
            "poor-cli/startTask",
            "poor-cli/createAutomation",
            "poor-cli/listAutomations",
            "poor-cli/getAutomation",
            "poor-cli/setAutomationEnabled",
            "poor-cli/runAutomationNow",
            "poor-cli/runDueAutomations",
            "poor-cli/startHostServer",
            "poor-cli/getHostServerStatus",
            "poor-cli/stopHostServer",
            "poor-cli/listHostMembers",
            "poor-cli/removeHostMember",
            "poor-cli/setHostMemberRole",
            "poor-cli/startService",
            "poor-cli/stopService",
            "poor-cli/getServiceStatus",
            "poor-cli/getServiceLogs",
        ]

        for method in required:
            assert method in server.handlers, f"Missing handler: {method}"

    @pytest.mark.asyncio
    async def test_handle_set_config_reloads_mcp_servers(self, server):
        server.initialized = True
        server.core.config = Config()
        server.core.config.mcp_servers = {
            "demo": {
                "command": "demo-mcp",
                "enabled": True,
                "allow_tools": [],
                "deny_tools": [],
            }
        }
        server.core._config_manager = MagicMock()
        server.core._config_manager.config = server.core.config
        server.core._config_manager.validate = MagicMock()
        server.core._config_manager.save = MagicMock()
        server.core.reload_mcp_servers = AsyncMock(return_value={"configuredServers": 1})

        result = await server.handle_set_config(
            {"keyPath": "mcp_servers.demo.enabled", "value": False}
        )

        assert result["success"] is True
        assert server.core.config.mcp_servers["demo"]["enabled"] is False
        server.core.reload_mcp_servers.assert_awaited_once()
        server.core._config_manager.validate.assert_called_once()
        server.core._config_manager.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_host_server_lifecycle_start_status_stop(self, server):
        """In-process host lifecycle returns shareable room join details."""
        server.initialized = True
        _FakeMultiplayerHost.instances.clear()

        with (
            patch.dict(
                sys.modules,
                {"poor_cli.multiplayer": SimpleNamespace(MultiplayerHost=_FakeMultiplayerHost)},
            ),
            patch.object(server, "_is_port_bindable", return_value=True),
            patch.object(server, "_resolve_multiplayer_share_host", return_value="192.168.1.42"),
        ):
            started = await server.handle_start_host_server(
                {"room": "dev", "bindHost": "0.0.0.0", "port": 8765}
            )
            status = await server.handle_get_host_server_status({})
            stopped = await server.handle_stop_host_server({})

        assert started["running"] is True
        assert started["created"] is True
        assert started["shareWsUrl"] == "ws://192.168.1.42:8765/rpc"
        assert started["rooms"][0]["name"] == "dev"
        assert "poor-cli --remote-url" in started["rooms"][0]["viewerJoinCommand"]
        assert status["running"] is True
        assert stopped["running"] is False
        assert stopped["stopped"] is True
        assert _FakeMultiplayerHost.instances[-1].stopped is True

    @pytest.mark.asyncio
    async def test_host_server_start_is_idempotent_when_already_running(self, server):
        """Starting host twice returns existing host details without recreating."""
        server.initialized = True
        _FakeMultiplayerHost.instances.clear()

        with (
            patch.dict(
                sys.modules,
                {"poor_cli.multiplayer": SimpleNamespace(MultiplayerHost=_FakeMultiplayerHost)},
            ),
            patch.object(server, "_is_port_bindable", return_value=True),
            patch.object(server, "_resolve_multiplayer_share_host", return_value="192.168.1.42"),
        ):
            first = await server.handle_start_host_server({"room": "dev", "port": 8765})
            second = await server.handle_start_host_server({"room": "docs", "port": 9000})
            await server.handle_stop_host_server({})

        assert first["created"] is True
        assert second["created"] is False
        assert len(_FakeMultiplayerHost.instances) == 1

    @pytest.mark.asyncio
    async def test_pair_start_returns_canonical_room_payload(self, server):
        """Pair start should reuse canonical room join data from host status payload."""
        server.initialized = True
        _FakeMultiplayerHost.instances.clear()

        with (
            patch.dict(
                sys.modules,
                {"poor_cli.multiplayer": SimpleNamespace(MultiplayerHost=_FakeMultiplayerHost)},
            ),
            patch.object(server, "_is_port_bindable", return_value=True),
            patch.object(server, "_resolve_multiplayer_share_host", return_value="192.168.1.42"),
        ):
            pair = await server.handle_pair_start({})
            await server.handle_stop_host_server({})

        assert pair["room"]["name"] == pair["shortCode"]
        assert pair["room"]["joinWsUrl"] == "ws://192.168.1.42:8765/rpc"
        assert pair["wsUrl"] == pair["room"]["joinWsUrl"]
        assert pair["viewerToken"] == pair["room"]["viewerToken"]
        assert pair["inviteCode"] == pair["room"]["viewerInviteCode"]

    @pytest.mark.asyncio
    async def test_host_member_admin_controls_list_role_remove(self, server):
        """Host admin handlers can list members, change role, and remove users."""
        server.initialized = True
        _FakeMultiplayerHost.instances.clear()

        with (
            patch.dict(
                sys.modules,
                {"poor_cli.multiplayer": SimpleNamespace(MultiplayerHost=_FakeMultiplayerHost)},
            ),
            patch.object(server, "_is_port_bindable", return_value=True),
            patch.object(server, "_resolve_multiplayer_share_host", return_value="192.168.1.42"),
        ):
            await server.handle_start_host_server({"room": "dev", "port": 8765})
            members = await server.handle_list_host_members({})
            assert members["running"] is True
            assert members["rooms"][0]["name"] == "dev"
            assert members["rooms"][0]["memberCount"] == 1

            target_id = members["rooms"][0]["members"][0]["connectionId"]
            role_update = await server.handle_set_host_member_role(
                {"connectionId": target_id, "role": "prompter"}
            )
            assert role_update["success"] is True
            assert role_update["role"] == "prompter"

            removed = await server.handle_remove_host_member({"connectionId": target_id})
            assert removed["success"] is True
            assert removed["removed"] is True

            refreshed = await server.handle_list_host_members({"room": "dev"})
            assert refreshed["rooms"][0]["memberCount"] == 0
            await server.handle_stop_host_server({})

    @pytest.mark.asyncio
    async def test_host_member_role_requires_explicit_room_when_multiple_rooms(self, server):
        """Role updates without room are rejected when multiple rooms are active."""
        server.initialized = True
        _FakeMultiplayerHost.instances.clear()

        with (
            patch.dict(
                sys.modules,
                {"poor_cli.multiplayer": SimpleNamespace(MultiplayerHost=_FakeMultiplayerHost)},
            ),
            patch.object(server, "_is_port_bindable", return_value=True),
            patch.object(server, "_resolve_multiplayer_share_host", return_value="192.168.1.42"),
        ):
            await server.handle_start_host_server({"rooms": ["dev", "docs"], "port": 8765})

            with pytest.raises(InvalidParamsError):
                await server.handle_set_host_member_role(
                    {"connectionId": "dev-viewer", "role": "prompter"}
                )

            await server.handle_stop_host_server({})

    @pytest.mark.asyncio
    async def test_service_lifecycle_start_status_logs_stop(self, server, tmp_path):
        """Managed service controls expose start/status/logs/stop over RPC handlers."""
        server.initialized = True
        fake_process = _FakeManagedProcess()
        spawn_mock = AsyncMock(return_value=fake_process)

        with (
            patch.object(server, "_service_logs_dir", tmp_path / "services"),
            patch.object(server, "_resolve_service_executable", return_value="/usr/bin/fake"),
            patch("poor_cli._server.asyncio.create_subprocess_exec", spawn_mock),
            patch.object(server, "_is_ollama_reachable", return_value=False),
            patch("poor_cli._server.asyncio.sleep", AsyncMock(return_value=None)),
        ):
            started = await server.handle_start_service(
                {"name": "demo", "command": "demo-server --port 9000"}
            )
            status = await server.handle_get_service_status({"name": "demo"})

            log_path = Path(started["logPath"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")
            logs = await server.handle_get_service_logs({"name": "demo", "lines": 2})
            stopped = await server.handle_stop_service({"name": "demo"})

        assert started["service"] == "demo"
        assert started["running"] is True
        assert started["managed"] is True
        assert started["created"] is True
        assert status["running"] is True
        assert "line-2" in logs["content"]
        assert "line-3" in logs["content"]
        assert stopped["stopped"] is True
        assert stopped["running"] is False
        assert fake_process.terminated is True
        assert server._managed_services["demo"].log_handle is None
        if hasattr(os, "killpg"):
            assert spawn_mock.await_args.kwargs["start_new_session"] is True

    @pytest.mark.asyncio
    async def test_service_status_reconciles_exited_managed_process(self, server, tmp_path):
        server.initialized = True
        fake_process = _FakeManagedProcess()
        spawn_mock = AsyncMock(return_value=fake_process)

        with (
            patch.object(server, "_service_logs_dir", tmp_path / "services"),
            patch.object(server, "_resolve_service_executable", return_value="/usr/bin/fake"),
            patch("poor_cli._server.asyncio.create_subprocess_exec", spawn_mock),
            patch.object(server, "_is_ollama_reachable", return_value=False),
            patch("poor_cli._server.asyncio.sleep", AsyncMock(return_value=None)),
        ):
            started = await server.handle_start_service(
                {"name": "demo", "command": "demo-server --port 9000"}
            )
            runtime = server._managed_services["demo"]
            runtime.process.returncode = 7

            status = await server.handle_get_service_status({"name": "demo"})

        assert started["running"] is True
        assert status["running"] is False
        assert status["managedRunning"] is False
        assert status["exitCode"] == 7
        assert runtime.log_handle is None

    @pytest.mark.asyncio
    async def test_start_service_rejects_untrusted_cwd(self, server, tmp_path, monkeypatch):
        server.initialized = True
        server.core.config = Config()
        trusted_root = tmp_path / "trusted"
        trusted_root.mkdir()
        outside_root = tmp_path / "outside"
        outside_root.mkdir()
        monkeypatch.chdir(trusted_root)

        with patch.object(server, "_resolve_service_executable", return_value="/usr/bin/fake"):
            with pytest.raises(InvalidParamsError, match="trusted workspace roots"):
                await server.handle_start_service(
                    {
                        "name": "demo",
                        "command": "demo-server",
                        "cwd": str(outside_root),
                    }
                )

    @pytest.mark.asyncio
    async def test_start_service_rejects_inherited_untrusted_cwd(self, server, tmp_path, monkeypatch):
        server.initialized = True
        server.core.config = Config()
        trusted_root = tmp_path / "trusted"
        trusted_root.mkdir()
        outside_root = tmp_path / "outside"
        outside_root.mkdir()
        monkeypatch.chdir(trusted_root)

        server._managed_services["demo"] = SimpleNamespace(
            name="demo",
            command=["/usr/bin/fake", "serve"],
            command_display="/usr/bin/fake serve",
            cwd=str(outside_root),
            process=SimpleNamespace(pid=9999, returncode=0),
            log_path=tmp_path / "services" / "demo.log",
            log_handle=None,
            started_at="now",
            last_exit_code=0,
        )

        with pytest.raises(InvalidParamsError, match="trusted workspace roots"):
            await server.handle_start_service({"name": "demo"})

    @pytest.mark.asyncio
    async def test_start_service_rotates_oversized_log_before_spawn(self, server, tmp_path):
        server.initialized = True
        fake_process = _FakeManagedProcess(pid=9876)
        spawn_mock = AsyncMock(return_value=fake_process)
        log_dir = tmp_path / "services"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "demo.log"
        log_path.write_text("stale log\n", encoding="utf-8")

        with (
            patch.object(server, "_service_logs_dir", log_dir),
            patch.object(server, "_service_log_rotation_threshold_bytes", return_value=4),
            patch.object(server, "_resolve_service_executable", return_value="/usr/bin/fake"),
            patch("poor_cli._server.asyncio.create_subprocess_exec", spawn_mock),
            patch.object(server, "_is_ollama_reachable", return_value=False),
            patch("poor_cli._server.asyncio.sleep", AsyncMock(return_value=None)),
        ):
            started = await server.handle_start_service(
                {"name": "demo", "command": "demo-server --port 9000"}
            )
            await server.handle_stop_service({"name": "demo"})

        rotated_path = log_dir / "demo.log.1"
        assert started["logPath"] == str(log_path)
        assert rotated_path.read_text(encoding="utf-8") == "stale log\n"
        assert log_path.exists()

    @pytest.mark.asyncio
    async def test_start_service_ollama_uses_default_command(self, server, tmp_path):
        """Ollama service can be started without an explicit command string."""
        server.initialized = True
        fake_process = _FakeManagedProcess(pid=9999)
        spawn_mock = AsyncMock(return_value=fake_process)

        with (
            patch.object(server, "_service_logs_dir", tmp_path / "services"),
            patch.object(server, "_resolve_service_executable", return_value="/usr/bin/ollama"),
            patch.object(server, "_is_ollama_reachable", return_value=False),
            patch("poor_cli._server.asyncio.create_subprocess_exec", spawn_mock),
            patch("poor_cli._server.asyncio.sleep", AsyncMock(return_value=None)),
        ):
            started = await server.handle_start_service({"name": "ollama"})
            await server.handle_stop_service({"name": "ollama"})

        assert started["service"] == "ollama"
        assert started["running"] is True
        assert started["created"] is True
        spawn_args = spawn_mock.await_args.args
        assert Path(spawn_args[0]).name == "ollama"
        assert spawn_args[1] == "serve"

    def test_list_ollama_models_parses_and_deduplicates(self, server):
        """Installed model names are extracted from /api/tags payload."""
        payload = {
            "models": [
                {"name": "llama2:7b"},
                {"name": "mistral:7b"},
                {"name": "llama2:7b"},
                {"name": ""},
                {},
            ]
        }
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(payload).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False

        with patch("poor_cli._server.urlopen", return_value=fake_context):
            models = server._list_ollama_models("http://localhost:11434")

        assert models == ["llama2:7b", "mistral:7b"]

    @pytest.mark.asyncio
    async def test_handle_list_providers_prefers_installed_ollama_models(self, server):
        """Provider listing surfaces live Ollama models when endpoint is reachable."""
        from poor_cli.providers.provider_factory import ProviderFactory
        from poor_cli.config import Config

        fake_providers = {"ollama": object(), "openai": object()}
        fake_info = {"available": True}
        config = Config()
        config_manager = MagicMock()
        config_manager.get_api_key.side_effect = lambda provider: (
            "sk-openai" if provider == "openai" else None
        )

        with (
            patch.object(ProviderFactory, "list_providers", return_value=fake_providers),
            patch.object(ProviderFactory, "get_provider_info", return_value=fake_info),
            patch.object(server, "_is_ollama_reachable", return_value=True),
            patch.object(server, "_list_ollama_models", return_value=["llama2:7b"]),
            patch.object(server, "_ensure_config_loaded", return_value=(config_manager, config)),
        ):
            providers = await server.handle_list_providers({})

        assert providers["ollama"]["models"] == ["llama2:7b"]
        assert providers["ollama"]["ready"] is True
        assert providers["ollama"]["statusLabel"] == "service up"
        assert providers["openai"]["models"] == ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
        assert providers["openai"]["ready"] is True
        assert providers["openai"]["statusLabel"] == "API key configured"

    @pytest.mark.asyncio
    async def test_list_sessions_serializes_active_and_completed(self, server):
        """Session listing returns active marker and message counts."""
        server.initialized = True
        active = SimpleNamespace(
            session_id="session-active",
            started_at="2026-03-04T10:00:00",
            ended_at=None,
            model="gemini-test",
            messages=[1, 2],
        )
        completed = SimpleNamespace(
            session_id="session-done",
            started_at="2026-03-03T10:00:00",
            ended_at="2026-03-03T10:05:00",
            model="gemini-test",
            messages=[1],
        )
        repo_config = SimpleNamespace(
            current_session=active,
            list_sessions=MagicMock(return_value=[active, completed]),
        )

        with patch.object(server, "_get_repo_config", return_value=repo_config):
            result = await server.handle_list_sessions({"limit": 10})

        assert result["activeSessionId"] == "session-active"
        assert result["sessions"][0]["isActive"] is True
        assert result["sessions"][0]["messageCount"] == 2
        assert result["sessions"][1]["isActive"] is False

    @pytest.mark.asyncio
    async def test_handle_chat_logs_request_start_and_complete(self, server):
        """Sync chat handler logs request metadata for easier debugging."""
        server.initialized = True
        server.core.send_message_sync = AsyncMock(return_value="pong")

        with patch.object(server.logger, "info") as info_mock:
            result = await server.handle_chat(
                {
                    "message": "ping!",
                    "requestId": "req-sync-1",
                    "contextFiles": ["a.py", "b.py"],
                    "pinnedContextFiles": ["README.md"],
                    "contextBudgetTokens": 3200,
                }
            )

        assert result == {"content": "pong", "role": "assistant"}
        server.core.send_message_sync.assert_awaited_once_with(
            message="ping!",
            context_files=["a.py", "b.py"],
            pinned_context_files=["README.md"],
            context_budget_tokens=3200,
        )
        start_call = next(
            (call for call in info_mock.call_args_list if call.args[0].startswith("chat_start mode=sync")),
            None,
        )
        complete_call = next(
            (
                call
                for call in info_mock.call_args_list
                if call.args[0].startswith("chat_complete mode=sync")
            ),
            None,
        )
        assert start_call is not None
        assert complete_call is not None
        assert start_call.args[1] == "req-sync-1"
        assert start_call.args[2] == len("ping!")
        assert start_call.args[3] == 3
        assert complete_call.args[1] == "req-sync-1"
        assert complete_call.args[2] == len("pong")

    @pytest.mark.asyncio
    async def test_handle_chat_streaming_logs_request_start_and_complete(self, server):
        """Streaming chat handler logs request metadata for easier debugging."""
        from poor_cli.core import CoreEvent

        server.initialized = True
        server.write_message_stdio = AsyncMock()
        captured = {}

        async def fake_send_message_events(
            *,
            message,
            context_files=None,
            pinned_context_files=None,
            context_budget_tokens=None,
            request_id="",
        ):
            captured.update(
                {
                    "message": message,
                    "context_files": context_files,
                    "pinned_context_files": pinned_context_files,
                    "context_budget_tokens": context_budget_tokens,
                    "request_id": request_id,
                }
            )
            yield CoreEvent.text_chunk("hello ", request_id)
            yield CoreEvent.text_chunk("world", request_id)
            yield CoreEvent.done("complete")

        with (
            patch.object(server.core, "send_message_events", fake_send_message_events),
            patch.object(server.logger, "info") as info_mock,
        ):
            result = await server.handle_chat_streaming(
                {
                    "message": "stream this",
                    "requestId": "req-stream-1",
                    "contextFiles": ["ctx.py"],
                    "pinnedContextFiles": ["README.md"],
                    "contextBudgetTokens": 4096,
                }
            )

        assert result == {"content": "hello world", "role": "assistant"}
        start_call = next(
            (
                call
                for call in info_mock.call_args_list
                if call.args[0].startswith("chat_start mode=stream")
            ),
            None,
        )
        complete_call = next(
            (
                call
                for call in info_mock.call_args_list
                if call.args[0].startswith("chat_complete mode=stream")
            ),
            None,
        )
        assert start_call is not None
        assert complete_call is not None
        assert captured == {
            "message": "stream this",
            "context_files": ["ctx.py"],
            "pinned_context_files": ["README.md"],
            "context_budget_tokens": 4096,
            "request_id": "req-stream-1",
        }
        assert start_call.args[1] == "req-stream-1"
        assert start_call.args[2] == len("stream this")
        assert start_call.args[3] == 2
        assert complete_call.args[1] == "req-stream-1"
        assert complete_call.args[2] == len("hello world")

    @pytest.mark.asyncio
    async def test_streaming_reviews_fail_fast_when_client_capability_is_disabled(self, server):
        server.initialized = True
        server.write_message_stdio = AsyncMock()
        server._client_capabilities = {
            "reviewFlows": {
                "permissionRequests": False,
                "planReview": False,
            }
        }

        permission_result = await server._streaming_permission_callback(
            "bash",
            {"command": "pwd"},
            {"requestId": "req-1"},
        )
        plan_result = await server._streaming_plan_callback(
            {
                "requestId": "req-1",
                "summary": "write files",
                "originalRequest": "update repo",
                "steps": ["edit foo.py"],
            }
        )

        assert permission_result == {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        assert plan_result is False
        server.write_message_stdio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_streaming_permission_callback_auto_safe_uses_allowlist(self, server):
        server.initialized = True
        server.permission_mode = "auto-safe"
        server.core.config = Config()
        server.write_message_stdio = AsyncMock()

        allowed = await server._streaming_permission_callback(
            "bash",
            {"command": "pwd"},
            {"requestId": "req-safe"},
        )
        denied = await server._streaming_permission_callback(
            "bash",
            {"command": "touch demo.txt"},
            {"requestId": "req-unsafe"},
        )

        assert allowed == {"allowed": True, "approvedPaths": [], "approvedChunks": []}
        assert denied == {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        server.write_message_stdio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_preview_context_forwards_paths_and_budget(self, server):
        server.initialized = True
        server.core.preview_context = AsyncMock(
            return_value={"files": [], "totalTokens": 0, "truncated": False, "message": "ok"}
        )

        result = await server.handle_preview_context(
            {
                "message": "review this",
                "contextFiles": ["a.py"],
                "pinnedContextFiles": ["README.md"],
                "contextBudgetTokens": 6000,
            }
        )

        assert result["message"] == "ok"
        server.core.preview_context.assert_awaited_once_with(
            message="review this",
            context_files=["a.py"],
            pinned_context_files=["README.md"],
            context_budget_tokens=6000,
        )

    @pytest.mark.asyncio
    async def test_handle_preview_mutation_forwards_tool_name_and_args(self, server):
        server.initialized = True
        server.core.preview_mutation = AsyncMock(
            return_value={
                "ok": True,
                "operation": "edit_file",
                "paths": ["/tmp/demo.py"],
                "diff": "--- /tmp/demo.py\n+++ /tmp/demo.py\n",
                "checkpointId": None,
                "changed": True,
                "message": "Preview edit /tmp/demo.py",
            }
        )

        result = await server.handle_preview_mutation(
            {
                "toolName": "edit_file",
                "toolArgs": {"file_path": "/tmp/demo.py", "old_text": "old", "new_text": "new"},
            }
        )

        assert result["operation"] == "edit_file"
        assert result["paths"] == ["/tmp/demo.py"]
        server.core.preview_mutation.assert_awaited_once_with(
            tool_name="edit_file",
            arguments={"file_path": "/tmp/demo.py", "old_text": "old", "new_text": "new"},
        )

    @pytest.mark.asyncio
    async def test_handle_apply_edit_returns_structured_outcome(self, server):
        server.initialized = True
        server.permission_mode = "danger-full-access"
        server.core.apply_edit_outcome = AsyncMock(
            return_value=ToolOutcome(
                ok=True,
                operation="edit_file",
                path="/tmp/example.py",
                changed=True,
                diff="--- /tmp/example.py\n+++ /tmp/example.py\n",
                checkpoint_id="cp_123",
                message="Edited /tmp/example.py",
                metadata={"mode": "exact_replace"},
            )
        )

        result = await server.handle_apply_edit(
            {"filePath": "/tmp/example.py", "oldText": "a", "newText": "b"}
        )

        assert result["success"] is True
        assert result["checkpointId"] == "cp_123"
        assert result["diff"].startswith("--- /tmp/example.py")
        assert result["metadata"]["mode"] == "exact_replace"

    @pytest.mark.asyncio
    async def test_compare_files_returns_unified_diff(self, server, tmp_path):
        """File comparison endpoint returns unified diff output."""
        server.initialized = True
        left = tmp_path / "left.txt"
        right = tmp_path / "right.txt"
        left.write_text("line-a\nline-b\n", encoding="utf-8")
        right.write_text("line-a\nline-c\n", encoding="utf-8")

        result = await server.handle_compare_files(
            {"file1": str(left), "file2": str(right)}
        )

        assert "---" in result["diff"]
        assert "+++" in result["diff"]
        assert "-line-b" in result["diff"]
        assert "+line-c" in result["diff"]

    @pytest.mark.asyncio
    async def test_export_conversation_writes_output_file(self, server, tmp_path, monkeypatch):
        """Conversation export writes a file and returns file metadata."""
        server.initialized = True
        monkeypatch.chdir(tmp_path)

        server.core.config = SimpleNamespace(
            model=SimpleNamespace(provider="gemini", model_name="gemini-test"),
            history=SimpleNamespace(auto_migrate_legacy_history=True),
        )
        current_session = SimpleNamespace(session_id="session-12345678")
        repo_config = SimpleNamespace(
            current_session=current_session,
            get_recent_messages=MagicMock(
                return_value=[
                    SimpleNamespace(
                        role="user",
                        content="hello",
                        timestamp="2026-03-04T10:00:00",
                    ),
                    SimpleNamespace(
                        role="assistant",
                        content="world",
                        timestamp="2026-03-04T10:00:01",
                    ),
                ]
            ),
        )

        with patch.object(server, "_get_repo_config", return_value=repo_config):
            result = await server.handle_export_conversation({"format": "json"})

        output_path = tmp_path / Path(result["filePath"]).name
        assert output_path.exists()
        assert result["messageCount"] == 2
        assert result["sizeBytes"] > 0

    @pytest.mark.asyncio
    async def test_dispatch_invalid_request(self, server):
        """Test dispatching request without method."""
        message = JsonRpcMessage(id=1)  # No method

        response = await server.dispatch(message)

        assert response.error is not None
        assert response.error["code"] == JsonRpcError.INVALID_REQUEST
        assert response.error["data"]["error_code"] == "INVALID_REQUEST"

    @pytest.mark.asyncio
    async def test_dispatch_method_not_found(self, server):
        """Test dispatching unknown method."""
        message = JsonRpcMessage(id=1, method="unknownMethod")

        response = await server.dispatch(message)

        assert response.error is not None
        assert response.error["code"] == JsonRpcError.METHOD_NOT_FOUND
        assert response.error["data"]["error_code"] == "METHOD_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_dispatch_text_document_completion_not_supported(self, server):
        """Test that legacy LSP completion alias is not supported."""
        message = JsonRpcMessage(id=1, method="textDocument/completion")

        response = await server.dispatch(message)

        assert response.error is not None
        assert response.error["code"] == JsonRpcError.METHOD_NOT_FOUND
        assert response.error["data"]["error_code"] == "METHOD_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_dispatch_shutdown(self, server):
        """Test shutdown handler via dispatch."""
        message = JsonRpcMessage(id=1, method="shutdown")

        response = await server.dispatch(message)

        # Shutdown returns None result
        assert response.error is None

    @pytest.mark.asyncio
    async def test_run_stdio_eof_resolves_pending_reviews_and_shuts_core(self, server):
        loop = asyncio.get_event_loop()
        permission_future = loop.create_future()
        plan_future = loop.create_future()
        server._pending_permissions["perm-1"] = permission_future
        server._pending_plans["plan-1"] = plan_future
        server.core.shutdown = AsyncMock()

        async def _read_eof():
            server._transport.last_error = None
            return None

        with (
            patch.object(server, "read_message_stdio", _read_eof),
            patch.object(server, "_shutdown_background_tasks", AsyncMock()) as bg_mock,
            patch.object(server, "_shutdown_host_server_locked", AsyncMock()) as host_mock,
            patch.object(server, "_shutdown_managed_services_locked", AsyncMock()) as svc_mock,
        ):
            await server.run_stdio()

        assert permission_future.result() == {
            "allowed": False,
            "approvedPaths": [],
            "approvedChunks": [],
        }
        assert plan_future.result() is False
        bg_mock.assert_awaited_once()
        host_mock.assert_awaited_once()
        svc_mock.assert_awaited_once()
        server.core.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_stdio_cancels_background_stream_tasks_on_exit(self, server):
        cancelled = asyncio.Event()
        sequence = [JsonRpcMessage(id=5, method="poor-cli/chatStreaming"), None]

        async def _read_messages():
            if len(sequence) == 1:
                await asyncio.sleep(0)
            message = sequence.pop(0)
            server._transport.last_error = None
            return message

        async def _dispatch_and_block(_message):
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        server.core.shutdown = AsyncMock()

        with (
            patch.object(server, "read_message_stdio", _read_messages),
            patch.object(server, "_dispatch_and_respond", _dispatch_and_block),
            patch.object(server, "_shutdown_host_server_locked", AsyncMock()),
            patch.object(server, "_shutdown_managed_services_locked", AsyncMock()),
        ):
            await server.run_stdio()

        assert cancelled.is_set()
        assert server._background_tasks == set()
        server.core.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_read_message_stdio_handles_fragmented_header_and_body(self, server, monkeypatch):
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "initialize",
                "params": {"provider": "gemini"},
            }
        )
        fragments = [
            "Cont",
            "ent-Len",
            "gth: ",
            str(len(body)),
            "\r",
            "\n",
            "\r\n",
            body[:5],
            body[5:17],
            body[17:],
        ]

        monkeypatch.setattr("poor_cli._server.sys.stdin", _FragmentedStdin(fragments))
        monkeypatch.setattr("poor_cli._server.asyncio.get_event_loop", lambda: _InlineEventLoop())

        message = await server.read_message_stdio()

        assert message is not None
        assert message.id == 7
        assert message.method == "initialize"
        assert message.params == {"provider": "gemini"}

    @pytest.mark.asyncio
    async def test_read_message_stdio_returns_none_for_incomplete_body(self, server, monkeypatch):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "shutdown"})
        fragments = [
            f"Content-Length: {len(body)}\r\n\r\n",
            body[:5],  # Intentionally truncated body stream
        ]

        monkeypatch.setattr("poor_cli._server.sys.stdin", _FragmentedStdin(fragments))
        monkeypatch.setattr("poor_cli._server.asyncio.get_event_loop", lambda: _InlineEventLoop())

        message = await server.read_message_stdio()

        assert message is None
        assert isinstance(server._transport.last_error, EOFError)

    @pytest.mark.asyncio
    async def test_read_message_stdio_records_invalid_json_parse_error(self, server, monkeypatch):
        body = '{"jsonrpc": "2.0", "id": 1, "method": '
        fragments = [f"Content-Length: {len(body)}\r\n\r\n", body]

        monkeypatch.setattr("poor_cli._server.sys.stdin", _FragmentedStdin(fragments))
        monkeypatch.setattr("poor_cli._server.asyncio.get_event_loop", lambda: _InlineEventLoop())

        message = await server.read_message_stdio()

        assert message is None
        assert isinstance(server._transport.last_error, json.JSONDecodeError)

    @pytest.mark.asyncio
    async def test_run_stdio_skips_malformed_message_and_continues(self, server):
        valid_message = JsonRpcMessage(id=11, method="shutdown")
        sequence = [("error", None), ("message", valid_message), ("eof", None)]

        async def _fake_read():
            kind, payload = sequence.pop(0)
            if kind == "error":
                server._transport.last_error = ValueError("bad json payload")
                return None
            server._transport.last_error = None
            return payload

        response = JsonRpcMessage(id=11, result={"ok": True})
        server.write_message_stdio = AsyncMock()

        with (
            patch.object(server, "read_message_stdio", _fake_read),
            patch.object(server, "dispatch", AsyncMock(return_value=response)) as dispatch_mock,
            patch.object(server.logger, "warning") as warning_mock,
        ):
            await server.run_stdio()

        dispatch_mock.assert_awaited_once_with(valid_message)
        server.write_message_stdio.assert_awaited_once_with(response)
        warning_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_accepts_permission_mode_param(self, server):
        """Test initialize stores requested permission mode for the session."""
        server.core.initialize = AsyncMock()
        server.core.get_provider_info = MagicMock(return_value={"name": "gemini"})

        result = await server.handle_initialize({"permissionMode": "auto-safe"})

        assert server.permission_mode == "auto-safe"
        assert result["capabilities"]["permissionMode"] == "auto-safe"

    @pytest.mark.asyncio
    async def test_initialize_reports_trusted_workspace_capabilities(
        self,
        server,
        monkeypatch,
        tmp_path,
    ):
        server.core.initialize = AsyncMock()
        server.core.get_provider_info = MagicMock(return_value={"name": "gemini"})
        monkeypatch.chdir(tmp_path)

        result = await server.handle_initialize({})

        assert result["capabilities"]["security"]["trustedWorkspaceBoundary"] is True
        assert result["capabilities"]["security"]["trustedRoots"] == [str(tmp_path.resolve())]

    @pytest.mark.asyncio
    async def test_initialize_reports_completion_streaming_and_log_path(self, server):
        server.core.initialize = AsyncMock()
        server.core.get_provider_info = MagicMock(
            return_value={"name": "gemini", "model": "gemini-2.5-pro"}
        )

        with patch.dict(
            "os.environ",
            {"POOR_CLI_SERVER_LOG_FILE": "/tmp/poor-cli-server.log"},
            clear=False,
        ):
            result = await server.handle_initialize(
                {
                    "clientCapabilities": {
                        "completion": {
                            "partialStreaming": True,
                        }
                    }
                }
            )

        capabilities = result["capabilities"]
        assert capabilities["completionStreamingProvider"] is True
        assert capabilities["serverLogPath"] == "/tmp/poor-cli-server.log"
        assert server._client_capabilities == {
            "completion": {
                "partialStreaming": True,
            }
        }

    @pytest.mark.asyncio
    async def test_initialize_rejects_invalid_permission_mode(self, server):
        """Test invalid initialize permissionMode returns INVALID_PARAMS."""
        server.core.initialize = AsyncMock()
        server.core.get_provider_info = MagicMock(return_value={"name": "gemini"})
        message = JsonRpcMessage(
            id=1,
            method="initialize",
            params={"permissionMode": "never-ask"},
        )

        response = await server.dispatch(message)

        assert response.error is not None
        assert response.error["code"] == JsonRpcError.INVALID_PARAMS
        assert response.error["data"]["error_code"] == "INVALID_PARAMS"

    @pytest.mark.asyncio
    async def test_execute_command_permission_denied_returns_structured_error(self, server):
        """Permission-denied command execution returns structured JSON-RPC error data."""
        server.initialized = True
        message = JsonRpcMessage(
            id=1,
            method="poor-cli/executeCommand",
            params={"command": "echo hello"},
        )

        response = await server.dispatch(message)

        assert response.error is not None
        assert response.error["code"] == JsonRpcError.INTERNAL_ERROR
        assert response.error["data"]["error_code"] == "permission_denied"
        assert response.error["data"]["tool"] == "bash"
        assert response.error["data"]["permission_mode"] == "prompt"

    @pytest.mark.asyncio
    async def test_apply_edit_permission_denied_returns_structured_error(self, server):
        """Permission-denied applyEdit returns structured JSON-RPC error data."""
        server.initialized = True
        message = JsonRpcMessage(
            id=2,
            method="poor-cli/applyEdit",
            params={
                "filePath": "example.py",
                "oldText": "a",
                "newText": "b",
            },
        )

        response = await server.dispatch(message)

        assert response.error is not None
        assert response.error["code"] == JsonRpcError.INTERNAL_ERROR
        assert response.error["data"]["error_code"] == "permission_denied"
        assert response.error["data"]["tool"] == "edit_file"
        assert response.error["data"]["permission_mode"] == "prompt"

    @pytest.mark.asyncio
    async def test_handle_get_config_includes_theme(self, server):
        """getConfig payload exposes ui.theme for TUI theming."""
        server.initialized = True
        server.core.get_provider_info = MagicMock(return_value={"name": "gemini", "model": "gemini-test"})
        server.core.config = SimpleNamespace(
            ui=SimpleNamespace(
                theme="light",
                enable_streaming=True,
                show_token_count=True,
                markdown_rendering=True,
                show_tool_calls=True,
                verbose_logging=False,
            ),
            plan_mode=SimpleNamespace(enabled=True),
            checkpoint=SimpleNamespace(enabled=True),
        )
        server.core._config_manager = SimpleNamespace(config_path="/tmp/config.yaml")

        result = await server.handle_get_config({})

        assert result["theme"] == "light"
        assert result["provider"] == "gemini"

    @pytest.mark.asyncio
    async def test_handle_set_api_key_updates_runtime_and_secure_store(self, server):
        server.initialized = True
        server.core.config = Config()
        server.core.config.model.provider = "openai"
        server.core.config.model.model_name = "gpt-4o"
        server.core._config_manager = SimpleNamespace(config=server.core.config)
        server.core.switch_provider = AsyncMock()

        fake_store = MagicMock()
        with (
            patch("poor_cli.api_key_manager.get_api_key_manager", return_value=fake_store),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await server.handle_set_api_key(
                {"provider": "openai", "apiKey": "sk-test-openai-key"}
            )
            assert os.environ["OPENAI_API_KEY"] == "sk-test-openai-key"

        assert result["success"] is True
        assert result["provider"] == "openai"
        assert result["activeProviderReloaded"] is True
        assert server.core.config.api_keys["openai"] == "sk-test-openai-key"
        fake_store.store_key.assert_called_once()
        server.core.switch_provider.assert_awaited_once_with("openai", "gpt-4o")

    @pytest.mark.asyncio
    async def test_handle_get_api_key_status_reports_sources(self, server):
        server.initialized = True
        server.core.config = Config()
        server.core.config.model.provider = "openai"
        server.core.config.api_keys["anthropic"] = "session-anthropic-key"

        fake_store = MagicMock()
        fake_store.list_providers.return_value = {"gemini": {"created_at": "now"}}
        fake_store.get_key.side_effect = lambda provider: (
            "secure-gemini-key" if provider == "gemini" else None
        )

        with (
            patch("poor_cli.api_key_manager.get_api_key_manager", return_value=fake_store),
            patch.dict("os.environ", {"OPENAI_API_KEY": "env-openai-key"}, clear=True),
        ):
            result = await server.handle_get_api_key_status({})

        providers = result["providers"]
        assert providers["openai"]["source"] == "environment"
        assert providers["openai"]["active"] is True
        assert providers["anthropic"]["source"] == "session"
        assert providers["gemini"]["source"] == "secure-store"
        assert providers["gemini"]["persisted"] is True

    @pytest.mark.asyncio
    async def test_handle_set_api_key_bootstraps_config_before_initialize(self, server):
        server.initialized = False
        server.core.switch_provider = AsyncMock()

        fake_store = MagicMock()
        with (
            patch("poor_cli.api_key_manager.get_api_key_manager", return_value=fake_store),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = await server.handle_set_api_key(
                {"provider": "gemini", "apiKey": "gm-test-key", "persist": False}
            )
            assert os.environ["GEMINI_API_KEY"] == "gm-test-key"

        assert result["success"] is True
        assert result["provider"] == "gemini"
        assert result["activeProviderReloaded"] is False
        assert server.core.config is not None
        assert server.core._config_manager is not None
        assert server.core.config.api_keys["gemini"] == "gm-test-key"
        fake_store.store_key.assert_not_called()
        server.core.switch_provider.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_get_api_key_status_works_before_initialize(self, server):
        server.initialized = False

        fake_store = MagicMock()
        fake_store.list_providers.return_value = {"openai": {"created_at": "now"}}
        fake_store.get_key.side_effect = lambda provider: (
            "secure-openai-key" if provider == "openai" else None
        )

        with (
            patch("poor_cli.api_key_manager.get_api_key_manager", return_value=fake_store),
            patch.dict("os.environ", {"GEMINI_API_KEY": "env-gemini-key"}, clear=True),
        ):
            result = await server.handle_get_api_key_status({})

        providers = result["providers"]
        assert providers["gemini"]["source"] == "environment"
        assert providers["gemini"]["configured"] is True
        assert providers["gemini"]["active"] is True
        assert providers["openai"]["source"] == "secure-store"
        assert providers["openai"]["persisted"] is True

    @pytest.mark.asyncio
    async def test_handle_inline_complete_streams_partial_chunks(self, server):
        server.initialized = True
        captured = {}

        async def _inline_complete(**kwargs):
            captured.update(kwargs)
            for chunk in ("return ", "value"):
                yield chunk

        server.core.inline_complete = _inline_complete
        server.write_message_stdio = AsyncMock()

        result = await server.handle_inline_complete(
            {
                "codeBefore": "def demo():\n    ",
                "codeAfter": "\n",
                "instruction": "",
                "filePath": "/tmp/demo.py",
                "language": "python",
                "requestId": "inline-123",
                "provider": "openai",
                "model": "gpt-5-codex",
                "streamPartial": True,
            }
        )

        assert result == {"completion": "return value", "isPartial": False}
        assert captured["request_id"] == "inline-123"
        assert captured["provider_name"] == "openai"
        assert captured["model_name"] == "gpt-5-codex"

        notifications = [call.args[0] for call in server.write_message_stdio.await_args_list]
        assert [message.method for message in notifications] == [
            "poor-cli/inlineChunk",
            "poor-cli/inlineChunk",
            "poor-cli/inlineChunk",
        ]
        assert notifications[0].params == {
            "requestId": "inline-123",
            "chunk": "return ",
            "done": False,
        }
        assert notifications[1].params == {
            "requestId": "inline-123",
            "chunk": "value",
            "done": False,
        }
        assert notifications[2].params == {
            "requestId": "inline-123",
            "chunk": "",
            "done": True,
        }

    @pytest.mark.asyncio
    async def test_handle_cancel_request_passes_request_id_to_core(self, server):
        server.core.cancel_request = MagicMock()

        result = await server.handle_cancel_request({"requestId": "req-42"})

        assert result == {"success": True, "requestId": "req-42"}
        server.core.cancel_request.assert_called_once_with("req-42")


class TestServerMain:
    """Test server CLI entrypoint behavior."""

    def test_stdio_flag_uses_stdio_transport(self, monkeypatch):
        """Test that --stdio runs the stdio transport."""
        monkeypatch.setattr("poor_cli._server.sys.argv", ["poor-cli-server", "--stdio"])
        mock_server = MagicMock()
        mock_server.run_stdio.return_value = "stdio-coro"

        with (
            patch("poor_cli._server.PoorCLIServer", return_value=mock_server),
            patch("poor_cli._server.asyncio.run") as mock_asyncio_run,
        ):
            main()

        mock_server.run_stdio.assert_called_once_with()
        mock_asyncio_run.assert_called_once_with("stdio-coro")

    def test_no_transport_flag_defaults_to_stdio(self, monkeypatch):
        """Test that no transport flag still runs stdio."""
        monkeypatch.setattr("poor_cli._server.sys.argv", ["poor-cli-server"])
        mock_server = MagicMock()
        mock_server.run_stdio.return_value = "stdio-coro"

        with (
            patch("poor_cli._server.PoorCLIServer", return_value=mock_server),
            patch("poor_cli._server.asyncio.run") as mock_asyncio_run,
        ):
            main()

        mock_server.run_stdio.assert_called_once_with()
        mock_asyncio_run.assert_called_once_with("stdio-coro")
