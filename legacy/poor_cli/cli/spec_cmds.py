"""Spec/PRD-driven development CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from poor_cli.spec_mode import SpecMode


def run_spec_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli spec")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_new = sub.add_parser("new")
    p_new.add_argument("path")
    p_run = sub.add_parser("run")
    p_run.add_argument("path")
    p_run.add_argument("--json", action="store_true")
    p_status = sub.add_parser("status")
    p_status.add_argument("spec_id")
    p_status.add_argument("--json", action="store_true")
    p_resume = sub.add_parser("resume")
    p_resume.add_argument("spec_id")
    p_resume.add_argument("--json", action="store_true")
    p_abort = sub.add_parser("abort")
    p_abort.add_argument("spec_id")
    p_abort.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    mode = SpecMode(Path.cwd())

    if args.subcommand == "new":
        print(mode.new(Path(args.path)))
        return 0
    if args.subcommand == "run":
        return _print_run(mode.run(Path(args.path)), json_output=bool(args.json))
    if args.subcommand == "status":
        return _print_run(mode.status(args.spec_id), json_output=bool(args.json))
    if args.subcommand == "resume":
        return _print_run(mode.resume(args.spec_id), json_output=bool(args.json))
    if args.subcommand == "abort":
        return _print_run(mode.abort(args.spec_id), json_output=bool(args.json))
    raise SystemExit(f"Unknown spec subcommand: {args.subcommand}")


def _print_run(run: Any, *, json_output: bool) -> int:
    payload = run.to_dict()
    if json_output:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{payload['specId']} {payload['status']} {payload['title']}")
        for task in payload["subtasks"]:
            deps = ",".join(task["dependsOn"])
            dep_text = f" deps=[{deps}]" if deps else ""
            print(f"  {task['id']:8s} {task['status']:8s} {task['title']}{dep_text}")
    return 0
