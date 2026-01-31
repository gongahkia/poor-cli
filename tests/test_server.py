"""
Tests for the JSON-RPC server.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.server import (
    PoorCLIServer,
    JsonRpcMessage,
    JsonRpcError,
)


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
        assert server.initialized is False
        assert len(server.handlers) > 0
    
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
    
    @pytest.mark.asyncio
    async def test_dispatch_method_not_found(self, server):
        """Test dispatching unknown method."""
        message = JsonRpcMessage(id=1, method="unknownMethod")
        
        response = await server.dispatch(message)
        
        assert response.error is not None
        assert response.error["code"] == JsonRpcError.METHOD_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_dispatch_shutdown(self, server):
        """Test shutdown handler via dispatch."""
        message = JsonRpcMessage(id=1, method="shutdown")
        
        response = await server.dispatch(message)
        
        # Shutdown returns None result
        assert response.error is None
