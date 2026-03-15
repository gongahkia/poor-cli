"""Tests for multiplayer WebSocket host runtime."""

import asyncio
import contextlib
import json
import socket
import time
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
    dispatch_delay: float = 0.02
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
            await asyncio.sleep(self.dispatch_delay)
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
    def __init__(self, dispatch_delay: float = 0.02):
        self.instances: List[_FakeServer] = []
        self.dispatch_delay = dispatch_delay

    def __call__(self) -> _FakeServer:
        instance = _FakeServer(dispatch_delay=self.dispatch_delay)
        self.instances.append(instance)
        return instance


async def _ws_recv_json(ws: aiohttp.ClientWebSocketResponse) -> Dict[str, Any]:
    msg = await ws.receive(timeout=2.0)
    assert msg.type == aiohttp.WSMsgType.TEXT
    payload = json.loads(msg.data)
    assert isinstance(payload, dict)
    return payload


async def _wait_for_response_id(
    ws: aiohttp.ClientWebSocketResponse, expected_id: int, max_messages: int = 40
) -> Dict[str, Any]:
    for _ in range(max_messages):
        payload = await _ws_recv_json(ws)
        if payload.get("id") == expected_id:
            return payload
    raise AssertionError(f"Did not receive response id={expected_id}")


async def _wait_for_notification(
    ws: aiohttp.ClientWebSocketResponse, expected_method: str, max_messages: int = 40
) -> Dict[str, Any]:
    for _ in range(max_messages):
        payload = await _ws_recv_json(ws)
        if payload.get("method") == expected_method:
            return payload
    raise AssertionError(f"Did not receive notification method={expected_method}")


