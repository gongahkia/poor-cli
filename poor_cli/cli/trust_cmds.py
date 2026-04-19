"""Trust-management CLI subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def run_trust_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli trust")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("status")
    p_add = sub.add_parser("trust")
    p_add.add_argument("--path")
    p_rm = sub.add_parser("untrust")
    p_rm.add_argument("--path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from ..trust import TrustManager

    mgr = TrustManager()
    cmd = args.subcommand or "status"
    if cmd == "status":
        payload = mgr.to_dict()
        if args.json:
            import json
            print(json.dumps(payload, indent=2, default=str))
        else:
            trusted = payload.get("trusted", [])
            current = payload.get("currentRepo", "")
            is_trusted = payload.get("currentRepoTrusted", False)
            print(f"Current repo: {current} ({'trusted' if is_trusted else 'not trusted'})")
            if trusted:
                for item in trusted:
                    print(f"  {item}")
            else:
                print("  No trusted repos.")
        return 0
    if cmd == "trust":
        canonical = mgr.trust(getattr(args, "path", None))
        if args.json:
            import json
            print(json.dumps({"trusted": True, "path": canonical}, indent=2, default=str))
        else:
            print(f"Trusted: {canonical}")
        return 0
    if cmd == "untrust":
        removed = mgr.untrust(getattr(args, "path", None))
        path = getattr(args, "path", None) or str(Path.cwd())
        if args.json:
            import json
            print(json.dumps({"untrusted": removed, "path": path}, indent=2, default=str))
        else:
            print(f"Untrusted: {path}" if removed else f"Not trusted: {path}")
        return 0
    raise SystemExit(f"Unknown trust subcommand: {cmd}")
