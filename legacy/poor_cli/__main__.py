"""Lightweight poor-cli entrypoint with deferred command-module imports."""

from __future__ import annotations

import sys
from typing import Any, Sequence


def _run_server_mode(argv: Sequence[str]) -> int:
    from .server.cli import main as server_main

    original_argv = sys.argv[:]
    try:
        sys.argv = ["poor-cli server", *argv]
        server_main()
    finally:
        sys.argv = original_argv
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] in {"version", "--version", "-V"}:
        from . import __version__

        print(__version__)
        return
    if argv and argv[0] == "server":
        raise SystemExit(_run_server_mode(argv[1:]))

    from .cli_app import main as cli_app_main

    cli_app_main()


def __getattr__(name: str) -> Any:
    from . import cli_app

    return getattr(cli_app, name)


if __name__ == "__main__":
    main()
