"""
Backward-compatible server exports.

The implementation now lives under ``poor_cli.server``.
"""

from .server.cli import main
from .server.multiplayer_runtime import (
    NgrokTunnel,
    _decode_bridge_invite,
    _print_multiplayer_join_hints,
    _run_multiplayer_host,
    _run_stdio_bridge,
)
from .server.runtime import PoorCLIServer, StreamingJsonRpcServer

__all__ = [
    "PoorCLIServer",
    "StreamingJsonRpcServer",
    "NgrokTunnel",
    "_print_multiplayer_join_hints",
    "_decode_bridge_invite",
    "_run_stdio_bridge",
    "_run_multiplayer_host",
    "main",
]


if __name__ == "__main__":
    main()
