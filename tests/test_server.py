"""
Tests for the JSON-RPC server.
"""

import json
import pytest
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.server import (
    PoorCLIServer,
    JsonRpcMessage,
    JsonRpcError,
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
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "test",
            "params": {"key": "value"}
        }
        
        message = JsonRpcMessage.from_dict(data)
        
        assert message.jsonrpc == "2.0"
        assert message.id == 1
        assert message.method == "test"
        assert message.params == {"key": "value"}
    
    def test_from_dict_without_params(self):
        """Test parsing request without params."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "test"
        }
        
        message = JsonRpcMessage.from_dict(data)
        
        assert message.params is None
    
    def test_from_dict_notification(self):
        """Test parsing notification (no id)."""
        data = {
            "jsonrpc": "2.0",
            "method": "notify"
        }
        
        message = JsonRpcMessage.from_dict(data)
        
        assert message.id is None
        assert message.method == "notify"
    
    def test_to_dict_success_response(self):
        """Test serializing success response."""
        message = JsonRpcMessage(
            id=1,
            result={"status": "ok"}
        )
        
        data = message.to_dict()
        
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"] == {"status": "ok"}
    
    def test_to_dict_error_response(self):
        """Test serializing error response."""
        message = JsonRpcMessage(
            id=1,
            error={"code": -32600, "message": "Invalid request"}
        )
        
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
        ]
        
        for method in required:
            assert method in server.handlers, f"Missing handler: {method}"
    
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
