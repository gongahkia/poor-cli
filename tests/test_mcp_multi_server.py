from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from aiohttp import web

from poor_cli.mcp import MultiMcp, discover_mcp_config
from tests.test_mcp_transport import _write_stdio_server


class TestMultiMcp(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runner: web.AppRunner | None = None

    async def asyncTearDown(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()

    async def _start_http_mcp(self) -> str:
        async def handle(request: web.Request) -> web.Response:
            payload = await request.json()
            method = payload.get("method")
            req_id = payload.get("id")
            if method == "initialize":
                return web.json_response({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}}, headers={"Mcp-Session-Id": "http-session"})
            if method == "tools/list":
                return web.json_response({"jsonrpc": "2.0", "id": req_id, "result": {"tools": [{"name": "echo", "description": "echo", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}]}})
            if method == "tools/call":
                text = payload.get("params", {}).get("arguments", {}).get("text", "")
                return web.json_response({"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"http:{text}"}]}})
            if method == "resources/list":
                return web.json_response({"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}})
            if method == "prompts/list":
                return web.json_response({"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}})
            if method == "ping":
                return web.json_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
            return web.json_response({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": method}}, status=400)

        app = web.Application()
        app.router.add_post("/mcp", handle)

        async def delete(_request: web.Request) -> web.Response:
            return web.Response(status=202)

        app.router.add_delete("/mcp", delete)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/mcp"

    async def test_multi_server_aggregates_tools_with_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            server = root / "stdio_server.py"
            _write_stdio_server(server)
            http_url = await self._start_http_mcp()
            config_dir = root / ".poor-cli"
            config_dir.mkdir()
            (config_dir / "mcp.json").write_text(
                json.dumps(
                    {
                        "multi": True,
                        "registry_autodiscover": False,
                        "servers": [
                            {"name": "stdio", "transport": "stdio", "command": [sys.executable, str(server)], "enabled": True},
                            {"name": "http", "transport": "http", "url": http_url, "enabled": True},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manager = MultiMcp(discover_mcp_config(repo_root=root), repo_root=root)
            await manager.start_all()
            try:
                tools = await manager.tools()
                names = {tool["name"] for tool in tools}
                self.assertEqual(names, {"stdio:echo", "http:echo"})
                self.assertEqual(await manager.call_tool("stdio:echo", {"text": "a"}), "stdio:a")
                self.assertEqual(await manager.call_tool("http:echo", {"text": "b"}), "http:b")
            finally:
                await manager.shutdown()

    async def test_health_reports_per_server(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            server = root / "stdio_server.py"
            _write_stdio_server(server)
            manager = MultiMcp({"stdio": {"transport": "stdio", "command": [sys.executable, str(server)], "enabled": True}}, repo_root=root)
            await manager.start_all()
            try:
                self.assertEqual(await manager.health(), {"stdio": True})
            finally:
                await manager.shutdown()

    async def test_multi_false_keeps_legacy_bare_tool_names(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            server = root / "stdio_server.py"
            _write_stdio_server(server)
            manager = MultiMcp(
                {
                    "multi": False,
                    "servers": [
                        {"name": "stdio", "transport": "stdio", "command": [sys.executable, str(server)]},
                    ],
                },
                repo_root=root,
            )
            await manager.start_all()
            try:
                self.assertEqual({tool["name"] for tool in await manager.tools()}, {"echo"})
                self.assertEqual(await manager.call_tool("echo", {"text": "legacy"}), "stdio:legacy")
            finally:
                await manager.shutdown()

    async def test_registry_disabled_by_default_and_on_demand(self) -> None:
        manager = MultiMcp({})
        result = await manager.registry_search("github")
        self.assertFalse(result["enabled"])
        self.assertEqual(result["servers"], [])

    async def test_sse_transport_is_rejected(self) -> None:
        manager = MultiMcp({"old": {"transport": "sse", "url": "http://127.0.0.1/mcp"}})
        await manager.start_all()
        self.assertIn("deprecated", manager.status()["servers"]["old"]["error"])
