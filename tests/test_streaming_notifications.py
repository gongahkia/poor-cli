"""
Tests for streaming notification protocol and permission flow.
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.server import PoorCLIServer, JsonRpcMessage


class TestStreamingHandlers:
    """Test that streaming-related handlers are registered."""

    @pytest.fixture
    def server(self):
        return PoorCLIServer()

    def test_chat_streaming_handler_registered(self, server):
        assert "poor-cli/chatStreaming" in server.handlers

    def test_cancel_request_handler_registered(self, server):
        assert "poor-cli/cancelRequest" in server.handlers


class TestNotificationParsing:
    """Test incoming notification (no id) handling."""

    def test_permission_res_notification_structure(self):
        msg = JsonRpcMessage.from_dict({
            "jsonrpc": "2.0",
            "method": "poor-cli/permissionRes",
            "params": {"promptId": "abc", "allowed": True},
        })
        assert msg.id is None
        assert msg.method == "poor-cli/permissionRes"
        assert msg.params["promptId"] == "abc"
        assert msg.params["allowed"] is True

    def test_plan_approval_notification_structure(self):
        msg = JsonRpcMessage.from_dict({
            "jsonrpc": "2.0",
            "method": "poor-cli/planApproval",
            "params": {"planId": "p1", "approved": False},
        })
        assert msg.id is None
        assert msg.method == "poor-cli/planApproval"


class TestStreamingPermissionCallback:
    """Test the streaming permission callback mechanism."""

    @pytest.fixture
    def server(self):
        s = PoorCLIServer()
        s._pending_permissions = {}
        return s

    @pytest.mark.asyncio
    async def test_permission_future_resolved(self, server):
        """Simulate resolving a pending permission future."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        server._pending_permissions["test-id"] = future
        # simulate client responding
        future.set_result(True)
        result = await asyncio.wait_for(future, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_permission_future_denied(self, server):
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        server._pending_permissions["test-id"] = future
        future.set_result(False)
        result = await asyncio.wait_for(future, timeout=1.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_permission_timeout(self, server):
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        server._pending_permissions["test-id"] = future
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(future, timeout=0.01)


class TestNotificationOutput:
    """Test outgoing notification serialization."""

    def test_stream_chunk_notification(self):
        msg = JsonRpcMessage(
            method="poor-cli/streamChunk",
            params={"requestId": "r1", "chunk": "hello", "done": False},
        )
        d = msg.to_dict()
        assert d["method"] == "poor-cli/streamChunk"
        assert "id" not in d or d.get("id") is None
        assert d["params"]["chunk"] == "hello"

    def test_tool_event_notification_with_diff(self):
        msg = JsonRpcMessage(
            method="poor-cli/toolEvent",
            params={
                "requestId": "r1",
                "eventType": "tool_result",
                "toolName": "edit_file",
                "toolResult": "ok",
                "diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new",
            },
        )
        d = msg.to_dict()
        assert d["params"]["diff"].startswith("---")

    def test_permission_req_notification(self):
        msg = JsonRpcMessage(
            method="poor-cli/permissionReq",
            params={"toolName": "bash", "toolArgs": {"cmd": "rm"}, "promptId": "p1"},
        )
        d = msg.to_dict()
        assert d["params"]["promptId"] == "p1"

    def test_cost_update_notification(self):
        msg = JsonRpcMessage(
            method="poor-cli/costUpdate",
            params={"inputTokens": 500, "outputTokens": 200, "estimatedCost": 0.01},
        )
        d = msg.to_dict()
        assert d["params"]["inputTokens"] == 500

    def test_progress_notification(self):
        msg = JsonRpcMessage(
            method="poor-cli/progress",
            params={"phase": "executing", "message": "running tool", "iterationIndex": 2, "iterationCap": 25},
        )
        d = msg.to_dict()
        assert d["params"]["iterationIndex"] == 2
