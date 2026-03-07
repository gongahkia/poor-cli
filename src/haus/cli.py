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

    build = subparsers.add_parser("build", help="Full pipeline: image -> vector + GLB mesh")
    build.add_argument("--image", required=True, type=Path, help="Path to floor plan image (PNG/JPEG)")
    build.add_argument("--out", required=True, type=Path, help="Output directory")
    build.add_argument("--debug-dir", type=Path, default=None, help="Optional debug artifact directory")
    build.add_argument("--wall-height", type=float, default=2.6, help="Wall extrusion height in meters (default: 2.6)")
    build.add_argument("--scale-override", type=float, default=None, help="Override m_per_px scale (bypass auto-detection)")

    view = subparsers.add_parser("view", help="Launch 3D viewer for a GLB file")
    view.add_argument("--glb", required=True, type=Path, help="Path to GLB file")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command in ("vectorize", "build"):
            if not args.image.exists():
                print(f"error: image does not exist: {args.image}", file=sys.stderr)
                return 2
            cfg = VectorizeConfig(
                image_path=args.image,
                out_dir=args.out,
                debug_dir=args.debug_dir,
                wall_height=getattr(args, "wall_height", 2.6),
                scale_override=getattr(args, "scale_override", None),
            )
            metadata = run_vectorize(cfg)
            print(json.dumps(metadata, indent=2))
            if args.command == "build" and "output_glb" in metadata:
                print(metadata["output_glb"], file=sys.stderr)
            return 0
        if args.command == "view":
            import shutil
            import subprocess
            import webbrowser
            viewer_dir = Path(__file__).resolve().parent.parent.parent / "viewer"
            if not viewer_dir.exists():
                print(f"error: viewer directory not found: {viewer_dir}", file=sys.stderr)
                return 2
            if not args.glb.exists():
                print(f"error: GLB file does not exist: {args.glb}", file=sys.stderr)
                return 2
            shutil.copy2(args.glb, viewer_dir / "model.glb")
            print(f"Copied {args.glb} -> {viewer_dir / 'model.glb'}", file=sys.stderr)
            print("Starting server at http://localhost:8080", file=sys.stderr)
            webbrowser.open("http://localhost:8080")
            proc = subprocess.Popen(
                [sys.executable, "-m", "http.server", "8080"],
                cwd=str(viewer_dir),
            )
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
            return 0
        parser.error(f"Unsupported command: {args.command}")
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
