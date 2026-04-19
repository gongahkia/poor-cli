#!/usr/bin/env python3
"""Build the committed static server RPC/attr registry index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poor_cli.server.registry import write_static_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/build_server_registry_index.py")
    parser.add_argument("--output", default="", help="optional output path")
    args = parser.parse_args()

    output = str(args.output or "").strip()
    out_path = write_static_index(Path(output).expanduser().resolve() if output else None)
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "path": str(out_path),
                "version": int(payload.get("version", 0) or 0),
                "rpc_method_count": len(payload.get("rpcIndex", {})),
                "attr_count": len(payload.get("attrIndex", {})),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
