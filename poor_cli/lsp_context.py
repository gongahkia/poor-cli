"""
Optional lightweight LSP client for context resolution.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)

LSP_SERVER_MAP: Dict[str, List[str]] = {
    "python": ["pyright-langserver", "--stdio"],
    "typescript": ["typescript-language-server", "--stdio"],
    "javascript": ["typescript-language-server", "--stdio"],
    "rust": ["rust-analyzer"],
    "go": ["gopls"],
}


def detect_project_language(root_path: str) -> Optional[str]:
    root = Path(root_path)
    checks = [
        (["pyproject.toml", "setup.py", "requirements.txt"], "python"),
        (["package.json"], "typescript"),
        (["Cargo.toml"], "rust"),
        (["go.mod"], "go"),
    ]
    for files, language in checks:
        if any((root / name).exists() for name in files):
            return language
    return None


class LSPClient:
    """Very small JSON-RPC-over-stdio LSP client."""

    def __init__(self, language: str, root_path: str):
        self.language = language
        self.root_path = root_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self.available = False
        self._request_id = 1
        self._opened_docs: set = set()

    async def _send_payload(self, payload: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("LSP process not running")
        body = json.dumps(payload, ensure_ascii=False)
        frame = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n{body}"
        self.process.stdin.write(frame.encode("utf-8"))
        await self.process.stdin.drain()

    async def _read_payload(self) -> Dict[str, Any]:
        if not self.process or not self.process.stdout:
            raise RuntimeError("LSP process not running")

        content_length = 0
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise RuntimeError("LSP server closed stream")
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded == "":
                break
            if decoded.lower().startswith("content-length:"):
                content_length = int(decoded.split(":", 1)[1].strip())

        if content_length <= 0:
            raise RuntimeError("Invalid LSP Content-Length")

        data = await self.process.stdout.readexactly(content_length)
        return json.loads(data.decode("utf-8", errors="replace"))

    async def start(self) -> None:
        command = LSP_SERVER_MAP.get(self.language)
        if not command:
            self.available = False
            return
        if shutil.which(command[0]) is None:
            logger.info(f"LSP binary not found for {self.language}: {command[0]}")
            self.available = False
            return

        self.process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        init_params = {
            "processId": os.getpid(),
            "rootUri": Path(self.root_path).resolve().as_uri(),
            "capabilities": {},
            "workspaceFolders": [
                {
                    "uri": Path(self.root_path).resolve().as_uri(),
                    "name": Path(self.root_path).name,
                }
            ],
        }
        await self._send_request("initialize", init_params)
        await self._send_notification("initialized", {})
        self.available = True

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        request_id = self._request_id
        self._request_id += 1
        await self._send_payload(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        while True:
            response = await self._read_payload()
            if response.get("id") == request_id:
                return response.get("result", {})

    async def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        await self._send_payload(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )

    async def _ensure_document_open(self, file_path: str) -> None:
        resolved = str(Path(file_path).resolve())
        if resolved in self._opened_docs:
            return
        try:
            with open(resolved, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            text = ""
        await self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": Path(resolved).as_uri(),
                    "languageId": self.language,
                    "version": 1,
                    "text": text,
                }
            },
        )
        self._opened_docs.add(resolved)

    async def get_symbols(self, file_path: str) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        await self._ensure_document_open(file_path)
        result = await self._send_request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": Path(file_path).resolve().as_uri()}},
        )
        return result or []

    async def get_definition(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        await self._ensure_document_open(file_path)
        result = await self._send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": Path(file_path).resolve().as_uri()},
                "position": {"line": line, "character": character},
            },
        )
        if isinstance(result, list):
            return result[0] if result else None
        if isinstance(result, dict):
            return result
        return None

    async def get_references(
        self,
        file_path: str,
        line: int,
        character: int
    ) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        await self._ensure_document_open(file_path)
        result = await self._send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": Path(file_path).resolve().as_uri()},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True},
            },
        )
        if isinstance(result, list):
            return result
        return []

    async def shutdown(self) -> None:
        if not self.process:
            return
        try:
            await self._send_request("shutdown", {})
            await self._send_notification("exit", {})
        except Exception:
            pass
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=2)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        self.process = None
        self.available = False
