"""Tests for multiplayer WebSocket host runtime."""

import asyncio
import contextlib
import json
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest
aiohttp = pytest.importorskip("aiohttp")

from poor_cli.multiplayer import MultiplayerHost
from poor_cli.server import JsonRpcError, JsonRpcMessage



def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@dataclass
class _FakeServer:
    permission_mode: str = "prompt"
    initialized: bool = False
    dispatch_calls: List[str] = field(default_factory=list)
    dispatch_request_ids: List[str] = field(default_factory=list)
    notification_calls: List[JsonRpcMessage] = field(default_factory=list)
    write_message_stdio: Any = None

    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        self.initialized = True
        return {
            "capabilities": {
                "completionProvider": True,
                "inlineCompletionProvider": True,
                "chatProvider": True,
                "chatStreamingProvider": True,
                "fileOperations": True,
                "permissionMode": self.permission_mode,
                "providerInfo": {"name": "fake", "model": "fake-model"},
            }
        }

    async def dispatch(self, message: JsonRpcMessage) -> JsonRpcMessage:
        method = message.method or ""
        self.dispatch_calls.append(method)

        if method == "poor-cli/chatStreaming":
            request_id = str((message.params or {}).get("requestId", ""))
            self.dispatch_request_ids.append(request_id)
            if self.write_message_stdio is not None:
                await self.write_message_stdio(
                    JsonRpcMessage(
                        method="poor-cli/streamChunk",
                        params={"requestId": request_id, "chunk": "hello", "done": False},
                    )
                )
                await self.write_message_stdio(
                    JsonRpcMessage(
                        method="poor-cli/streamChunk",
                        params={"requestId": request_id, "chunk": "", "done": True},
                    )
                )
            await asyncio.sleep(0.02)
            return JsonRpcMessage(
                id=message.id,
                result={"content": "done", "role": "assistant"},
            )

        if method == "poor-cli/inlineComplete":
            return JsonRpcMessage(id=message.id, result={"completion": "x", "isPartial": False})

        return JsonRpcMessage(id=message.id, result={"ok": True, "method": method})

    async def _handle_notification(self, message: JsonRpcMessage) -> None:
        self.notification_calls.append(message)


class _FakeServerFactory:
    def __init__(self):
        self.instances: List[_FakeServer] = []

    def __call__(self) -> _FakeServer:
        instance = _FakeServer()
        self.instances.append(instance)
        return instance


async def _ws_recv_json(ws: aiohttp.ClientWebSocketResponse) -> Dict[str, Any]:
    msg = await ws.receive(timeout=2.0)
    assert msg.type == aiohttp.WSMsgType.TEXT
    payload = json.loads(msg.data)
    assert isinstance(payload, dict)
    return payload


