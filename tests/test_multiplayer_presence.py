import json
import unittest
from typing import Any

from poor_cli.multiplayer import ConnectionState, MultiplayerHost
from poor_cli.multiplayer_presence import PresenceTracker
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


class MultiplayerPresenceTests(unittest.IsolatedAsyncioTestCase):
    def test_tracker_debounces_typing_and_caps_broadcasts(self) -> None:
        now = 10.0

        def clock() -> float:
            return now

        tracker = PresenceTracker(
            debounce_ms=250,
            broadcast_interval_ms=500,
            clock=clock,
        )

        self.assertTrue(tracker.mark_typing("a"))
        now = 10.1
        self.assertFalse(tracker.mark_typing("a"))
        self.assertEqual(tracker.sweep(), {})
        now = 10.36
        self.assertEqual(tracker.sweep(), {})
        now = 10.5
        self.assertEqual(tracker.sweep(), {"a": False})
        self.assertEqual(tracker.sweep(), {})

    async def asyncSetUp(self) -> None:
        self.host = MultiplayerHost(
            bind_host="127.0.0.1",
            port=8765,
            room_names=["dev"],
            server_factory=_StubRoomServer,
            message_cls=JsonRpcMessage,
            rpc_error_cls=JsonRpcError,
            typing_presence_enabled=True,
            typing_presence_debounce_ms=250,
            typing_presence_broadcast_interval_ms=500,
        )

    async def asyncTearDown(self) -> None:
        await self.host.stop()

    def _add_member(self, connection_id: str, name: str) -> ConnectionState:
        conn = ConnectionState(
            connection_id=connection_id,
            ws=_FakeWs(),
            role="prompter",
            room_name="dev",
            initialized=True,
            client_name=name,
        )
        room = self.host.rooms["dev"]
        room.members[connection_id] = conn
        self.host.connections[connection_id] = conn
        return conn

    async def test_disconnect_cleanup_broadcasts_idle(self) -> None:
        first = self._add_member("a", "alice")
        second = self._add_member("b", "bob")
        room = self.host.rooms["dev"]

        await self.host._handle_set_typing(
            first,
            room,
            JsonRpcMessage(
                id=1,
                method="poor-cli/setTyping",
                params={"typing": True},
            ),
        )
        typing_events = [
            message for message in second.ws.sent
            if message.get("method") == "poor-cli/memberTyping"
        ]
        self.assertEqual(typing_events[-1]["params"]["typing"], True)

        await self.host._cleanup_connection(first)
        typing_events = [
            message for message in second.ws.sent
            if message.get("method") == "poor-cli/memberTyping"
        ]
        self.assertEqual(typing_events[-1]["params"]["connectionId"], "a")
        self.assertEqual(typing_events[-1]["params"]["displayName"], "alice")
        self.assertEqual(typing_events[-1]["params"]["typing"], False)

    async def test_new_joiner_snapshot_lists_current_presence(self) -> None:
        first = self._add_member("a", "alice")
        second = self._add_member("b", "bob")
        room = self.host.rooms["dev"]

        await self.host._handle_set_typing(
            first,
            room,
            JsonRpcMessage(
                id=1,
                method="poor-cli/setTyping",
                params={"typing": True},
            ),
        )
        await self.host._handle_list_presence(
            second,
            room,
            JsonRpcMessage(id=2, method="poor-cli/listPresence", params={}),
        )

        response = next(message for message in second.ws.sent if message.get("id") == 2)
        self.assertEqual(response["result"]["presence"], {"a": True})
        member = next(
            item for item in response["result"]["members"]
            if item["connectionId"] == "a"
        )
        self.assertEqual(member["displayName"], "alice")
        self.assertEqual(member["typing"], True)

    async def test_feature_flag_off_returns_method_not_found(self) -> None:
        await self.host.stop()
        self.host = MultiplayerHost(
            bind_host="127.0.0.1",
            port=8765,
            room_names=["dev"],
            server_factory=_StubRoomServer,
            message_cls=JsonRpcMessage,
            rpc_error_cls=JsonRpcError,
            typing_presence_enabled=False,
        )
        conn = self._add_member("a", "alice")

        await self.host._handle_message(
            conn,
            JsonRpcMessage(
                id=1,
                method="poor-cli/setTyping",
                params={"typing": True},
            ),
        )

        self.assertEqual(conn.ws.sent[-1]["error"]["code"], JsonRpcError.METHOD_NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
