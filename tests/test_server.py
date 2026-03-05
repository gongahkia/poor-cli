"""
Tests for the JSON-RPC server.
"""

import json
import os
import sys
import pytest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.config import Config
from poor_cli.server import (
    PoorCLIServer,
    JsonRpcMessage,
    JsonRpcError,
    InvalidParamsError,
    _sanitize_exception_message,
    main,
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

    def test_has_required_handlers(self, server):
        """Test that required handlers are registered."""
        required = [
            "initialize",
            "shutdown",
            "poor-cli/chat",
            "poor-cli/inlineComplete",
            "poor-cli/getProviderInfo",
            "poor-cli/setApiKey",
            "poor-cli/getApiKeyStatus",
            "poor-cli/listSessions",
            "poor-cli/listCheckpoints",
            "poor-cli/exportConversation",
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

        fake_providers = {"ollama": object(), "openai": object()}
        fake_info = {"available": True}

        with (
            patch.object(ProviderFactory, "list_providers", return_value=fake_providers),
            patch.object(ProviderFactory, "get_provider_info", return_value=fake_info),
            patch.object(server, "_is_ollama_reachable", return_value=True),
            patch.object(server, "_list_ollama_models", return_value=["llama2:7b"]),
        ):
            providers = await server.handle_list_providers({})

        assert providers["ollama"]["models"] == ["llama2:7b"]
        assert providers["openai"]["models"] == ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]

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

    @pytest.mark.asyncio
    async def test_initialize_accepts_permission_mode_param(self, server):
        """Test initialize stores requested permission mode for the session."""
        server.core.initialize = AsyncMock()
        server.core.get_provider_info = MagicMock(return_value={"name": "gemini"})

        result = await server.handle_initialize({"permissionMode": "auto-safe"})

        assert server.permission_mode == "auto-safe"
        assert result["capabilities"]["permissionMode"] == "auto-safe"

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
