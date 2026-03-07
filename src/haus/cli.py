from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import run_vectorize
from .types import VectorizeConfig


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="haus",
        description="Vectorize a raster floor plan image to a clean wall-polygon PNG",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    vec = subparsers.add_parser("vectorize", help="Produce vector_clean.png from a raster floor plan")
    vec.add_argument("--image", required=True, type=Path, help="Path to floor plan image (PNG/JPEG)")
    vec.add_argument("--out", required=True, type=Path, help="Output directory")
    vec.add_argument("--debug-dir", type=Path, default=None, help="Optional debug artifact directory")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "vectorize":
            if not args.image.exists():
                print(f"error: image does not exist: {args.image}", file=sys.stderr)
                return 2
            cfg = VectorizeConfig(
                image_path=args.image,
                out_dir=args.out,
                debug_dir=args.debug_dir,
            )
            metadata = run_vectorize(cfg)
            print(json.dumps(metadata, indent=2))
            return 0
        parser.error(f"Unsupported command: {args.command}")
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
