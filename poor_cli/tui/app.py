"""Textual poor-cli frontend launcher."""

from __future__ import annotations

import argparse
from typing import List, Optional

from .rpc_client import BackendConfiguration
from .textual_app import run_textual_tui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli tui")
    parser.add_argument("--repo-root", help="Working repository root for the backend server")
    parser.add_argument(
        "--python",
        dest="python_executable",
        help="Python executable to launch poor-cli.server",
    )
    parser.add_argument("--provider", help="Initial provider override")
    parser.add_argument("--model", help="Initial model override")
    parser.add_argument("--api-key", help="Initial API key override")
    parser.add_argument(
        "--permission-mode",
        default="default",
        help="Permission mode for this TUI session",
    )
    parser.add_argument(
        "--sandbox-preset",
        default="workspace-write",
        help="Sandbox preset for this TUI session",
    )
    parser.add_argument(
        "--validate-api-key",
        action="store_true",
        help="Validate the configured API key during initialize",
    )
    parser.add_argument(
        "--multiplayer-host",
        action="store_true",
        help="Let this TUI consume and execute prompts from the multiplayer foreground queue",
    )
    return parser


def run_tui(configuration: BackendConfiguration) -> int:
    return run_textual_tui(configuration)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configuration = BackendConfiguration.detected(
        repo_root=args.repo_root or "",
        python_executable=args.python_executable or "",
        provider=args.provider or "",
        model=args.model or "",
        api_key=args.api_key or "",
        permission_mode=args.permission_mode,
        sandbox_preset=args.sandbox_preset,
        validate_api_key=bool(args.validate_api_key),
        enable_multiplayer_queue=bool(args.multiplayer_host),
    )
    return run_tui(configuration)
