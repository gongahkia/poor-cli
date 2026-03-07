from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import run_vectorize
from .types import VectorizeConfig


def _build_manifest(out_dir: Path, project_root: Path) -> list[dict]:
    """Scan out/ for model.glb files and build a manifest for the landing page."""
    manifest = []
    if not out_dir.exists():
        return manifest
    for glb in sorted(out_dir.rglob("model.glb")):
        model_dir = glb.parent
        name = model_dir.name
        entry: dict = {
            "name": name,
            "glb": "/" + str(glb.relative_to(project_root)),
        }
        thumb = model_dir / "vector_clean.png"
        if thumb.exists():
            entry["thumb"] = "/" + str(thumb.relative_to(project_root))
        meta_file = model_dir / "vector.metadata.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                entry["walls"] = meta.get("walls", {}).get("total_segments")
                entry["columns"] = len(meta.get("columns", []))
                entry["openings"] = meta.get("openings", {}).get("total")
                m_per_px = meta.get("scale", {}).get("m_per_px")
                if m_per_px is not None:
                    entry["scale"] = f"{m_per_px:.4f}"
                entry["source"] = meta.get("source_image", "")
            except (json.JSONDecodeError, KeyError):
                pass
        manifest.append(entry)
    return manifest


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
    vec.add_argument("--no-clean", action="store_true", help="Skip floor plan pre-cleaning")

    build = subparsers.add_parser("build", help="Full pipeline: image -> vector + GLB mesh")
    build.add_argument("--image", required=True, type=Path, help="Path to floor plan image (PNG/JPEG)")
    build.add_argument("--out", required=True, type=Path, help="Output directory")
    build.add_argument("--debug-dir", type=Path, default=None, help="Optional debug artifact directory")
    build.add_argument("--wall-height", type=float, default=2.6, help="Wall extrusion height in meters (default: 2.6)")
    build.add_argument("--scale-override", type=float, default=None, help="Override m_per_px scale (bypass auto-detection)")
    build.add_argument("--no-clean", action="store_true", help="Skip floor plan pre-cleaning")

    clean = subparsers.add_parser("clean", help="Pre-clean a floor plan image (remove arcs, ledges, annotations)")
    clean.add_argument("--image", required=True, type=Path, help="Path to floor plan image")
    clean.add_argument("--out", required=True, type=Path, help="Output cleaned image path")

    subparsers.add_parser("mcp", help="Start MCP server for AI-assisted editing")

    view = subparsers.add_parser("view", help="Launch 3D viewer for a GLB file")
    view.add_argument("--glb", required=False, type=Path, default=None, help="Path to GLB file (opens editor directly)")
    view.add_argument("--port", type=int, default=8080, help="HTTP server port (default: 8080)")

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
                clean=not getattr(args, "no_clean", False),
            )
            metadata = run_vectorize(cfg)
            print(json.dumps(metadata, indent=2))
            if args.command == "build" and "output_glb" in metadata:
                print(metadata["output_glb"], file=sys.stderr)
            return 0
        if args.command == "clean":
            import cv2 as _cv2
            from .preprocess import clean_floor_plan
            if not args.image.exists():
                print(f"error: image does not exist: {args.image}", file=sys.stderr)
                return 2
            img_bgr = _cv2.imread(str(args.image))
            if img_bgr is None:
                raise ValueError(f"Could not read image: {args.image}")
            img_rgb = _cv2.cvtColor(img_bgr, _cv2.COLOR_BGR2RGB)
            cleaned = clean_floor_plan(img_rgb)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _cv2.imwrite(str(args.out), _cv2.cvtColor(cleaned, _cv2.COLOR_RGB2BGR))
            print(f"Cleaned image saved to {args.out}", file=sys.stderr)
            return 0
        if args.command == "mcp":
            from .mcp_server import run_server
            run_server()
            return 0
        if args.command == "view":
            import shutil
            import webbrowser
            project_root = Path(__file__).resolve().parent.parent.parent
            viewer_dir = project_root / "viewer"
            out_dir = project_root / "out"
            if not viewer_dir.exists():
                print(f"error: viewer directory not found: {viewer_dir}", file=sys.stderr)
                return 2
            port = args.port
            if args.glb:
                if not args.glb.exists():
                    print(f"error: GLB file does not exist: {args.glb}", file=sys.stderr)
                    return 2
                shutil.copy2(args.glb, viewer_dir / "model.glb")
            else:
                manifest = _build_manifest(out_dir, project_root)
                (viewer_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
            from .chat_server import run_server as run_chat_server
            open_url = f"http://localhost:{port}/viewer/editor.html"
            print(f"Starting server at http://localhost:{port}", file=sys.stderr)
            webbrowser.open(open_url)
            run_chat_server(str(project_root), port)
            return 0
        parser.error(f"Unsupported command: {args.command}")
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
