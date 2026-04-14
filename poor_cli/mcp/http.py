"""MCP Streamable HTTP transport."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from .stdio import McpTransport

MCP_PROTOCOL_VERSION = "2025-06-18"


class StreamableHttpTransport(McpTransport):
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        if not url:
            raise ValueError("HTTP MCP transport requires a URL")
        self.url = url
        self.headers = headers or {}
        self.session_id: Optional[str] = None
        self._session: Any = None
        self._responses: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    async def connect(self) -> None:
        try:
            import aiohttp
        except ImportError as exc:
            raise RuntimeError("aiohttp required for MCP Streamable HTTP transport") from exc
        self._session = aiohttp.ClientSession()

    async def send(self, msg: Dict[str, Any]) -> None:
        if self._session is None:
            await self.connect()
        headers = {
            **self.headers,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        async with self._session.post(self.url, json=msg, headers=headers) as resp:
            if resp.status == 404 and self.session_id:
                self.session_id = None
                raise RuntimeError("MCP HTTP session expired")
            resp.raise_for_status()
            session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("MCP-Session-Id")
            if session_id:
                self.session_id = session_id
            content_type = resp.headers.get("Content-Type", "")
            text = await resp.text()
        if not text.strip():
            await self._responses.put({})
            return
        if "text/event-stream" in content_type:
            for event in _parse_sse_messages(text):
                await self._responses.put(event)
            return
        await self._responses.put(json.loads(text))

    async def recv(self) -> Dict[str, Any]:
        return await self._responses.get()

    async def close(self) -> None:
        if self._session is None:
            return
        try:
            if self.session_id:
                headers = {**self.headers, "MCP-Protocol-Version": MCP_PROTOCOL_VERSION, "Mcp-Session-Id": self.session_id}
                try:
                    async with self._session.delete(self.url, headers=headers):
                        pass
                except Exception:
                    pass
        finally:
            await self._session.close()
            self._session = None


def _parse_sse_messages(body: str) -> list[Dict[str, Any]]:
    messages: list[Dict[str, Any]] = []
    data_lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                messages.append(json.loads("\n".join(data_lines)))
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        messages.append(json.loads("\n".join(data_lines)))
    return messages
