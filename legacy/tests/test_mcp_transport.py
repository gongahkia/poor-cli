from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from aiohttp import web

from poor_cli.mcp.http import StreamableHttpTransport
from poor_cli.mcp.stdio import StdioTransport


def _write_stdio_server(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            TOOLS = [{"name": "echo", "description": "echo", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}]

            def result(request):
                method = request.get("method")
                req_id = request.get("id")
                if method == "initialize":
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "stdio-test"}}}
                if method == "tools/list":
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
                if method == "tools/call":
                    text = request.get("params", {}).get("arguments", {}).get("text", "")
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"stdio:{text}"}]}}
                if method in ("resources/list", "prompts/list"):
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": [], "prompts": []}}
                if method == "ping":
                    return {"jsonrpc": "2.0", "id": req_id, "result": {}}
                return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": method}}

            for line in sys.stdin:
                sys.stdout.write(json.dumps(result(json.loads(line))) + "\\n")
                sys.stdout.flush()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


class TestMcpTransports(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_transport_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            server = Path(td) / "server.py"
            _write_stdio_server(server)
            transport = StdioTransport([sys.executable, str(server)])
            await transport.connect()
            try:
                await transport.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                response = await transport.recv()
                self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")
            finally:
                await transport.close()

    async def test_http_transport_roundtrip_with_mocked_server(self) -> None:
        async def handle(request: web.Request) -> web.Response:
            payload = await request.json()
            self.assertIn("application/json", request.headers.get("Accept", ""))
            self.assertIn("text/event-stream", request.headers.get("Accept", ""))
            if payload["method"] == "initialize":
                return web.json_response(
                    {"jsonrpc": "2.0", "id": payload["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}},
                    headers={"Mcp-Session-Id": "session-1"},
                )
            return web.json_response({"jsonrpc": "2.0", "id": payload["id"], "result": {"ok": True}})

        app = web.Application()
        app.router.add_post("/mcp", handle)

        async def delete(_request: web.Request) -> web.Response:
            return web.Response(status=202)

        app.router.add_delete("/mcp", delete)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        transport = StreamableHttpTransport(f"http://127.0.0.1:{port}/mcp")
        await transport.connect()
        try:
            await transport.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            response = await transport.recv()
            self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")
            self.assertEqual(transport.session_id, "session-1")
        finally:
            await transport.close()
            await runner.cleanup()
