"""Shared types for the JSON-RPC server package."""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class JsonRpcMessage:
    """JSON-RPC 2.0 message."""

    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        d: Dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JsonRpcMessage":
        """Create from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )

    @classmethod
    def from_json(cls, text: str) -> "JsonRpcMessage":
        """Parse from JSON string."""
        data = json.loads(text)
        return cls.from_dict(data)


class JsonRpcError:
    """JSON-RPC 2.0 error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    @classmethod
    def make_error(cls, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        """Create an error object."""
        error: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return error


class InvalidParamsError(Exception):
    """Raised when JSON-RPC method params fail validation."""


@dataclass
class ManagedServiceRuntime:
    """Track a long-running local service process managed by the server."""

    name: str
    command: List[str]
    command_display: str
    cwd: Optional[str]
    process: asyncio.subprocess.Process
    log_path: Path
    log_handle: Any
    started_at: str
    last_exit_code: Optional[int] = None
