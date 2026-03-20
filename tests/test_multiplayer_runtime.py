import asyncio
import contextlib
import json
import socket
import unittest
from dataclasses import dataclass
from typing import Any, Dict, Optional

from aiohttp import ClientSession

from poor_cli.multiplayer import MultiplayerHost

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription
except ImportError:  # pragma: no cover - exercised in the runtime validation venv
    RTCPeerConnection = None
    RTCSessionDescription = None


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class _JsonRpcMessage:
    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            payload["id"] = self.id
        if self.method is not None:
            payload["method"] = self.method
        if self.params is not None:
            payload["params"] = self.params
        if self.result is not None:
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_JsonRpcMessage":
        return cls(
            jsonrpc=str(data.get("jsonrpc", "2.0")),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )


class _JsonRpcError:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class _ConnectedClient:
    peer_connection: Any
    channel: Any
    inbound_messages: asyncio.Queue
    invite_code: str
    invite_token: str
    connection_id: str
    approval_state: str
    role: str


class _StubRoomServer:
    def __init__(self) -> None:
        self.permission_mode = "prompt"
        self._embedded_multiplayer_room = False
        self.write_message_stdio = None

    async def handle_initialize(self, params):
        del params
        return {
            "capabilities": {
                "providerInfo": {"name": "stub", "model": "stub"},
            }
        }

    async def dispatch(self, message):
        return _JsonRpcMessage(
            id=message.id,
            result={"ok": True, "method": getattr(message, "method", "")},
        )

    async def _handle_notification(self, message):
        del message
        return None


