"""CLI entrypoint for the server package."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List

from ..config import PermissionMode
from .multiplayer_runtime import _run_multiplayer_host, _run_stdio_bridge
from .runtime import PoorCLIServer


def main() -> None:
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(description="PoorCLI JSON-RPC Server for editor integration")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (for Neovim)")
    parser.add_argument("--host", action="store_true", help="Run multiplayer signaling host mode")
    parser.add_argument("--bind", default="127.0.0.1", help="Host bind address for --host mode")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Host port for --host mode (default: 8765)",
    )
    parser.add_argument(
        "--room",
        action="append",
        default=[],
        help="Multiplayer room name (repeatable in --host mode)",
    )
    parser.add_argument(
        "--permission-mode",
        default="prompt",
        choices=[mode.value for mode in PermissionMode],
        help="Default permission mode for multiplayer room engines",
    )
    parser.add_argument("--ngrok", action="store_true", help="Launch ngrok helper in --host mode")
    parser.add_argument("--bridge", action="store_true", help="Run stdio <-> P2P bridge mode")
    parser.add_argument("--invite", help="Invite code for --bridge mode")
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

    if args.host and args.bridge:
        raise SystemExit("Choose exactly one mode: either --host or --bridge (not both).")

    if args.bridge:
        if not args.invite:
            raise SystemExit("--bridge requires --invite")
        asyncio.run(_run_stdio_bridge(invite_code=args.invite))
        return

    if args.host:
        asyncio.run(
            _run_multiplayer_host(
                bind_host=args.bind,
                port=args.port,
                rooms=args.room,
                permission_mode=args.permission_mode,
                enable_ngrok=args.ngrok,
            )
        )
        return

    server = PoorCLIServer()
    asyncio.run(server.run_stdio())
