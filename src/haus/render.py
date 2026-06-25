from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .types import FloorPlanData

# Color palette by HDB type (BGR for OpenCV), thickest first for draw order
_BGR_BY_HDB = {
    "shelter":    (40, 40, 120),    # dark red-brown
    "structural": (50, 50, 50),     # dark grey
    "partition":  (160, 130, 100),  # blue-grey
    "ferrolite":  (180, 170, 150),  # light grey
}

# Fallback colors when hdb_type is not set
_BGR_BY_WALL_TYPE = {
    "structural": (50, 50, 50),
    "partition":  (160, 130, 100),
}

_BGR_COLUMN = (90, 130, 26)      # dark teal
_BGR_WINDOW = (228, 158, 58)     # blue
_BGR_DOOR = (61, 76, 232)        # red

# Draw order: thickest first so thin walls render on top
_HDB_DRAW_ORDER = ["shelter", "structural", "partition", "ferrolite"]


def render_vector_clean(
    data: FloorPlanData,
    out_path: Path,
) -> None:
    """Render classified floor plan elements onto a white background.

    Wall segments are drawn as filled polygons at their detected pixel
    thickness, color-coded by HDB type (or wall_type fallback).
    """
    h, w = data.image_shape_hw
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)

    # Group walls by HDB type for draw-order control
    walls_by_hdb: dict[str, list] = {t: [] for t in _HDB_DRAW_ORDER}
    walls_no_hdb: list = []

    for seg in data.walls:
        if seg.hdb_type in walls_by_hdb:
            walls_by_hdb[seg.hdb_type].append(seg)
        else:
            walls_no_hdb.append(seg)

    # Draw in order: thickest first
    for hdb_type in _HDB_DRAW_ORDER:
        color = _BGR_BY_HDB[hdb_type]
        for seg in walls_by_hdb[hdb_type]:
            pts = np.array(seg.polygon_px, dtype=np.int32)
            cv2.fillPoly(canvas, [pts], color)

    # Fallback for walls without HDB classification (structural first)
    for wt in ("structural", "partition"):
        color = _BGR_BY_WALL_TYPE.get(wt, (100, 100, 100))
        for seg in walls_no_hdb:
            if seg.wall_type == wt:
                pts = np.array(seg.polygon_px, dtype=np.int32)
                cv2.fillPoly(canvas, [pts], color)

    # Draw columns
    for col in data.columns:
        cv2.rectangle(canvas, (col.x, col.y), (col.x + col.w, col.y + col.h),
                      _BGR_COLUMN, -1)

    # Draw openings
    if data.openings:
        overlay = canvas.copy()
        for op in data.openings:
            color = _BGR_WINDOW if op.label == "Window" else _BGR_DOOR
            cv2.rectangle(overlay, (op.x, op.y), (op.x + op.w, op.y + op.h), color, -1)
        cv2.addWeighted(overlay, 0.8, canvas, 0.2, 0, canvas)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), canvas)