@unittest.skipIf(RTCPeerConnection is None, "aiortc is not installed")
class MultiplayerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.port = _unused_tcp_port()
        self.signaling_url = f"http://127.0.0.1:{self.port}/rpc"
        self.host = MultiplayerHost(
            bind_host="127.0.0.1",
            port=self.port,
            room_names=["dev"],
            server_factory=_StubRoomServer,
            message_cls=_JsonRpcMessage,
            rpc_error_cls=_JsonRpcError,
            owner_name="tester",
            ice_servers=[],
        )
        await self.host.start()

    async def asyncTearDown(self) -> None:
        await self.host.stop()

    async def _wait_for_ice_complete(self, peer_connection, timeout: float = 5.0) -> None:
        if str(getattr(peer_connection, "iceGatheringState", "")) == "complete":
            return

        done = asyncio.get_running_loop().create_future()

        @peer_connection.on("icegatheringstatechange")
        def _on_ice_gathering_state_change() -> None:
            if str(getattr(peer_connection, "iceGatheringState", "")) == "complete":
                if not done.done():
                    done.set_result(None)

        await asyncio.wait_for(done, timeout=timeout)

    async def _wait_until(self, predicate, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.05)
        self.fail("timed out waiting for runtime condition")

    async def _recv_message(self, queue: asyncio.Queue, predicate, timeout: float = 5.0):
        while True:
            payload = await asyncio.wait_for(queue.get(), timeout=timeout)
            if predicate(payload):
                return payload

    async def _assert_no_matching_message(
        self,
        queue: asyncio.Queue,
        predicate,
        timeout: float = 0.5,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=min(0.05, remaining))
            except asyncio.TimeoutError:
                return
            if predicate(payload):
                self.fail(f"unexpected message received: {payload}")

    def _build_client_transport(self):
        peer_connection = RTCPeerConnection()
        channel = peer_connection.createDataChannel("rpc", ordered=True)
        open_event = asyncio.Event()
        inbound_messages: asyncio.Queue = asyncio.Queue()

        @channel.on("open")
        def _on_open() -> None:
            open_event.set()

        @channel.on("message")
        def _on_message(data) -> None:
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="ignore")
            inbound_messages.put_nowait(json.loads(str(data)))

        return peer_connection, channel, open_event, inbound_messages

    async def _signal_peer_connection(
        self,
        peer_connection,
        *,
        invite_code: str,
        client_name: str,
    ):
        offer = await peer_connection.createOffer()
        await peer_connection.setLocalDescription(offer)
        await self._wait_for_ice_complete(peer_connection)

        async with ClientSession() as session:
            async with session.post(
                self.signaling_url,
                json={
                    "action": "connect",
                    "invite": invite_code,
                    "clientName": client_name,
                    "offer": {
                        "type": str(getattr(peer_connection.localDescription, "type", "offer")),
                        "sdp": str(getattr(peer_connection.localDescription, "sdp", "")),
                    },
                },
            ) as response:
                payload = await response.json()
                return response.status, payload

    async def _connect_initialized_client(
        self,
        *,
        role: str,
        client_name: str,
        invite_code: Optional[str] = None,
        invite_token: Optional[str] = None,
    ) -> _ConnectedClient:
        share_payload = None
        if not invite_code or not invite_token:
            share_payload = self.host.build_room_share_payload(
                "dev",
                role,
                signaling_url=self.signaling_url,
            )
            self.assertIsNotNone(share_payload)
            invite_code = str((share_payload or {}).get("inviteCode", "")).strip()
            invite_token = str((share_payload or {}).get("token", "")).strip()

        self.assertTrue(invite_code)
        self.assertTrue(invite_token)

        peer_connection, channel, open_event, inbound_messages = self._build_client_transport()
        status, payload = await self._signal_peer_connection(
            peer_connection,
            invite_code=invite_code,
            client_name=client_name,
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("transport"), "webrtc-datachannel")

        await peer_connection.setRemoteDescription(
            RTCSessionDescription(
                sdp=str(payload["answer"]["sdp"]),
                type=str(payload["answer"]["type"]),
            )
        )
        await asyncio.wait_for(open_event.wait(), timeout=5.0)

        channel.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "room": "dev",
                        "inviteToken": invite_token,
                        "clientName": client_name,
                    },
                }
            )
        )
        init_response = await self._recv_message(
            inbound_messages,
            lambda message: message.get("id") == 1,
        )
        capabilities = init_response["result"]["capabilities"]["multiplayer"]
        return _ConnectedClient(
            peer_connection=peer_connection,
            channel=channel,
            inbound_messages=inbound_messages,
            invite_code=invite_code,
            invite_token=invite_token,
            connection_id=str(capabilities["connectionId"]),
            approval_state=str(capabilities["approvalState"]),
            role=str(capabilities["role"]),
        )

    async def _close_client(self, client: _ConnectedClient) -> None:
        with contextlib.suppress(Exception):
            await client.peer_connection.close()

    async def test_signaling_connects_and_cleans_up_room_members(self) -> None:
        share_payload = self.host.build_room_share_payload(
            "dev",
            "viewer",
            signaling_url=self.signaling_url,
        )
        self.assertIsNotNone(share_payload)
        invite_code = str((share_payload or {}).get("inviteCode", "")).strip()
        invite_token = str((share_payload or {}).get("token", "")).strip()
        self.assertTrue(invite_code)
        self.assertTrue(invite_token)

        peer_connection = RTCPeerConnection()
        channel = peer_connection.createDataChannel("rpc", ordered=True)
        open_event = asyncio.Event()
        inbound_messages: asyncio.Queue = asyncio.Queue()

        @channel.on("open")
        def _on_open() -> None:
            open_event.set()

        @channel.on("message")
        def _on_message(data) -> None:
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="ignore")
            inbound_messages.put_nowait(json.loads(str(data)))

        try:
            offer = await peer_connection.createOffer()
            await peer_connection.setLocalDescription(offer)
            await self._wait_for_ice_complete(peer_connection)

            async with ClientSession() as session:
                async with session.post(
                    self.signaling_url,
                    json={
                        "action": "connect",
                        "invite": invite_code,
                        "clientName": "viewer-one",
                        "offer": {
                            "type": str(getattr(peer_connection.localDescription, "type", "offer")),
                            "sdp": str(getattr(peer_connection.localDescription, "sdp", "")),
                        },
                    },
                ) as response:
                    self.assertEqual(response.status, 200)
                    payload = await response.json()

            self.assertTrue(payload.get("ok"))
            self.assertEqual(payload.get("transport"), "webrtc-datachannel")

            await peer_connection.setRemoteDescription(
                RTCSessionDescription(
                    sdp=str(payload["answer"]["sdp"]),
                    type=str(payload["answer"]["type"]),
                )
            )
            await asyncio.wait_for(open_event.wait(), timeout=5.0)

            channel.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "room": "dev",
                            "inviteToken": invite_token,
                            "clientName": "viewer-one",
                        },
                    }
                )
            )
            init_response = await self._recv_message(
                inbound_messages,
                lambda message: message.get("id") == 1,
            )
            capabilities = init_response["result"]["capabilities"]["multiplayer"]
            connection_id = str(capabilities["connectionId"])
            self.assertEqual(capabilities["room"], "dev")
            self.assertEqual(capabilities["role"], "viewer")
            self.assertEqual(capabilities["approvalState"], "approved")

            room_event = await self._recv_message(
                inbound_messages,
                lambda message: message.get("method") == "poor-cli/roomEvent",
            )
            self.assertEqual(room_event["params"]["eventType"], "member_joined")
            self.assertEqual(room_event["params"]["memberCount"], 1)

            channel.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "poor-cli/listRoomMembers",
                        "params": {"room": "dev"},
                    }
                )
            )
            members_response = await self._recv_message(
                inbound_messages,
                lambda message: message.get("id") == 2,
            )
            self.assertEqual(members_response["result"]["room"], "dev")
            self.assertEqual(len(members_response["result"]["members"]), 1)
            self.assertEqual(members_response["result"]["members"][0]["display_name"], "viewer-one")

            channel.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "poor-cli/setHandRaised",
                        "params": {"raised": True},
                    }
                )
            )
            hand_raise_response = await self._recv_message(
                inbound_messages,
                lambda message: message.get("id") == 3,
            )
            self.assertTrue(hand_raise_response["result"]["handRaised"])
            await self._wait_until(
                lambda: self.host.rooms["dev"].members[connection_id].hand_raised is True
            )

            await peer_connection.close()
            await self._wait_until(
                lambda: not self.host.connections
                and not self.host.rooms["dev"].members
                and not self.host._peer_connections
            )
        finally:
            with contextlib.suppress(Exception):
                await peer_connection.close()

    async def test_signaling_requires_invite_or_room_token_auth(self) -> None:
        peer_connection, _, _, _ = self._build_client_transport()
        try:
            status, payload = await self._signal_peer_connection(
                peer_connection,
                invite_code="",
                client_name="missing-auth",
            )
            self.assertEqual(status, 403)
            self.assertEqual(payload.get("error"), "invalid_multiplayer_auth")
        finally:
            with contextlib.suppress(Exception):
                await peer_connection.close()

    async def test_rotated_invite_token_rejects_stale_signed_invite(self) -> None:
        share_payload = self.host.build_room_share_payload(
            "dev",
            "viewer",
            signaling_url=self.signaling_url,
        )
        self.assertIsNotNone(share_payload)
        invite_code = str((share_payload or {}).get("inviteCode", "")).strip()
        previous_token = str((share_payload or {}).get("token", "")).strip()

        new_token = await self.host.rotate_room_token("dev", "viewer", expires_in_seconds=60)

        self.assertIsNotNone(new_token)
        self.assertNotEqual(new_token, previous_token)

        peer_connection, _, _, _ = self._build_client_transport()
        try:
            status, payload = await self._signal_peer_connection(
                peer_connection,
                invite_code=invite_code,
                client_name="stale-viewer",
            )
            self.assertEqual(status, 403)
            self.assertEqual(payload.get("error"), "invalid_multiplayer_auth")
        finally:
            with contextlib.suppress(Exception):
                await peer_connection.close()

    async def test_pending_members_can_be_approved_and_driver_handed_off(self) -> None:
        await self.host.set_room_lobby("dev", True)
        first = await self._connect_initialized_client(
            role="prompter",
            client_name="driver-one",
        )
        second = await self._connect_initialized_client(
            role="viewer",
            client_name="viewer-two",
        )

        try:
            self.assertEqual(first.approval_state, "pending")
            self.assertEqual(second.approval_state, "pending")

            approved_first = await self.host.approve_room_member("dev", first.connection_id)
            approved_second = await self.host.approve_room_member("dev", second.connection_id)
            self.assertTrue(approved_first)
            self.assertTrue(approved_second)

            await self._wait_until(
                lambda: self.host.rooms["dev"].members[first.connection_id].approved
                and self.host.rooms["dev"].members[second.connection_id].approved
            )
            self.assertEqual(self.host.rooms["dev"].members[first.connection_id].role, "prompter")

            handed_off = await self.host.handoff_room_prompter("dev", second.connection_id)
            self.assertTrue(handed_off)

            await self._wait_until(
                lambda: self.host.rooms["dev"].members[first.connection_id].role == "viewer"
                and self.host.rooms["dev"].members[second.connection_id].role == "prompter"
            )

            for queue in (first.inbound_messages, second.inbound_messages):
                role_update = await self._recv_message(
                    queue,
                    lambda message: message.get("method") == "poor-cli/memberRoleUpdated"
                    and message.get("params", {}).get("connectionId") == second.connection_id
                    and message.get("params", {}).get("role") == "prompter",
                )
                self.assertEqual(role_update["params"]["uiRole"], "driver")
        finally:
            await self._close_client(first)
            await self._close_client(second)
            await self._wait_until(
                lambda: not self.host.connections
                and not self.host.rooms["dev"].members
                and not self.host._peer_connections
            )

    async def test_invite_can_reconnect_after_disconnect(self) -> None:
        share_payload = self.host.build_room_share_payload(
            "dev",
            "viewer",
            signaling_url=self.signaling_url,
        )
        self.assertIsNotNone(share_payload)
        invite_code = str((share_payload or {}).get("inviteCode", "")).strip()
        invite_token = str((share_payload or {}).get("token", "")).strip()

        first = await self._connect_initialized_client(
            role="viewer",
            client_name="viewer-one",
            invite_code=invite_code,
            invite_token=invite_token,
        )
        first_connection_id = first.connection_id

        await self._close_client(first)
        await self._wait_until(
            lambda: not self.host.connections
            and not self.host.rooms["dev"].members
            and not self.host._peer_connections
        )

        second = await self._connect_initialized_client(
            role="viewer",
            client_name="viewer-one-rejoin",
            invite_code=invite_code,
            invite_token=invite_token,
        )

        try:
            self.assertNotEqual(second.connection_id, first_connection_id)
            self.assertEqual(second.approval_state, "approved")
            self.assertIn(second.connection_id, self.host.rooms["dev"].members)
        finally:
            await self._close_client(second)
            await self._wait_until(
                lambda: not self.host.connections
                and not self.host.rooms["dev"].members
                and not self.host._peer_connections
            )

    async def test_streaming_chunks_only_reach_viewers_and_active_requester(self) -> None:
        prompter = await self._connect_initialized_client(
            role="prompter",
            client_name="driver-one",
        )
        viewer_one = await self._connect_initialized_client(
            role="viewer",
            client_name="viewer-one",
        )
        viewer_two = await self._connect_initialized_client(
            role="viewer",
            client_name="viewer-two",
        )

        try:
            room = self.host.rooms["dev"]
            room.active_connection_id = viewer_one.connection_id

            await self.host._broadcast_streaming_chunk(
                room,
                request_id="req-1",
                content="hello world",
                done=False,
            )

            for queue in (viewer_one.inbound_messages, viewer_two.inbound_messages):
                chunk = await self._recv_message(
                    queue,
                    lambda message: message.get("method") == "poor-cli/streamingChunk"
                    and message.get("params", {}).get("requestId") == "req-1",
                )
                self.assertEqual(chunk["params"]["content"], "hello world")
                self.assertFalse(chunk["params"]["done"])

            await self._assert_no_matching_message(
                prompter.inbound_messages,
                lambda message: message.get("method") == "poor-cli/streamingChunk"
                and message.get("params", {}).get("requestId") == "req-1",
            )
        finally:
            await self._close_client(prompter)
            await self._close_client(viewer_one)
            await self._close_client(viewer_two)
            await self._wait_until(
                lambda: not self.host.connections
                and not self.host.rooms["dev"].members
                and not self.host._peer_connections
            )
