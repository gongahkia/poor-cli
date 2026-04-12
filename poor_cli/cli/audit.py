"""Audit CLI subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def run_audit_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli audit")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    export = sub.add_parser("export")
    export.add_argument("--from", dest="start_time")
    export.add_argument("--since", dest="start_time")
    export.add_argument("--to", dest="end_time")
    export.add_argument("--until", dest="end_time")
    export.add_argument("--out", dest="output")
    export.add_argument("--output", dest="output")
    rotate = sub.add_parser("rotate")
    rotate.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))

    from ..audit_log import AuditLogger

    logger = AuditLogger(audit_dir=Path.cwd() / ".poor-cli")
    if args.subcommand == "export":
        count = logger.export_range(
            start_time=args.start_time,
            end_time=args.end_time,
            output_path=Path(args.output).expanduser() if args.output else None,
        )
        if args.output:
            print(f"Exported {count} audit events to {args.output}")
        return 0
    if args.subcommand == "rotate":
        result = logger.rotate_if_needed()
        if args.json:
            import json

            print(json.dumps(result, indent=2))
        else:
            print(f"Archived {result['archived']} audit events")
        return 0
    raise SystemExit(f"Unknown audit subcommand: {args.subcommand}")
