"""Backward-compatible server exports with lazy runtime imports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "PoorCLIServer",
    "StreamingJsonRpcServer",
    "main",
]


def main() -> None:
    from .cli import main as cli_main

    cli_main()


def __getattr__(name: str) -> Any:
    if name in {"PoorCLIServer", "StreamingJsonRpcServer"}:
        from .runtime import PoorCLIServer, StreamingJsonRpcServer

        mapping = {
            "PoorCLIServer": PoorCLIServer,
            "StreamingJsonRpcServer": StreamingJsonRpcServer,
        }
        return mapping[name]
    raise AttributeError(name)
