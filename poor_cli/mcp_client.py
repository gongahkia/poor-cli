"""
Minimal MCP client/manager integration.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)


def _json_schema_type_to_gemini(type_name: str) -> str:
    mapping = {
        "string": "STRING",
        "number": "NUMBER",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }
    return mapping.get(type_name.lower(), "STRING")


class MCPClient:
    """Single MCP server client process."""

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process: Optional[asyncio.subprocess.Process] = None
        self.capabilities: Dict[str, Any] = {}
        self._next_request_id = 3
        self._tools: List[Dict[str, Any]] = []

    async def _send(self, payload: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP process is not connected")
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

    async def _read_response(self) -> Dict[str, Any]:
        if not self.process or not self.process.stdout:
            raise RuntimeError("MCP process is not connected")
        raw = await self.process.stdout.readline()
        if not raw:
            raise RuntimeError("MCP server closed stream")
        return json.loads(raw.decode("utf-8", errors="replace"))

    async def connect(self) -> None:
        merged_env = dict(os.environ)
        merged_env.update(self.env)
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "poor-cli"},
            },
        }
        await self._send(init_payload)
        response = await self._read_response()
        self.capabilities = response.get("result", {}).get("capabilities", {})

    async def list_tools(self) -> List[Dict[str, Any]]:
        await self._send({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        })
        response = await self._read_response()
        tools = response.get("result", {}).get("tools", [])
        declarations: List[Dict[str, Any]] = []

        for tool in tools:
            name = tool.get("name", "")
            description = tool.get("description", "")
            input_schema = tool.get("inputSchema", {})
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])

            decl_props: Dict[str, Any] = {}
            for prop_name, prop_schema in properties.items():
                prop_type = prop_schema.get("type", "string")
                decl_props[prop_name] = {
                    "type": _json_schema_type_to_gemini(prop_type),
                    "description": prop_schema.get("description", ""),
                }

            declarations.append(
                {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "OBJECT",
                        "properties": decl_props,
                        "required": required,
                    },
                }
            )

        self._tools = declarations
        return declarations

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        request_id = self._next_request_id
        self._next_request_id += 1
        await self._send({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        response = await self._read_response()
        result = response.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            first = content[0]
            if isinstance(first, dict):
                return str(first.get("text", ""))
        return json.dumps(result, ensure_ascii=False)

    async def disconnect(self) -> None:
        if not self.process:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=3)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        self.process = None


class MCPManager:
    """Manage multiple MCP server clients and tool routing."""

    def __init__(self, servers_config: Dict[str, Any]):
        self.servers_config = servers_config
        self.clients: Dict[str, MCPClient] = {}
        self._declarations: List[Dict[str, Any]] = []
        self._tool_to_client: Dict[str, MCPClient] = {}
        self._server_status: Dict[str, Dict[str, Any]] = {}

    async def initialize(self) -> None:
        for server_name, cfg in self.servers_config.items():
            enabled = bool(cfg.get("enabled", True))
            self._server_status[server_name] = {
                "configured": True,
                "enabled": enabled,
                "connected": False,
                "toolCount": 0,
                "tools": [],
                "registeredTools": [],
                "error": None,
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
            }
            if not enabled:
                self._server_status[server_name]["error"] = "disabled by config"
                continue
            command = cfg.get("command")
            if not command:
                logger.warning(f"MCP server '{server_name}' missing command, skipping")
                self._server_status[server_name]["error"] = "missing command"
                continue
            client = MCPClient(
                name=server_name,
                command=command,
                args=cfg.get("args", []),
                env=cfg.get("env", {}),
            )
            try:
                await client.connect()
                declarations = await client.list_tools()
                allow_tools = {
                    str(name)
                    for name in cfg.get("allow_tools", []) or []
                    if str(name).strip()
                }
                deny_tools = {
                    str(name)
                    for name in cfg.get("deny_tools", []) or []
                    if str(name).strip()
                }
                filtered_declarations = []
                for decl in declarations:
                    tool_name = str(decl.get("name", "")).strip()
                    if not tool_name:
                        continue
                    if allow_tools and tool_name not in allow_tools:
                        continue
                    if tool_name in deny_tools:
                        continue
                    filtered_declarations.append(decl)
                self.clients[server_name] = client
                self._server_status[server_name]["connected"] = True
                self._server_status[server_name]["toolCount"] = len(declarations)
                self._server_status[server_name]["tools"] = [
                    decl.get("name", "") for decl in declarations if decl.get("name")
                ]
                self._server_status[server_name]["registeredTools"] = [
                    decl.get("name", "") for decl in filtered_declarations if decl.get("name")
                ]
                for decl in filtered_declarations:
                    tool_name = decl.get("name")
                    if not tool_name:
                        continue
                    self._tool_to_client[tool_name] = client
                    self._declarations.append(decl)
            except Exception as e:
                logger.warning(f"Failed to initialize MCP server '{server_name}': {e}")
                self._server_status[server_name]["error"] = str(e)

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        return list(self._declarations)

    def status(self) -> Dict[str, Any]:
        return {
            "configuredServers": len(self.servers_config),
            "connectedServers": len(self.clients),
            "toolCount": len(self._declarations),
            "servers": self._server_status,
        }

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        client = self._tool_to_client.get(name)
        if not client:
            raise RuntimeError(f"MCP tool not found: {name}")
        return await client.call_tool(name=name, arguments=arguments)

    async def shutdown(self) -> None:
        for client in self.clients.values():
            try:
                await client.disconnect()
            except Exception as e:
                logger.debug(f"MCP disconnect failed: {e}")
        for server_name in self._server_status:
            self._server_status[server_name]["connected"] = False
        self.clients.clear()
        self._tool_to_client.clear()
        self._declarations.clear()