async def _drain_pending(ws: aiohttp.ClientWebSocketResponse, timeout: float = 0.05) -> None:
    while True:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
        except asyncio.TimeoutError:
            break
        if msg.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED}:
            break


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
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as driver_ws, session.ws_connect(
                f"ws://127.0.0.1:{port}/rpc"
            ) as viewer_a_ws, session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as viewer_b_ws:
                await driver_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _ws_recv_json(driver_ws)
                _ = await _ws_recv_json(driver_ws)

                await viewer_a_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["viewer"]},
                    }
                )
                _ = await _ws_recv_json(viewer_a_ws)
                _ = await _ws_recv_json(viewer_a_ws)

                await viewer_b_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["viewer"]},
                    }
                )
                _ = await _ws_recv_json(viewer_b_ws)
                _ = await _ws_recv_json(viewer_b_ws)

                await _drain_pending(driver_ws)
                await _drain_pending(viewer_a_ws)
                await _drain_pending(viewer_b_ws)

                await driver_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 99,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "hello", "requestId": "req-99"},
                    }
                )

                seen_stream_driver = False
                seen_stream_viewer_a = False
                seen_stream_viewer_b = False
                got_final_response = False

                for _ in range(8):
                    payload = await _ws_recv_json(driver_ws)
                    if payload.get("method") == "poor-cli/streamingChunk":
                        seen_stream_driver = True
                    if payload.get("id") == 99:
                        got_final_response = True
                        break

                for _ in range(6):
                    payload = await _ws_recv_json(viewer_a_ws)
                    if payload.get("method") == "poor-cli/streamingChunk":
                        seen_stream_viewer_a = True
                        break

                for _ in range(6):
                    payload = await _ws_recv_json(viewer_b_ws)
                    if payload.get("method") == "poor-cli/streamingChunk":
                        seen_stream_viewer_b = True
                        break

                assert seen_stream_driver
                assert seen_stream_viewer_a
                assert seen_stream_viewer_b
                assert got_final_response

                # Viewer should not receive requester's final RPC response id=99.
                with contextlib.suppress(asyncio.TimeoutError):
                    maybe_extra = await asyncio.wait_for(viewer_a_ws.receive(), timeout=0.1)
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
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as ws1:
                await ws1.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _ws_recv_json(ws1)
                _ = await _ws_recv_json(ws1)

                await ws1.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "first", "requestId": "first"},
                    }
                )
                await ws1.send_json(
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


@pytest.mark.asyncio
async def test_queued_request_dropped_when_connection_disconnects():
    """Audit: queued requests from disconnected members are dropped without rerouting."""
    factory = _FakeServerFactory(dispatch_delay=0.15)
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
                await ws1.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _ws_recv_json(ws1)
                _ = await _ws_recv_json(ws1)

                await ws2.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["viewer"]},
                    }
                )
                ws2_init = await _wait_for_response_id(ws2, 2)
                ws2_connection_id = ws2_init["result"]["capabilities"]["multiplayer"]["connectionId"]
                _ = await _wait_for_notification(ws2, "poor-cli/roomEvent")
                _ = await _wait_for_notification(ws1, "poor-cli/roomEvent")

                await ws1.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "first", "requestId": "first"},
                    }
                )
                await asyncio.sleep(0.03)

                promoted = await host.set_room_member_role("dev", ws2_connection_id, "prompter")
                assert promoted is True

                await ws2.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 20,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "second", "requestId": "second"},
                    }
                )

                await asyncio.sleep(0.03)
                await ws2.close()

                await ws1.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 30,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "third", "requestId": "third"},
                    }
                )

                final_ids = set()
                for _ in range(40):
                    payload = await _ws_recv_json(ws1)
                    msg_id = payload.get("id")
                    assert msg_id != 20
                    if msg_id in {10, 30}:
                        final_ids.add(msg_id)
                    if final_ids == {10, 30}:
                        break

                assert final_ids == {10, 30}
                room_server = factory.instances[0]
                assert room_server.dispatch_request_ids == ["first", "third"]

    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_token_expiry_and_activity_filtering():
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

    try:
        room = host.rooms["dev"]
        host._record_activity(room, event_type="custom_one")
        host._record_activity(room, event_type="custom_two")
        host._record_activity(room, event_type="custom_one")

        filtered = host.list_room_activity("dev", 10, "custom_one")
        assert len(filtered) == 2
        assert all(item.get("eventType") == "custom_one" for item in filtered)

        rotated = await host.rotate_room_token("dev", "viewer", expires_in_seconds=1)
        assert rotated is not None

        tokens_before = host.get_room_tokens()["dev"]
        assert tokens_before.get("viewer") == rotated

        await asyncio.sleep(1.2)

        tokens_after = host.get_room_tokens()["dev"]
        assert tokens_after.get("viewer") != rotated
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_heartbeat_closes_stale_connection():
    factory = _FakeServerFactory()
    port = _free_port()
    host = MultiplayerHost(
        bind_host="127.0.0.1",
        port=port,
        room_names=["dev"],
        server_factory=factory,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
        heartbeat_interval_seconds=0.05,
        pong_timeout_seconds=0.10,
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

                room = host.rooms["dev"]
                assert room.members
                member = next(iter(room.members.values()))
                member.last_pong = time.monotonic() - 999

                for _ in range(20):
                    if member.connection_id not in host.connections:
                        break
                    await asyncio.sleep(0.05)

                assert member.connection_id not in host.connections
                assert member.connection_id not in room.members
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_kick_member_rpc_disconnects_target():
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
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as host_ws, session.ws_connect(
                f"ws://127.0.0.1:{port}/rpc"
            ) as target_ws:
                await host_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _ws_recv_json(host_ws)
                _ = await _ws_recv_json(host_ws)

                await target_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["viewer"]},
                    }
                )
                _ = await _ws_recv_json(target_ws)
                _ = await _ws_recv_json(target_ws)
                _ = await _ws_recv_json(host_ws)

                room = host.rooms["dev"]
                target_connection_id = next(
                    member.connection_id
                    for member in room.members.values()
                    if member.role == "viewer"
                )

                await host_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 55,
                        "method": "poor-cli/kickMember",
                        "params": {"room": "dev", "connectionId": target_connection_id},
                    }
                )

                saw_response = False
                saw_room_event = False
                for _ in range(8):
                    payload = await _ws_recv_json(host_ws)
                    if payload.get("id") == 55:
                        assert payload.get("result", {}).get("ok") is True
                        saw_response = True
                    if payload.get("method") == "poor-cli/roomEvent":
                        details = payload.get("params", {}).get("details", {})
                        if details.get("targetConnectionId") == target_connection_id:
                            saw_room_event = True
                    if saw_response and saw_room_event:
                        break

                assert saw_response
                assert saw_room_event

                for _ in range(20):
                    if target_connection_id not in host.connections:
                        break
                    await asyncio.sleep(0.02)
                assert target_connection_id not in host.connections
                assert target_connection_id not in room.members

    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_rate_limit_per_connection_blocks_flooding_not_other_members():
    factory = _FakeServerFactory()
    port = _free_port()
    host = MultiplayerHost(
        bind_host="127.0.0.1",
        port=port,
        room_names=["dev"],
        server_factory=factory,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
        requests_per_minute=2,
    )
    await host.start()
    tokens = host.get_room_tokens()["dev"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as ws_a, session.ws_connect(
                f"ws://127.0.0.1:{port}/rpc"
            ) as ws_b:
                await ws_a.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _ws_recv_json(ws_a)
                _ = await _ws_recv_json(ws_a)

                await ws_b.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["viewer"]},
                    }
                )
                ws_b_init = await _wait_for_response_id(ws_b, 2)
                ws_b_connection_id = ws_b_init["result"]["capabilities"]["multiplayer"]["connectionId"]
                _ = await _wait_for_notification(ws_b, "poor-cli/roomEvent")
                _ = await _wait_for_notification(ws_a, "poor-cli/roomEvent")

                await ws_a.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 11,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "one", "requestId": "one"},
                    }
                )
                first = await _wait_for_response_id(ws_a, 11)
                assert first.get("result", {}).get("content") == "done"

                await ws_a.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 12,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "two", "requestId": "two"},
                    }
                )
                second = await _wait_for_response_id(ws_a, 12)
                assert second.get("result", {}).get("content") == "done"

                await ws_a.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 13,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "three", "requestId": "three"},
                    }
                )
                limited = await _wait_for_response_id(ws_a, 13)
                assert limited.get("error", {}).get("code") == -32029
                assert limited.get("error", {}).get("message") == "Rate limited"

                promoted = await host.set_room_member_role("dev", ws_b_connection_id, "prompter")
                assert promoted is True
                await _drain_pending(ws_a)
                await _drain_pending(ws_b)

                await ws_b.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 21,
                        "method": "poor-cli/chatStreaming",
                        "params": {"message": "other", "requestId": "other"},
                    }
                )
                other = await _wait_for_response_id(ws_b, 21)
                assert other.get("result", {}).get("content") == "done"
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_list_room_members_rpc_available_to_authenticated_viewer():
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

                await viewer_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 99,
                        "method": "poor-cli/listRoomMembers",
                        "params": {"room": "dev"},
                    }
                )
                payload = await _wait_for_response_id(viewer_ws, 99)
                result = payload.get("result", {})
                assert result.get("room") == "dev"
                members = result.get("members")
                assert isinstance(members, list)
                assert len(members) == 2
                assert all("connection_id" in member for member in members)
                assert all("role" in member for member in members)
                assert all("connected_at" in member for member in members)
                assert all("last_active" in member for member in members)
                assert all("is_active_prompter" in member for member in members)
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_prompter_join_and_pass_driver_preserve_single_active_driver():
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
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as first_prompter_ws, session.ws_connect(
                f"ws://127.0.0.1:{port}/rpc"
            ) as second_prompter_ws:
                await first_prompter_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "room": "dev",
                            "inviteToken": tokens["prompter"],
                            "clientName": "driver-a",
                        },
                    }
                )
                first_init = await _wait_for_response_id(first_prompter_ws, 1)
                first_connection_id = first_init["result"]["capabilities"]["multiplayer"]["connectionId"]
                _ = await _wait_for_notification(first_prompter_ws, "poor-cli/roomEvent")

                await second_prompter_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {
                            "room": "dev",
                            "inviteToken": tokens["prompter"],
                            "clientName": "driver-b",
                        },
                    }
                )
                second_init = await _wait_for_response_id(second_prompter_ws, 2)
                second_connection_id = second_init["result"]["capabilities"]["multiplayer"]["connectionId"]
                _ = await _wait_for_notification(second_prompter_ws, "poor-cli/roomEvent")
                _ = await _wait_for_notification(first_prompter_ws, "poor-cli/roomEvent")

                members_after_join = host.list_room_members("dev")[0]["members"]
                assert sum(member["role"] == "prompter" for member in members_after_join) == 1
                assert any(
                    member["connectionId"] == second_connection_id and member["role"] == "prompter"
                    for member in members_after_join
                )
                assert any(
                    member["connectionId"] == first_connection_id and member["role"] == "viewer"
                    for member in members_after_join
                )

                await _drain_pending(first_prompter_ws)
                await _drain_pending(second_prompter_ws)

                await second_prompter_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "poor-cli/passDriver",
                        "params": {"displayName": "driver-a"},
                    }
                )
                pass_response = await _wait_for_response_id(second_prompter_ws, 3)
                assert pass_response["result"]["success"] is True
                assert pass_response["result"]["connectionId"] == first_connection_id

                members_after_pass = host.list_room_members("dev")[0]["members"]
                assert sum(member["role"] == "prompter" for member in members_after_pass) == 1
                assert any(
                    member["connectionId"] == first_connection_id and member["role"] == "prompter"
                    for member in members_after_pass
                )
                assert any(
                    member["connectionId"] == second_connection_id and member["role"] == "viewer"
                    for member in members_after_pass
                )
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_suggest_text_is_delivered_only_to_active_driver():
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
            async with session.ws_connect(f"ws://127.0.0.1:{port}/rpc") as driver_ws, session.ws_connect(
                f"ws://127.0.0.1:{port}/rpc"
            ) as viewer_ws:
                await driver_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["prompter"]},
                    }
                )
                _ = await _wait_for_response_id(driver_ws, 1)
                _ = await _wait_for_notification(driver_ws, "poor-cli/roomEvent")

                await viewer_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "initialize",
                        "params": {"room": "dev", "inviteToken": tokens["viewer"], "clientName": "navigator"},
                    }
                )
                _ = await _wait_for_response_id(viewer_ws, 2)
                _ = await _wait_for_notification(viewer_ws, "poor-cli/roomEvent")
                _ = await _wait_for_notification(driver_ws, "poor-cli/roomEvent")
                await _drain_pending(driver_ws)
                await _drain_pending(viewer_ws)

                await viewer_ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "poor-cli/suggestText",
                        "params": {"text": "check the failing branch"},
                    }
                )
                suggest_response = await _wait_for_response_id(viewer_ws, 3)
                assert suggest_response["result"] == {"success": True, "delivered": 1}

                suggestion = await _wait_for_notification(driver_ws, "poor-cli/suggestion")
                assert suggestion["params"]["sender"] == "navigator"
                assert suggestion["params"]["text"] == "check the failing branch"

                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(_wait_for_notification(viewer_ws, "poor-cli/suggestion", 1), timeout=0.1)
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_plan_response_notifications_are_forwarded_to_embedded_room_server():
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
                _ = await _wait_for_response_id(ws, 1)
                _ = await _wait_for_notification(ws, "poor-cli/roomEvent")

                await ws.send_json(
                    {
                        "jsonrpc": "2.0",
                        "method": "poor-cli/planRes",
                        "params": {"promptId": "plan-1", "allowed": True},
                    }
                )

                for _ in range(20):
                    if any(
                        message.method == "poor-cli/planRes"
                        for message in factory.instances[0].notification_calls
                    ):
                        break
                    await asyncio.sleep(0.05)

                assert any(
                    message.method == "poor-cli/planRes"
                    for message in factory.instances[0].notification_calls
                )
    finally:
        await host.stop()
