import asyncio
import contextlib
import json
import unittest
from types import SimpleNamespace
from typing import Any

from poor_cli.multiplayer import ConnectionState, MultiplayerHost
from poor_cli.multiplayer_queue import MultiPrompterQueue, MultiPrompterQueueFull
from poor_cli.multiplayer_session import CollaborationSession
from poor_cli.server.types import JsonRpcError, JsonRpcMessage


class _StubRoomServer:
    def __init__(self) -> None:
        self.permission_mode = "prompt"
        self._embedded_multiplayer_room = False
        self.write_message_stdio = None

    async def handle_initialize(self, params):
        del params
        return {"capabilities": {}}

    async def dispatch(self, message):
        return JsonRpcMessage(id=message.id, result={"ok": True})

    async def _handle_notification(self, message):
        del message
        return None


class _FakeWs:
    def __init__(self) -> None:
        self.closed = False
        self.sent: list[dict[str, Any]] = []

    async def send_str(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self, code: int = 1000, message: bytes = b"") -> None:
        del code, message
        self.closed = True


def _member(connection_id: str, role: str = "prompter") -> SimpleNamespace:
    return SimpleNamespace(
        connection_id=connection_id,
        client_name=connection_id,
        role=role,
        approved=True,
        initialized=True,
        hand_raised=False,
        connected_at=1.0,
        last_active=1.0,
        joined_at="2026-03-18T00:00:00+00:00",
        ws=SimpleNamespace(closed=False),
    )


def _room() -> SimpleNamespace:
    state = SimpleNamespace(
        name="dev",
        preset="mob",
        members={"a": _member("a"), "b": _member("b")},
        active_connection_id=None,
        hand_raise_queue=[],
        agenda=[],
    )
    state.session = CollaborationSession(
        state,
        is_member_closed=lambda member: getattr(member.ws, "closed", False),
    )
    return state


def _msg(message_id: int, method: str = "poor-cli/chat") -> JsonRpcMessage:
    return JsonRpcMessage(id=message_id, method=method, params={"requestId": f"r-{message_id}"})


class MultiPrompterQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_robin_per_user_fifo(self) -> None:
        queue = MultiPrompterQueue(_room(), max_concurrent=1, max_per_user=10)
        await queue.submit("a", _msg(1))
        await queue.submit("a", _msg(2))
        await queue.submit("b", _msg(3))
        await queue.submit("b", _msg(4))

        seen = []
        for _ in range(4):
            request = await queue.next()
            self.assertIsNotNone(request)
            seen.append((request.connection_id, request.message.id))
            await queue.task_done(request)

        self.assertEqual(seen, [("a", 1), ("b", 3), ("a", 2), ("b", 4)])

    async def test_max_per_user_rejects_queued_and_inflight(self) -> None:
        queue = MultiPrompterQueue(_room(), max_concurrent=1, max_per_user=1)
        await queue.submit("a", _msg(1))
        with self.assertRaises(MultiPrompterQueueFull):
            await queue.submit("a", _msg(2))
        request = await queue.next()
        self.assertIsNotNone(request)
        with self.assertRaises(MultiPrompterQueueFull):
            await queue.submit("a", _msg(3))
        await queue.task_done(request)
        await queue.submit("a", _msg(4))
        self.assertEqual(queue.qsize(), 1)

    async def test_disconnect_cleanup_drops_pending_items(self) -> None:
        queue = MultiPrompterQueue(_room(), max_concurrent=1, max_per_user=10)
        await queue.submit("a", _msg(1))
        await queue.submit("b", _msg(2))
        await queue.submit("a", _msg(3))

        removed = await queue.remove_connection("a")

        self.assertTrue(removed)
        self.assertEqual(
            [(item["connectionId"], item["requestId"]) for item in queue.snapshot()],
            [("b", "r-2")],
        )

    async def test_owner_author_cancel_and_non_author_rejected(self) -> None:
        host = MultiplayerHost(
            bind_host="127.0.0.1",
            port=8765,
            room_names=["dev"],
            server_factory=_StubRoomServer,
            message_cls=JsonRpcMessage,
            rpc_error_cls=JsonRpcError,
            multi_prompter_enabled=True,
        )
        try:
            room = host.rooms["dev"]
            if room.worker_task is not None:
                room.worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await room.worker_task
            a = self._add_member(host, "a")
            b = self._add_member(host, "b")

            await host._handle_message(a, _msg(1))
            queue_id = room.multi_queue.snapshot()[0]["queueId"]
            await host._handle_cancel_queue_item(
                b,
                room,
                JsonRpcMessage(id=2, method="poor-cli/cancelQueueItem", params={"queueId": queue_id}),
            )
            self.assertEqual(b.ws.sent[-1]["error"]["data"]["error_code"], "permission_denied")

            await host._handle_cancel_queue_item(
                a,
                room,
                JsonRpcMessage(id=3, method="poor-cli/cancelQueueItem", params={"queueId": queue_id}),
            )
            self.assertTrue(a.ws.sent[-1]["result"]["cancelled"])

            await host._handle_message(a, _msg(4))
            queue_id = room.multi_queue.snapshot()[0]["queueId"]
            owner_result = await host.cancel_room_queue_item("dev", queue_id, owner=True)
            self.assertTrue(owner_result["cancelled"])
        finally:
            await host.stop()

    async def test_feature_flag_off_uses_legacy_single_queue_golden(self) -> None:
        host = MultiplayerHost(
            bind_host="127.0.0.1",
            port=8765,
            room_names=["dev"],
            server_factory=_StubRoomServer,
            message_cls=JsonRpcMessage,
            rpc_error_cls=JsonRpcError,
            multi_prompter_enabled=False,
        )
        try:
            room = host.rooms["dev"]
            if room.worker_task is not None:
                room.worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await room.worker_task
            conn = self._add_member(host, "a")

            await host._handle_message(conn, _msg(1))

            self.assertIsNone(room.multi_queue)
            self.assertEqual(room.request_queue.qsize(), 1)
            self.assertEqual(len(conn.ws.sent), 1)
            self.assertEqual(
                conn.ws.sent[0],
                {
                    "jsonrpc": "2.0",
                    "method": "poor-cli/roomEvent",
                    "params": {
                        "eventType": "queued",
                        "room": "dev",
                        "mode": "pair",
                        "requestId": "r-1",
                        "actor": "a",
                        "queueDepth": 1,
                        "memberCount": 1,
                        "activeConnectionId": "",
                        "lobbyEnabled": False,
                        "preset": "pairing",
                        "agendaSummary": {"total": 0, "open": 0, "openItems": []},
                        "members": [
                            {
                                "connectionId": "a",
                                "role": "prompter",
                                "clientName": "a",
                                "displayName": "a",
                                "uiRole": "driver",
                                "initialized": True,
                                "connected": True,
                                "active": False,
                                "approved": True,
                                "approvalState": "approved",
                                "handRaised": False,
                                "queuePosition": 0,
                                "joinedAt": "2026-03-18T00:00:00+00:00",
                            }
                        ],
                        "details": {},
                        "authorConnectionId": "a",
                        "authorDisplayName": "a",
                        "authorRole": "prompter",
                    },
                },
            )
        finally:
            await host.stop()

    def _add_member(self, host: MultiplayerHost, connection_id: str) -> ConnectionState:
        conn = ConnectionState(
            connection_id=connection_id,
            ws=_FakeWs(),
            role="prompter",
            room_name="dev",
            initialized=True,
            client_name=connection_id,
            joined_at="2026-03-18T00:00:00+00:00",
        )
        conn.connected_at = 1.0
        conn.last_active = 1.0
        room = host.rooms["dev"]
        room.members[connection_id] = conn
        host.connections[connection_id] = conn
        return conn


if __name__ == "__main__":
    unittest.main()
