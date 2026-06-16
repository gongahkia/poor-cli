from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .config import explain_route, load_config, save_repo_config, set_route
from .route_policy import preflight_route


def add_route_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    route = sub.add_parser("route")
    route_sub = route.add_subparsers(dest="route_command")
    explain = route_sub.add_parser("explain")
    explain.add_argument("task", nargs="*")
    explain.add_argument("--role", default="executor")
    explain.add_argument("--json", action="store_true")
    explain.add_argument("--shim-agent", choices=("claude", "codex"))
    explain.add_argument("--shim-arg", action="append", default=[])
    explain.add_argument("--stdin-mode", choices=("tty", "pipe", "none"), default="tty")
    route_set = route_sub.add_parser("set")
    route_set.add_argument("--role", required=True)
    route_set.add_argument("--profile", required=True)
    route_set.add_argument("--model")


def handle_route_command(args: Any) -> int:
    config = load_config()
    if args.route_command == "explain":
        text = " ".join(args.task)
        if not text and not args.shim_agent:
            raise RuntimeError("route explain requires a task or --shim-agent")
        explanation = explain_route(config, text or " ".join(args.shim_arg), role=args.role)
        if args.shim_agent:
            explanation["preflight"] = preflight_route(
                str(args.shim_agent),
                list(args.shim_arg),
                str(args.stdin_mode),
                Path.cwd(),
                os.environ,
                prompt=text or None,
                route=explanation,
            )
        if args.json:
            print(json.dumps(explanation, indent=2, sort_keys=True))
            return 0
        print(
            f"role={explanation['role']} profile={explanation['profile']} model={explanation['model']} "
            f"provider={explanation['provider_kind']} reason={explanation['reason']}"
        )
        if "preflight" in explanation:
            preflight = explanation["preflight"]
            print(
                f"preflight={preflight['selected_route']} labels={','.join(preflight['labels']) or '-'} "
                f"intervention={preflight['intervention_reason'] or '-'}"
            )
        return 0
    if args.route_command == "set":
        path = save_repo_config(set_route(load_config(include_env=False), args.role, args.profile, args.model))
        print(f"route {args.role}: profile={args.profile} model={args.model or ''}")
        print(f"wrote {path}")
        return 0
    raise RuntimeError("missing route command")
