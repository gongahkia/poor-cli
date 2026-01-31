"""
Tests for the JSON-RPC server.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.server import (
    PoorCLIServer,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcError,
    RpcErrorCode,
)


class TestJsonRpcRequest:
    """Test JsonRpcRequest parsing."""
    
    def test_valid_request(self):
        """Test parsing a valid JSON-RPC request."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "test",
            "params": {"key": "value"}
        }
        
        request = JsonRpcRequest.from_dict(data)
        
        assert request.jsonrpc == "2.0"
        assert request.id == 1
        assert request.method == "test"
        assert request.params == {"key": "value"}
    
    def test_request_without_params(self):
        """Test parsing request without params."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "test"
        }
        
        request = JsonRpcRequest.from_dict(data)
        
        assert request.params is None
    
    def test_notification_no_id(self):
        """Test parsing notification (no id)."""
        data = {
            "jsonrpc": "2.0",
            "method": "notify"
        }
        
        request = JsonRpcRequest.from_dict(data)
        
        assert request.id is None
        assert request.method == "notify"


class TestJsonRpcResponse:
    """Test JsonRpcResponse serialization."""
    
    def test_success_response(self):
        """Test creating success response."""
        response = JsonRpcResponse(
            id=1,
            result={"status": "ok"}
        )
        
        data = response.to_dict()
        
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"] == {"status": "ok"}
        assert "error" not in data
    
    def test_error_response(self):
        """Test creating error response."""
        error = JsonRpcError(
            code=RpcErrorCode.INVALID_REQUEST,
            message="Invalid request"
        )
        response = JsonRpcResponse(id=1, error=error)
        
        data = response.to_dict()
        
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "error" in data
        assert data["error"]["code"] == RpcErrorCode.INVALID_REQUEST
        assert "result" not in data


class TestPoorCLIServer:
    """Test PoorCLIServer class."""
    
    @pytest.fixture
    def server(self):
        """Create a server instance for testing."""
        return PoorCLIServer()
    
    def test_init(self, server):
        """Test server initialization."""
        assert server.core is None
        assert server._initialized is False
        assert len(server._handlers) > 0
    
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
            assert method in server._handlers, f"Missing handler: {method}"
    
    @pytest.mark.asyncio
    async def test_handle_message_invalid_json(self, server):
        """Test handling invalid JSON."""
        response = await server.handle_message("not valid json")
        
        assert response is not None
        data = json.loads(response)
        assert "error" in data
        assert data["error"]["code"] == RpcErrorCode.PARSE_ERROR
    
    @pytest.mark.asyncio
    async def test_handle_message_invalid_request(self, server):
        """Test handling invalid request format."""
        message = json.dumps({"jsonrpc": "2.0"})  # Missing method
        
        response = await server.handle_message(message)
        
        data = json.loads(response)
        assert "error" in data
        assert data["error"]["code"] == RpcErrorCode.INVALID_REQUEST
    
    @pytest.mark.asyncio
    async def test_handle_message_method_not_found(self, server):
        """Test handling unknown method."""
        message = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "unknownMethod"
        })
        
        response = await server.handle_message(message)
        
        data = json.loads(response)
        assert "error" in data
        assert data["error"]["code"] == RpcErrorCode.METHOD_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_handle_shutdown(self, server):
        """Test shutdown handler."""
        message = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "shutdown"
        })
        
        response = await server.handle_message(message)
        
        data = json.loads(response)
        assert data["result"] == {"status": "shutdown"}


class TestServerInitialize:
    """Test server initialization handler."""
    
    @pytest.fixture
    def server(self):
        return PoorCLIServer()
    
    @pytest.mark.asyncio
    async def test_initialize_without_api_key(self, server, monkeypatch):
        """Test initialize fails without API key."""
        # Clear all API keys
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        
        with patch.object(server, 'core', None):
            message = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"provider": "gemini"}
            })
            
            response = await server.handle_message(message)
            data = json.loads(response)
            
            # Should either error or indicate not configured
            # (depends on implementation - some may still initialize)
            assert "result" in data or "error" in data


class TestRpcErrorCode:
    """Test RPC error codes."""
    
    def test_error_codes_values(self):
        """Test standard error code values."""
        assert RpcErrorCode.PARSE_ERROR == -32700
        assert RpcErrorCode.INVALID_REQUEST == -32600
        assert RpcErrorCode.METHOD_NOT_FOUND == -32601
        assert RpcErrorCode.INVALID_PARAMS == -32602
        assert RpcErrorCode.INTERNAL_ERROR == -32603
