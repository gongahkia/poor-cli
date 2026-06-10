"""MCP stdio transport."""

from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class McpTransport(ABC):
    @abstractmethod
    async def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, msg: Dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def recv(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class StdioTransport(McpTransport):
    def __init__(self, command: list[str], env: Optional[Dict[str, str]] = None):
        if not command:
            raise ValueError("stdio MCP transport requires a command")
        self.command = command
        self.env = env or {}
        self.process: Optional[asyncio.subprocess.Process] = None

    async def connect(self) -> None:
        merged_env = dict(os.environ)
        merged_env.update(self.env)
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )

    async def send(self, msg: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP stdio process is not connected")
        self.process.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.process.stdin.drain()

    async def recv(self) -> Dict[str, Any]:
        if not self.process or not self.process.stdout:
            raise RuntimeError("MCP stdio process is not connected")
        while True:
            raw = await self.process.stdout.readline()
            if not raw:
                raise RuntimeError("MCP stdio server closed stdout")
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                return json.loads(line)

    async def close(self) -> None:
        if not self.process:
            return
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None
