"""Tests for stdio <-> WebSocket bridge mode."""

import asyncio
import json
import socket
from collections import deque
from typing import Deque, List

import pytest
aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web

from poor_cli.server import JsonRpcMessage, _run_stdio_bridge



def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _FakeStdioServer:
    instances: List["_FakeStdioServer"] = []

    def __init__(self):
        self.read_queue: Deque[JsonRpcMessage] = deque(
            [
                JsonRpcMessage(
                    id=1,
                    method="initialize",
                    params={"provider": "gemini", "streaming": True},
                ),
                JsonRpcMessage(
                    id=2,
                    method="poor-cli/getConfig",
                    params={},
                ),
            ]
        )
        self.written: List[JsonRpcMessage] = []
        _FakeStdioServer.instances.append(self)

    async def read_message_stdio(self):
        await asyncio.sleep(0)
        if self.read_queue:
            return self.read_queue.popleft()
        return None

    async def write_message_stdio(self, message: JsonRpcMessage):
        self.written.append(message)


@pytest.mark.asyncio
async def test_bridge_injects_room_token_and_forwards_ws_messages(monkeypatch):
    received_from_bridge: List[dict] = []

    async def ws_handler(request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                payload = json.loads(msg.data)
                received_from_bridge.append(payload)

                if payload.get("id") == 1:
                    await ws.send_str(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "method": "poor-cli/roomEvent",
                                "params": {
                                    "eventType": "member_joined",
                                    "room": "dev",
                                },
                            }
                        )
                    )

                await ws.send_str(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "result": {"ok": True},
                        }
                    )
                )

        return ws

    app = web.Application()
    app.router.add_get("/rpc", ws_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    port = _free_port()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()

    monkeypatch.setattr("poor_cli.server.PoorCLIServer", _FakeStdioServer)

    try:
        await _run_stdio_bridge(
            url=f"ws://127.0.0.1:{port}/rpc",
            room="dev",
            token="tok-123",
        )

        assert received_from_bridge, "bridge did not forward requests to websocket"
        init_req = received_from_bridge[0]
        assert init_req["method"] == "initialize"
        assert init_req["params"]["room"] == "dev"
        assert init_req["params"]["inviteToken"] == "tok-123"
        assert init_req["params"]["clientName"] == "stdio-bridge"

        fake_instance = _FakeStdioServer.instances[-1]
        methods = [m.method for m in fake_instance.written]
        assert "poor-cli/roomEvent" in methods
        assert any(m.id == 1 and m.result == {"ok": True} for m in fake_instance.written)
        assert any(m.id == 2 and m.result == {"ok": True} for m in fake_instance.written)
    finally:
        await runner.cleanup()
