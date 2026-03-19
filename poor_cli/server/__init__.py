"""PoorCLI JSON-RPC Server package."""

from .types import JsonRpcMessage, JsonRpcError, InvalidParamsError, ManagedServiceRuntime
from .error_formatter import _sanitize_exception_message, _MAX_ERROR_MESSAGE_LEN
from .transport import StdioTransport

def main() -> None:
    from .cli import main as _main

    _main()


def __getattr__(name: str):
    if name in {"PoorCLIServer", "StreamingJsonRpcServer"}:
        from .runtime import PoorCLIServer, StreamingJsonRpcServer

        mapping = {
            "PoorCLIServer": PoorCLIServer,
            "StreamingJsonRpcServer": StreamingJsonRpcServer,
        }
        return mapping[name]
    if name in {"NgrokTunnel", "_run_stdio_bridge"}:
        from .multiplayer_runtime import NgrokTunnel, _run_stdio_bridge

        mapping = {
            "NgrokTunnel": NgrokTunnel,
            "_run_stdio_bridge": _run_stdio_bridge,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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