@pytest.mark.asyncio
async def test_initialize_auth_and_viewer_denied_prompt_methods():
    factory = _FakeServerFactory()
    port = _free_port()
    host = MultiplayerHost(
        bind_host="127.0.0.1",
        port=port,
        room_names=["dev"],
        server_factory=factory,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
    )
    await host.start()

    tokens = host.get_room_tokens()["dev"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as ws:
                await ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "room": "dev",
                            "inviteToken": tokens["viewer"],
                            "clientName": "viewer-a",
                        },
                    }
                )
                init_resp = await _ws_recv_json(ws)
                assert init_resp["id"] == 1
                assert init_resp["result"]["capabilities"]["multiplayer"]["role"] == "viewer"

                # member_joined room event
                room_event = await _ws_recv_json(ws)
                assert room_event["method"] == "poor-cli/roomEvent"

                await ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "blocked", "requestId": "r1"},
                    }
                )
                denied = await _ws_recv_json(ws)
                assert denied["id"] == 2
                assert denied["error"]["data"]["error_code"] == "permission_denied"

            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as ws_bad:
                await ws_bad.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "initialize",
                        "params": {
                            "room": "dev",
                            "inviteToken": "invalid",
                        },
                    }
                )
                bad = await _ws_recv_json(ws_bad)
                assert bad["id"] == 3
                assert bad["error"]["code"] == JsonRpcError.INVALID_PARAMS

    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_streaming_notifications_broadcast_but_response_only_to_requester():
    factory = _FakeServerFactory()
    port = _free_port()
    host = MultiplayerHost(
        bind_host="127.0.0.1",
        port=port,
        room_names=["dev"],
        server_factory=factory,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
    )
    await host.start()

    tokens = host.get_room_tokens()["dev"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as prompter_ws, session.ws_connect(
                f"ws://127.0.0.1:{port}/rpc"
            ) as viewer_ws:
                await prompter_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _ws_recv_json(prompter_ws)
                _ = await _ws_recv_json(prompter_ws)

                await viewer_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["viewer"]},
                    }
                )
                _ = await _ws_recv_json(viewer_ws)
                _ = await _ws_recv_json(viewer_ws)
                _ = await _ws_recv_json(prompter_ws)

                await prompter_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 99,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "hello", "requestId": "req-99"},
                    }
                )

                # both receive queue/started/stream events
                seen_stream_prompter = False
                seen_stream_viewer = False
                got_final_response = False

                for _ in range(8):
                    payload = await _ws_recv_json(prompter_ws)
                    if payload.get("method") == "poor-cli/streamChunk":
                        seen_stream_prompter = True
                    if payload.get("id") == 99:
                        got_final_response = True
                        break

                for _ in range(6):
                    payload = await _ws_recv_json(viewer_ws)
                    if payload.get("method") == "poor-cli/streamChunk":
                        seen_stream_viewer = True
                        break

                assert seen_stream_prompter
                assert seen_stream_viewer
                assert got_final_response

                # Viewer should not receive requester's final RPC response id=99.
                with contextlib.suppress(asyncio.TimeoutError):
                    maybe_extra = await asyncio.wait_for(viewer_ws.receive(), timeout=0.1)
                    if maybe_extra.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(maybe_extra.data)
                        assert payload.get("id") != 99

    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_same_room_queue_is_fifo():
    factory = _FakeServerFactory()
    port = _free_port()
    host = MultiplayerHost(
        bind_host="127.0.0.1",
        port=port,
        room_names=["dev"],
        server_factory=factory,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
    )
    await host.start()

    tokens = host.get_room_tokens()["dev"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as ws1, session.ws_connect(
                f"ws://127.0.0.1:{port}/rpc"
            ) as ws2:
                for ws in (ws1, ws2):
                    await ws.send_json(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                        }
                    )
                    _ = await _ws_recv_json(ws)
                    _ = await _ws_recv_json(ws)

                await ws1.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "first", "requestId": "first"},
                    }
                )
                await ws2.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 20,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "second", "requestId": "second"},
                    }
                )

                # drain responses/events from both sockets until both final responses observed
                final_ids = set()
                attempts = 0
                while final_ids != {10, 20} and attempts < 30:
                    attempts += 1
                    payload1 = await _ws_recv_json(ws1)
                    if payload1.get("id") in {10, 20}:
                        final_ids.add(payload1["id"])
                    payload2 = await _ws_recv_json(ws2)
                    if payload2.get("id") in {10, 20}:
                        final_ids.add(payload2["id"])

                assert final_ids == {10, 20}
                room_server = factory.instances[0]
                chat_calls = [m for m in room_server.dispatch_calls if m == "poor-cli/chatStreaming"]
                assert chat_calls == ["poor-cli/chatStreaming", "poor-cli/chatStreaming"]
                assert room_server.dispatch_request_ids == ["first", "second"]

    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_inline_complete_uses_isolated_engine_not_room_server():
    factory = _FakeServerFactory()
    port = _free_port()
    host = MultiplayerHost(
        bind_host="127.0.0.1",
        port=port,
        room_names=["dev"],
        server_factory=factory,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
    )
    await host.start()

    tokens = host.get_room_tokens()["dev"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as ws:
                await ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _ws_recv_json(ws)
                _ = await _ws_recv_json(ws)

                await ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 77,
                        "method": "poor-cli/inlineComplete",
                        "params": {
                            "codeBefore": "a",
                            "codeAfter": "b",
                            "instruction": "",
                            "filePath": "x.py",
                            "language": "python",
                        },
                    }
                )

                inline_resp = await _ws_recv_json(ws)
                assert inline_resp["id"] == 77
                assert inline_resp["result"]["completion"] == "x"

                room_server = factory.instances[0]
                assert "poor-cli/inlineComplete" not in room_server.dispatch_calls
                assert len(factory.instances) >= 2  # room engine + isolated inline engine

    finally:
        await host.stop()
