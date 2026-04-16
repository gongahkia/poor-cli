"""
Backward-compatible server exports.

The implementation now lives under ``poor_cli.server``.
"""

from .server.cli import main
from .server.runtime import PoorCLIServer, StreamingJsonRpcServer

__all__ = [
    "PoorCLIServer",
    "StreamingJsonRpcServer",
    "main",
]


if __name__ == "__main__":
    main()
