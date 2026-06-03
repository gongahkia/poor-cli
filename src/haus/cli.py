from __future__ import annotations

import argparse
import os
import json
import shutil
import sys
from importlib import resources
from pathlib import Path
from typing import NamedTuple

from .logging_utils import configure_logging
from .pipeline import run_vectorize
from .types import VectorizeConfig

log = configure_logging("haus.cli")


class ViewEnvironment(NamedTuple):
    serve_root: Path
    viewer_dir: Path
    out_dir: Path
    source_checkout: bool


def _source_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _runtime_root() -> Path:
    configured = os.environ.get("HAUS_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".haus").resolve()


def _ensure_empty_layout(viewer_dir: Path) -> None:
    layout_path = viewer_dir / "mcp-layout.json"
    if not layout_path.exists():
        layout_path.write_text(json.dumps({"version": 1, "items": []}, indent=2), encoding="utf-8")


def _copy_resource_tree(resource_path: str, destination: Path, skip_names: set[str] | None = None) -> None:
    packaged_resource = resources.files("haus").joinpath(resource_path)
    with resources.as_file(packaged_resource) as packaged_path:
        packaged = Path(packaged_path)
        if not packaged.exists():
            raise FileNotFoundError(f"Packaged resource was not found: {resource_path}")

        destination.mkdir(parents=True, exist_ok=True)
        for child in packaged.iterdir():
            if skip_names and child.name in skip_names:
                continue
            dest = destination / child.name
            if child.is_dir():
                shutil.copytree(child, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(child, dest)


def _copy_packaged_viewer(runtime_viewer: Path) -> None:
    _copy_resource_tree("viewer", runtime_viewer, skip_names={"mcp-layout.json"})


def _copy_packaged_bto_library(runtime_root: Path) -> None:
    _copy_resource_tree("corpus/library", runtime_root / "corpus" / "library")


def _resolve_view_environment() -> ViewEnvironment:
    """Resolve static files and writable state for `haus view`.

    Source checkouts serve the repository root so generated `out/` assets keep
    working. Installed packages copy bundled viewer assets into `~/.haus`, which
    gives the MCP/chat sync loop a writable `viewer/mcp-layout.json`.
    """
    source_root = _source_project_root()
    source_viewer = source_root / "viewer"
    if source_viewer.exists():
        _ensure_empty_layout(source_viewer)
        return ViewEnvironment(
            serve_root=source_root,
            viewer_dir=source_viewer,
            out_dir=source_root / "out",
            source_checkout=True,
        )

    runtime_root = _runtime_root()
    runtime_viewer = runtime_root / "viewer"
    _copy_packaged_viewer(runtime_viewer)
    _copy_packaged_bto_library(runtime_root)
    _ensure_empty_layout(runtime_viewer)
    return ViewEnvironment(
        serve_root=runtime_root,
        viewer_dir=runtime_viewer,
        out_dir=runtime_root / "out",
        source_checkout=False,
    )


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
                log.warning("Skipping malformed metadata file: %s", meta_file)
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

    mcp = subparsers.add_parser("mcp", help="Start MCP server for AI-assisted editing")
    mcp.add_argument(
        "--layout",
        type=Path,
        default=None,
        help="Layout JSON path for standalone MCP mode (default: HAUS_LAYOUT_PATH or viewer/mcp-layout.json)",
    )

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
            if args.layout is not None:
                from . import mcp_server
                mcp_server.LAYOUT_PATH = args.layout
            from .mcp_server import run_server
            run_server()
            return 0
        if args.command == "view":
            import webbrowser
            env = _resolve_view_environment()
            project_root = env.serve_root
            viewer_dir = env.viewer_dir
            out_dir = env.out_dir
            port = args.port
            if args.glb:
                if not args.glb.exists():
                    print(f"error: GLB file does not exist: {args.glb}", file=sys.stderr)
                    return 2
                shutil.copy2(args.glb, viewer_dir / "model.glb")
            else:
                manifest = _build_manifest(out_dir, project_root)
                (viewer_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
            from . import mcp_server
            layout_path = viewer_dir / "mcp-layout.json"
            mcp_server.LAYOUT_PATH = layout_path
            from .chat_server import run_server as run_chat_server
            open_url = f"http://localhost:{port}/viewer/editor.html"
            print(f"Starting server at http://localhost:{port}", file=sys.stderr)
            webbrowser.open(open_url)
            run_chat_server(str(project_root), port, layout_path=str(layout_path))
            return 0
        parser.error(f"Unsupported command: {args.command}")
    except Exception as e:
        log.exception("CLI command failed")
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
