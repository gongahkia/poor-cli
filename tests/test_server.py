"""
Tests for the JSON-RPC server.
"""

import json
import os
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
        ]

        for method in required:
            assert method in server.handlers, f"Missing handler: {method}"

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

        monkeypatch.setattr("poor_cli.server.sys.stdin", _FragmentedStdin(fragments))
        monkeypatch.setattr("poor_cli.server.asyncio.get_event_loop", lambda: _InlineEventLoop())

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

        monkeypatch.setattr("poor_cli.server.sys.stdin", _FragmentedStdin(fragments))
        monkeypatch.setattr("poor_cli.server.asyncio.get_event_loop", lambda: _InlineEventLoop())

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
        monkeypatch.setattr("poor_cli.server.sys.argv", ["poor-cli-server", "--stdio"])
        mock_server = MagicMock()
        mock_server.run_stdio.return_value = "stdio-coro"

        with (
            patch("poor_cli.server.PoorCLIServer", return_value=mock_server),
            patch("poor_cli.server.asyncio.run") as mock_asyncio_run,
        ):
            main()

        mock_server.run_stdio.assert_called_once_with()
        mock_asyncio_run.assert_called_once_with("stdio-coro")

    def test_no_transport_flag_defaults_to_stdio(self, monkeypatch):
        """Test that no transport flag still runs stdio."""
        monkeypatch.setattr("poor_cli.server.sys.argv", ["poor-cli-server"])
        mock_server = MagicMock()
        mock_server.run_stdio.return_value = "stdio-coro"

        with (
            patch("poor_cli.server.PoorCLIServer", return_value=mock_server),
            patch("poor_cli.server.asyncio.run") as mock_asyncio_run,
        ):
            main()

        mock_server.run_stdio.assert_called_once_with()
        mock_asyncio_run.assert_called_once_with("stdio-coro")
