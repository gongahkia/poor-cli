"""CLI entrypoint for the server package."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List

from ..cli_errors import run_with_cli_error_handling


def _main() -> None:
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(description="PoorCLI JSON-RPC Server for automation clients")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: List[logging.Handler] = []
    log_file = os.environ.get("POOR_CLI_SERVER_LOG_FILE", "").strip()
    if log_file:
        try:
            log_path = Path(log_file).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
        except Exception as error:
            print(f"Warning: failed to open server log file {log_file}: {error}", file=sys.stderr)
    if not handlers:
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

    from .runtime import PoorCLIServer

    server = PoorCLIServer()
    asyncio.run(server.run_stdio())


def main() -> None:
    run_with_cli_error_handling(_main)
