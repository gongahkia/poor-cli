from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
from shapely.geometry import Polygon as ShapelyPolygon
from trimesh.visual import ColorVisuals

from .types import FloorPlanData

_M_PER_PX_FALLBACK = 0.02
_COLOR_BY_HDB = {
    "shelter": (120, 40, 40, 255),
    "structural": (80, 80, 80, 255),
    "partition": (140, 140, 160, 255),
    "ferrolite": (180, 180, 180, 255),
}
_COLOR_BY_WALL_TYPE = {
    "structural": (80, 80, 80, 255),
    "partition": (140, 140, 160, 255),
}


def _paint_mesh(mesh: trimesh.Trimesh, color: tuple[int, int, int, int]) -> None:
    face_colors = np.tile(np.array(color, dtype=np.uint8), (len(mesh.faces), 1))
    mesh.visual = ColorVisuals(mesh=mesh, face_colors=face_colors)


def extrude_floor_plan(
    data: FloorPlanData,
    wall_height_m: float = 2.6,
    scale_override: float | None = None,
) -> trimesh.Scene:
    m_per_px = scale_override or data.m_per_px
    if m_per_px is None:
        warnings.warn(
            f"No scale available, using fallback {_M_PER_PX_FALLBACK} m/px",
            stacklevel=2,
        )
        m_per_px = _M_PER_PX_FALLBACK

    scene = trimesh.Scene()

    for i, w in enumerate(data.walls):
        pts_px = w.polygon_px
        pts_m = [(x * m_per_px, y * m_per_px) for x, y in pts_px] # XY in pixel space -> XZ in scene
        poly = ShapelyPolygon(pts_m)
        if not poly.is_valid or poly.area < 1e-8:
            continue
        mesh = trimesh.creation.extrude_polygon(poly, wall_height_m)
        # rotate so extrusion (Z) becomes Y-up: swap Y and Z
        verts = mesh.vertices.copy()
        new_verts = np.empty_like(verts)
        new_verts[:, 0] = verts[:, 0]  # X stays
        new_verts[:, 1] = verts[:, 2]  # Z -> Y (up)
        new_verts[:, 2] = verts[:, 1]  # Y -> Z (depth)
        mesh.vertices = new_verts
        color = (
            _COLOR_BY_HDB.get(w.hdb_type, (80, 80, 80, 255))
            if w.hdb_type is not None
            else _COLOR_BY_WALL_TYPE.get(w.wall_type, (80, 80, 80, 255))
        )
        _paint_mesh(mesh, color)
        scene.add_geometry(mesh, node_name=f"wall_{i}")

    for i, c in enumerate(data.columns):
        cw = c.w * m_per_px
        ch = c.h * m_per_px
        cx = (c.x + c.w / 2) * m_per_px
        cy = (c.y + c.h / 2) * m_per_px
        box = trimesh.creation.box(extents=[cw, wall_height_m, ch])
        box.apply_translation([cx, wall_height_m / 2, cy])
        _paint_mesh(box, (180, 60, 180, 255))
        scene.add_geometry(box, node_name=f"column_{i}")

    for i, o in enumerate(data.openings):
        ow = o.w * m_per_px
        oh = o.h * m_per_px
        ox = (o.x + o.w / 2) * m_per_px
        oy = (o.y + o.h / 2) * m_per_px
        if o.label == "Door":
            height = 2.1
            bottom = 0.0
            color = (220, 60, 60, 200)
        else: # Window or Opening
            height = 1.2
            bottom = 0.9
            color = (60, 60, 220, 200)
        depth = 0.05
        box = trimesh.creation.box(extents=[ow, height, max(oh, depth)])
        box.apply_translation([ox, bottom + height / 2, oy])
        _paint_mesh(box, color)
        scene.add_geometry(box, node_name=f"opening_{i}")

    return scene


def export_glb(scene: trimesh.Scene, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    glb_data = cast(Any, scene.export(file_type="glb"))
    if not isinstance(glb_data, (bytes, bytearray, memoryview)):
        raise TypeError(f"Expected GLB export bytes, got {type(glb_data).__name__}")
    out_path.write_bytes(glb_data)
