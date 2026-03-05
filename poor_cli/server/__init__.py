"""PoorCLI JSON-RPC Server package.

Re-exports the main server class and entry point for backward compatibility.
"""

from .types import JsonRpcMessage, JsonRpcError, InvalidParamsError, ManagedServiceRuntime
from .error_formatter import _sanitize_exception_message, _MAX_ERROR_MESSAGE_LEN
from .transport import StdioTransport

# Import the main server module — the PoorCLIServer class and main() remain there
# during incremental decomposition. This allows `poor_cli.server:main` entry point to work.
from .._server import PoorCLIServer, StreamingJsonRpcServer, NgrokTunnel, main, _run_stdio_bridge

__all__ = [
    "JsonRpcMessage",
    "JsonRpcError",
    "InvalidParamsError",
    "ManagedServiceRuntime",
    "StdioTransport",
    "PoorCLIServer",
    "StreamingJsonRpcServer",
    "NgrokTunnel",
    "main",
    "_sanitize_exception_message",
    "_MAX_ERROR_MESSAGE_LEN",
]
