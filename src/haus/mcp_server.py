"""MCP server for haus floor plan editor.

Exposes tools for AI assistants to manipulate and analyze floor plan layouts.
Reads/writes a JSON layout file that the browser editor can import.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from mcp.server import FastMCP

from .logging_utils import configure_logging

LAYOUT_PATH = Path("viewer/mcp-layout.json")

FURNITURE_CATALOG = {
    "bed_single": {"w": 0.9, "h": 0.5, "d": 1.9, "color": 0x88BBEE},
    "bed_queen": {"w": 1.5, "h": 0.55, "d": 2.0, "color": 0x77AADD},
    "bed_king": {"w": 1.8, "h": 0.55, "d": 2.0, "color": 0x6699CC},
    "wardrobe": {"w": 1.8, "h": 2.0, "d": 0.6, "color": 0x4A3728},
    "wardrobe_s": {"w": 0.9, "h": 2.0, "d": 0.6, "color": 0x5A4738},
    "bedside": {"w": 0.5, "h": 0.5, "d": 0.4, "color": 0x8B7355},
    "dresser": {"w": 1.2, "h": 0.8, "d": 0.5, "color": 0x7A6245},
    "sofa_2": {"w": 1.5, "h": 0.8, "d": 0.8, "color": 0x555555},
    "sofa_3": {"w": 2.2, "h": 0.8, "d": 0.9, "color": 0x4A4A4A},
    "sofa_l": {"w": 2.2, "h": 0.8, "d": 1.6, "color": 0x505050},
    "coffee": {"w": 1.0, "h": 0.4, "d": 0.5, "color": 0x6B4226},
    "tv_console": {"w": 1.5, "h": 0.5, "d": 0.4, "color": 0x3A3A3A},
    "dining_4": {"w": 1.2, "h": 0.75, "d": 0.8, "color": 0x8B6914},
    "dining_6": {"w": 1.6, "h": 0.75, "d": 0.9, "color": 0x8B6914},
    "shoe_rack": {"w": 0.8, "h": 1.0, "d": 0.3, "color": 0x5C4033},
    "fridge": {"w": 0.7, "h": 1.7, "d": 0.7, "color": 0xCCCCCC},
    "washer": {"w": 0.6, "h": 0.85, "d": 0.6, "color": 0xDDDDDD},
    "kitchen_counter": {"w": 1.2, "h": 0.9, "d": 0.6, "color": 0x888888},
    "sink": {"w": 0.8, "h": 0.85, "d": 0.6, "color": 0x999999},
    "toilet": {"w": 0.4, "h": 0.4, "d": 0.7, "color": 0xEEEEEE},
    "shower": {"w": 0.9, "h": 2.0, "d": 0.9, "color": 0xAADDEE},
    "desk": {"w": 1.2, "h": 0.75, "d": 0.6, "color": 0xD2B48C},
    "desk_l": {"w": 1.6, "h": 0.75, "d": 1.2, "color": 0xC4A882},
    "bookshelf": {"w": 0.8, "h": 1.8, "d": 0.3, "color": 0x5A4020},
    "chair": {"w": 0.5, "h": 0.45, "d": 0.5, "color": 0x333333},
}

mcp = FastMCP(
    "haus-editor",
    instructions=(
        "You are an AI assistant for the haus floor plan editor. "
        "Use the provided tools to add, move, remove, and query furniture "
        "and walls in the user's floor plan layout. Coordinates are in meters. "
        "X is left-right, Z is forward-back. Y is vertical (height)."
    ),
)

log = configure_logging("haus.mcp")

_SIMULATION_CACHE: list[dict[str, Any]] = []


def _empty_layout() -> dict[str, Any]:
    return {"version": 1, "items": []}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_color(value: Any, default: int = 0x888888) -> int:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("#"):
            try:
                return int(text[1:], 16)
            except ValueError:
                return default
        try:
            return int(text)
        except ValueError:
            return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return default


def _normalize_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    pos_raw = raw.get("pos", [0.0, 0.0, 0.0])
    if not isinstance(pos_raw, (list, tuple)) or len(pos_raw) < 3:
        pos = [0.0, 0.0, 0.0]
    else:
        pos = [
            _coerce_float(pos_raw[0], 0.0),
            _coerce_float(pos_raw[1], 0.0),
            _coerce_float(pos_raw[2], 0.0),
        ]

    geo_raw = raw.get("geo", [1.0, 1.0, 1.0])
    if not isinstance(geo_raw, (list, tuple)) or len(geo_raw) < 3:
        geo = [1.0, 1.0, 1.0]
    else:
        geo = [
            max(0.01, _coerce_float(geo_raw[0], 1.0)),
            max(0.01, _coerce_float(geo_raw[1], 1.0)),
            max(0.01, _coerce_float(geo_raw[2], 1.0)),
        ]

    item_type = str(raw.get("type", "object"))
    item: dict[str, Any] = {
        "type": item_type,
        "pos": pos,
        "rot": _coerce_float(raw.get("rot", 0.0), 0.0),
        "visible": bool(raw.get("visible", True)),
        "geo": geo,
        "color": _coerce_color(raw.get("color", 0x888888), 0x888888),
    }

    furniture_type = raw.get("furnitureType")
    if furniture_type is not None:
        item["furnitureType"] = str(furniture_type)

    if "name" in raw and raw.get("name"):
        item["name"] = str(raw["name"])
    if "room" in raw and raw.get("room"):
        item["room"] = str(raw["room"])

    return item


def _normalize_layout(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_layout()

    items_raw = raw.get("items", [])
    normalized_items: list[dict[str, Any]] = []

    if isinstance(items_raw, list):
        for entry in items_raw:
            item = _normalize_item(entry)
            if item is not None:
                normalized_items.append(item)

    layout = {"version": _coerce_int(raw.get("version", 1), 1), "items": normalized_items}
    if "_stamp" in raw:
        layout["_stamp"] = _coerce_int(raw.get("_stamp", 0), 0)

    return layout


def _load_layout() -> dict[str, Any]:
    if not LAYOUT_PATH.exists():
        return _empty_layout()

    try:
        raw_text = LAYOUT_PATH.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        backup = LAYOUT_PATH.with_suffix(f".corrupt-{int(time.time())}.json")
        try:
            LAYOUT_PATH.rename(backup)
            log.exception("Layout JSON was corrupt, moved to %s", backup)
        except OSError:
            log.exception("Layout JSON was corrupt and could not be backed up")
        return _empty_layout()
    except OSError:
        log.exception("Failed reading layout file")
        return _empty_layout()

    return _normalize_layout(raw)


def _save_layout(data: dict[str, Any]) -> str | None:
    normalized = _normalize_layout(data)
    LAYOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LAYOUT_PATH.with_suffix(".tmp")

    try:
        tmp.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        tmp.replace(LAYOUT_PATH)
    except OSError:
        log.exception("Failed writing layout file")
        return "Error: failed to persist layout to disk."

    return None


def _item_label(item: dict[str, Any]) -> str:
    return str(item.get("furnitureType") or item.get("type", "object"))


def _validate_index(data: dict[str, Any], index: int) -> str | None:
    items = data["items"]
    if index < 0 or index >= len(items):
        return f"Error: index {index} out of range (0-{len(items) - 1})."
    return None


def _item_extents(item: dict[str, Any]) -> tuple[float, float]:
    geo = item.get("geo", [1.0, 1.0, 1.0])
    rot = _coerce_float(item.get("rot", 0.0), 0.0)
    half_x = (abs(geo[0] * math.cos(rot)) + abs(geo[2] * math.sin(rot))) / 2
    half_z = (abs(geo[0] * math.sin(rot)) + abs(geo[2] * math.cos(rot))) / 2
    return half_x, half_z


def _item_rect(item: dict[str, Any], padding: float = 0.0) -> tuple[float, float, float, float]:
    p = item.get("pos", [0.0, 0.0, 0.0])
    half_x, half_z = _item_extents(item)
    return (
        p[0] - half_x - padding,
        p[0] + half_x + padding,
        p[2] - half_z - padding,
        p[2] + half_z + padding,
    )


def _distance_xz(a: dict[str, Any], b: dict[str, Any]) -> float:
    pa = a.get("pos", [0.0, 0.0, 0.0])
    pb = b.get("pos", [0.0, 0.0, 0.0])
    return math.sqrt((pa[0] - pb[0]) ** 2 + (pa[2] - pb[2]) ** 2)


def _rect_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[1] and a[1] > b[0] and a[2] < b[3] and a[3] > b[2]


def _point_in_rect(point: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    return rect[0] <= point[0] <= rect[1] and rect[2] <= point[1] <= rect[3]


def _item_polygon(item: dict[str, Any], padding: float = 0.0) -> list[tuple[float, float]]:
    pos = item.get("pos", [0.0, 0.0, 0.0])
    geo = item.get("geo", [1.0, 1.0, 1.0])
    rot = _coerce_float(item.get("rot", 0.0), 0.0)

    cx = _coerce_float(pos[0], 0.0)
    cz = _coerce_float(pos[2], 0.0)
    half_w = max(0.005, _coerce_float(geo[0], 1.0) / 2 + max(0.0, padding))
    half_d = max(0.005, _coerce_float(geo[2], 1.0) / 2 + max(0.0, padding))

    corners_local = [
        (-half_w, -half_d),
        (half_w, -half_d),
        (half_w, half_d),
        (-half_w, half_d),
    ]
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)

    corners_world: list[tuple[float, float]] = []
    for lx, lz in corners_local:
        wx = cx + lx * cos_r + lz * sin_r
        wz = cz - lx * sin_r + lz * cos_r
        corners_world.append((wx, wz))
    return corners_world


def _polygon_edges(polygon: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    if len(polygon) < 2:
        return []
    return [(polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))]


def _polygon_axes(polygon: list[tuple[float, float]]) -> list[tuple[float, float]]:
    axes: list[tuple[float, float]] = []
    for a, b in _polygon_edges(polygon):
        edge_x = b[0] - a[0]
        edge_z = b[1] - a[1]
        axis = (-edge_z, edge_x)
        length = math.hypot(axis[0], axis[1])
        if length > 1e-9:
            axes.append((axis[0] / length, axis[1] / length))
    return axes


def _project_polygon(
    polygon: list[tuple[float, float]],
    axis: tuple[float, float],
) -> tuple[float, float]:
    dots = [point[0] * axis[0] + point[1] * axis[1] for point in polygon]
    return min(dots), max(dots)


def _polygons_intersect(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    if not a or not b:
        return False

    for axis in _polygon_axes(a) + _polygon_axes(b):
        a0, a1 = _project_polygon(a, axis)
        b0, b1 = _project_polygon(b, axis)
        if a1 < b0 or b1 < a0:
            return False
    return True


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> int:
    val = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(val) <= 1e-9:
        return 0
    return 1 if val > 0 else -1


def _on_segment(a: tuple[float, float], p: tuple[float, float], b: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
        and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9
    )


def _segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)

    if o1 != o2 and o3 != o4:
        return True

    if o1 == 0 and _on_segment(a1, b1, a2):
        return True
    if o2 == 0 and _on_segment(a1, b2, a2):
        return True
    if o3 == 0 and _on_segment(b1, a1, b2):
        return True
    if o4 == 0 and _on_segment(b1, a2, b2):
        return True
    return False


def _segment_intersects_rect(
    start: tuple[float, float],
    end: tuple[float, float],
    rect: tuple[float, float, float, float],
) -> bool:
    if _point_in_rect(start, rect) or _point_in_rect(end, rect):
        return True

    x0, x1, z0, z1 = rect
    edges = [
        ((x0, z0), (x1, z0)),
        ((x1, z0), (x1, z1)),
        ((x1, z1), (x0, z1)),
        ((x0, z1), (x0, z0)),
    ]

    for edge_start, edge_end in edges:
        if _segments_intersect(start, end, edge_start, edge_end):
            return True
    return False


def _distance_point_to_segment(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    ab_x = b[0] - a[0]
    ab_z = b[1] - a[1]
    ab_len_sq = ab_x * ab_x + ab_z * ab_z
    if ab_len_sq <= 1e-12:
        return math.hypot(point[0] - a[0], point[1] - a[1])

    ap_x = point[0] - a[0]
    ap_z = point[1] - a[1]
    t = max(0.0, min(1.0, (ap_x * ab_x + ap_z * ab_z) / ab_len_sq))
    proj_x = a[0] + t * ab_x
    proj_z = a[1] + t * ab_z
    return math.hypot(point[0] - proj_x, point[1] - proj_z)


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False

    for a, b in _polygon_edges(polygon):
        if _distance_point_to_segment(point, a, b) <= 1e-9:
            return True

    inside = False
    px, pz = point
    for i, (x1, z1) in enumerate(polygon):
        x2, z2 = polygon[(i + 1) % len(polygon)]
        crosses = (z1 > pz) != (z2 > pz)
        if not crosses:
            continue
        at_x = (x2 - x1) * (pz - z1) / max(z2 - z1, 1e-12) + x1
        if px < at_x:
            inside = not inside
    return inside


def _segment_intersects_polygon(
    start: tuple[float, float],
    end: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> bool:
    if _point_in_polygon(start, polygon) or _point_in_polygon(end, polygon):
        return True
    return any(_segments_intersect(start, end, edge_start, edge_end) for edge_start, edge_end in _polygon_edges(polygon))


def _polygon_distance(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    if _polygons_intersect(a, b):
        return 0.0

    min_dist = float("inf")
    for point in a:
        for edge_start, edge_end in _polygon_edges(b):
            min_dist = min(min_dist, _distance_point_to_segment(point, edge_start, edge_end))
    for point in b:
        for edge_start, edge_end in _polygon_edges(a):
            min_dist = min(min_dist, _distance_point_to_segment(point, edge_start, edge_end))
    return min_dist


def _segment_progress(
    start: tuple[float, float],
    end: tuple[float, float],
    point: tuple[float, float],
) -> float:
    sx, sz = start
    ex, ez = end
    seg_x = ex - sx
    seg_z = ez - sz
    seg_len_sq = seg_x * seg_x + seg_z * seg_z
    if seg_len_sq <= 1e-12:
        return 0.0
    px = point[0] - sx
    pz = point[1] - sz
    return max(0.0, min(1.0, (px * seg_x + pz * seg_z) / seg_len_sq))


def _collect_sightline_blockers(
    data: dict[str, Any],
    index_from: int,
    index_to: int,
    safety_margin: float,
    include_hidden: bool,
) -> list[dict[str, Any]]:
    items = data["items"]
    src = items[index_from]
    dst = items[index_to]

    start = (src["pos"][0], src["pos"][2])
    end = (dst["pos"][0], dst["pos"][2])
    line_len = math.hypot(end[0] - start[0], end[1] - start[1])

    blockers: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if i in (index_from, index_to):
            continue
        if not include_hidden and not item.get("visible", True):
            continue
        polygon = _item_polygon(item, padding=max(0.0, safety_margin))
        if _segment_intersects_polygon(start, end, polygon):
            center = (item["pos"][0], item["pos"][2])
            line_t = _segment_progress(start, end, center)
            dist = line_t * line_len
            blockers.append(
                {
                    "index": i,
                    "type": _item_label(item),
                    "distance": dist,
                    "line_t": line_t,
                }
            )

    blockers.sort(key=lambda b: b["distance"])
    return blockers


def _layout_bounds(data: dict[str, Any]) -> tuple[float, float, float, float]:
    if not data["items"]:
        return (-4.0, -4.0, 4.0, 4.0)

    x_mins, z_mins, x_maxs, z_maxs = [], [], [], []
    for item in data["items"]:
        rect = _item_rect(item)
        x_mins.append(rect[0])
        z_mins.append(rect[2])
        x_maxs.append(rect[1])
        z_maxs.append(rect[3])

    return (min(x_mins), min(z_mins), max(x_maxs), max(z_maxs))


def _room_extents(data: dict[str, Any], room: str) -> tuple[float, float, float, float] | None:
    x_min = float("inf")
    z_min = float("inf")
    x_max = float("-inf")
    z_max = float("-inf")
    found = False

    for item in data["items"]:
        if item.get("room") != room:
            continue
        found = True
        rect = _item_rect(item)
        x_min = min(x_min, rect[0])
        x_max = max(x_max, rect[1])
        z_min = min(z_min, rect[2])
        z_max = max(z_max, rect[3])

    return (x_min, z_min, x_max, z_max) if found else None


def _build_furniture_item(
    furniture_type: str,
    x: float,
    z: float,
    rotation_deg: float,
) -> dict[str, Any]:
    spec = FURNITURE_CATALOG[furniture_type]
    return {
        "type": "furniture",
        "furnitureType": furniture_type,
        "pos": [x, spec["h"] / 2, z],
        "rot": math.radians(rotation_deg),
        "visible": True,
        "geo": [spec["w"], spec["h"], spec["d"]],
        "color": spec["color"],
    }


def _resolve_search_bounds(
    data: dict[str, Any],
    room_name: str,
    near_index: int | None,
    max_distance: float,
) -> tuple[float, float, float, float]:
    if room_name:
        ext = _room_extents(data, room_name)
        if ext is not None:
            return (ext[0] - 0.2, ext[1] - 0.2, ext[2] + 0.2, ext[3] + 0.2)

    if near_index is not None and 0 <= near_index < len(data["items"]):
        near = data["items"][near_index]["pos"]
        pad = max(1.0, max_distance)
        return (near[0] - pad, near[2] - pad, near[0] + pad, near[2] + pad)

    bounds = _layout_bounds(data)
    return (bounds[0] - 2.0, bounds[1] - 2.0, bounds[2] + 2.0, bounds[3] + 2.0)


def _iter_grid_points(
    bounds: tuple[float, float, float, float],
    grid_size: float,
) -> list[tuple[float, float]]:
    x0, z0, x1, z1 = bounds
    gs = max(0.1, grid_size)

    x = x0
    points: list[tuple[float, float]] = []
    while x <= x1 + 1e-6:
        z = z0
        while z <= z1 + 1e-6:
            points.append((round(x, 4), round(z, 4)))
            z += gs
        x += gs
    return points


def _best_candidate_rot_deg(
    x: float,
    z: float,
    face_item: dict[str, Any] | None,
) -> float:
    if face_item is None:
        return 0.0
    dx = face_item["pos"][0] - x
    dz = face_item["pos"][2] - z
    if abs(dx) < 1e-6 and abs(dz) < 1e-6:
        return 0.0
    return math.degrees(-math.atan2(dz, dx))


def _simulate_candidates(
    *,
    data: dict[str, Any],
    furniture_type: str,
    room_name: str,
    near_index: int | None,
    face_index: int | None,
    min_distance: float,
    max_distance: float,
    require_clear_sightline: bool,
    max_candidates: int,
    grid_size: float,
) -> tuple[list[dict[str, Any]], str | None]:
    if furniture_type not in FURNITURE_CATALOG:
        return [], f"Error: unknown type '{furniture_type}'. Use list_furniture_catalog()."

    if near_index is not None and (msg := _validate_index(data, near_index)):
        return [], msg
    if face_index is not None and (msg := _validate_index(data, face_index)):
        return [], msg

    bounds = _resolve_search_bounds(data, room_name, near_index, max_distance)
    points = _iter_grid_points(bounds, grid_size)
    face_item = data["items"][face_index] if face_index is not None else None
    near_item = data["items"][near_index] if near_index is not None else None

    candidates: list[dict[str, Any]] = []

    for x, z in points:
        rot_deg = _best_candidate_rot_deg(x, z, face_item)
        candidate = _build_furniture_item(furniture_type, x, z, rot_deg)
        cand_polygon = _item_polygon(candidate, padding=0.02)

        overlap = False
        nearest_clearance = float("inf")
        for idx, other in enumerate(data["items"]):
            if not other.get("visible", True):
                continue
            other_polygon = _item_polygon(other, padding=0.02)
            if _polygons_intersect(cand_polygon, other_polygon):
                overlap = True
                break
            if idx != near_index:
                nearest_clearance = min(nearest_clearance, _polygon_distance(cand_polygon, other_polygon))

        if overlap:
            continue

        if near_item is not None:
            near_dist = _distance_xz(candidate, near_item)
            if near_dist < min_distance or near_dist > max_distance:
                continue
        else:
            near_dist = 0.0

        blockers: list[dict[str, Any]] = []
        if face_index is not None:
            tmp_layout = {"version": 1, "items": data["items"] + [candidate]}
            from_idx = len(tmp_layout["items"]) - 1
            blockers = _collect_sightline_blockers(
                tmp_layout,
                from_idx,
                face_index,
                safety_margin=0.02,
                include_hidden=False,
            )
            blockers = [b for b in blockers if b["index"] != face_index]
            if require_clear_sightline and blockers:
                continue

        accessibility_clearance = (
            nearest_clearance if nearest_clearance < float("inf") else None
        )
        if accessibility_clearance is not None and accessibility_clearance < 0.35:
            continue

        score = 0.0
        if near_item is not None:
            target = (min_distance + max_distance) / 2
            score += max(0.0, 1.0 - abs(near_dist - target) / max(target, 0.1)) * 0.45
        if face_index is not None:
            score += 0.35 if not blockers else max(0.0, 0.22 - 0.03 * len(blockers))

        if accessibility_clearance is not None:
            accessibility_score = min(accessibility_clearance, 1.2) / 1.2
            score += accessibility_score * 0.20
        else:
            accessibility_score = None

        candidates.append(
            {
                "x": round(x, 3),
                "z": round(z, 3),
                "rotation_deg": round(rot_deg, 1),
                "score": round(score, 4),
                "distance_to_reference_m": round(near_dist, 3) if near_item is not None else None,
                "blockers": blockers,
                "nearest_clearance_m": (
                    round(accessibility_clearance, 3) if accessibility_clearance is not None else None
                ),
                "accessibility_clearance_m": (
                    round(accessibility_clearance, 3) if accessibility_clearance is not None else None
                ),
                "accessibility_score": (
                    round(accessibility_score, 3) if accessibility_score is not None else None
                ),
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[: max(1, max_candidates)], None


@mcp.tool()
def list_furniture_catalog() -> str:
    """List all available furniture types with their dimensions."""
    lines = []
    for name, spec in FURNITURE_CATALOG.items():
        lines.append(f"  {name}: {spec['w']}m x {spec['d']}m (height {spec['h']}m)")
    return "Available furniture types:\n" + "\n".join(lines)


@mcp.tool()
def list_objects() -> str:
    """List all objects currently in the layout with their index, type, and position."""
    data = _load_layout()
    if not data["items"]:
        return "Layout is empty. No objects placed yet."

    lines = []
    for i, item in enumerate(data["items"]):
        p = item["pos"]
        rot = math.degrees(item.get("rot", 0.0))
        vis = "visible" if item.get("visible", True) else "hidden"
        lines.append(f"  [{i}] {_item_label(item)} at ({p[0]:.2f}, {p[2]:.2f}) rot={rot:.0f}° {vis}")
    return f"Layout has {len(data['items'])} objects:\n" + "\n".join(lines)


@mcp.tool()
def add_furniture(
    furniture_type: str,
    x: float = 0.0,
    z: float = 0.0,
    rotation_deg: float = 0.0,
) -> str:
    """Add a furniture item to the layout."""
    if furniture_type not in FURNITURE_CATALOG:
        return f"Error: unknown type '{furniture_type}'. Use list_furniture_catalog() to see options."

    data = _load_layout()
    item = _build_furniture_item(furniture_type, x, z, rotation_deg)
    data["items"].append(item)

    err = _save_layout(data)
    if err:
        return err

    idx = len(data["items"]) - 1
    log.info("Added %s as item [%s]", furniture_type, idx)
    return f"Added {furniture_type} at ({x}, {z}) as item [{idx}]."


@mcp.tool()
def add_wall(
    x1: float,
    z1: float,
    x2: float,
    z2: float,
    height: float = 2.6,
    thickness: float = 0.15,
) -> str:
    """Add a wall segment between two points."""
    dx, dz = x2 - x1, z2 - z1
    length = math.sqrt(dx * dx + dz * dz)
    if length < 0.01:
        return "Error: wall too short (start and end points are the same)."

    cx, cz = (x1 + x2) / 2, (z1 + z2) / 2
    angle = -math.atan2(dz, dx)

    data = _load_layout()
    item = {
        "type": "wall",
        "pos": [cx, max(0.05, height) / 2, cz],
        "rot": angle,
        "visible": True,
        "geo": [max(0.05, length), max(0.05, height), max(0.02, thickness)],
        "color": 0x666666,
    }
    data["items"].append(item)

    err = _save_layout(data)
    if err:
        return err

    idx = len(data["items"]) - 1
    log.info("Added wall as item [%s]", idx)
    return f"Added wall ({x1},{z1})->({x2},{z2}), length={length:.2f}m as item [{idx}]."


@mcp.tool()
def move_object(index: int, x: float, z: float) -> str:
    """Move an object to a new XZ position."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    item = data["items"][index]
    item["pos"][0] = x
    item["pos"][2] = z

    err = _save_layout(data)
    if err:
        return err

    return f"Moved [{index}] {_item_label(item)} to ({x}, {z})."


@mcp.tool()
def rotate_object(index: int, rotation_deg: float) -> str:
    """Set an object's rotation in degrees."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    data["items"][index]["rot"] = math.radians(rotation_deg)
    err = _save_layout(data)
    if err:
        return err

    return f"Rotated [{index}] to {rotation_deg}°."


@mcp.tool()
def remove_object(index: int) -> str:
    """Remove an object from the layout by index."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    removed = data["items"].pop(index)
    err = _save_layout(data)
    if err:
        return err

    return f"Removed [{index}] {_item_label(removed)}. Remaining items re-indexed."


@mcp.tool()
def remove_objects_by_type(object_type: str) -> str:
    """Remove all objects of a given type."""
    data = _load_layout()
    before = len(data["items"])
    data["items"] = [
        item
        for item in data["items"]
        if not (item.get("type") == object_type or item.get("furnitureType") == object_type)
    ]
    removed = before - len(data["items"])

    err = _save_layout(data)
    if err:
        return err

    return f"Removed {removed} {object_type} item(s). {len(data['items'])} remaining."


@mcp.tool()
def clear_layout() -> str:
    """Remove all objects from the layout."""
    err = _save_layout(_empty_layout())
    if err:
        return err

    return "Layout cleared."


@mcp.tool()
def get_layout_json() -> str:
    """Get the full layout as JSON (for importing into the editor)."""
    return json.dumps(_load_layout(), indent=2)


@mcp.tool()
def get_object_details(index: int) -> str:
    """Get full details for one object."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    item = data["items"][index]
    p = item["pos"]
    rot = math.degrees(item.get("rot", 0.0))
    geo = item.get("geo", [1.0, 1.0, 1.0])
    color = f"#{_coerce_color(item.get('color', 0), 0):06x}"
    vis = item.get("visible", True)

    return (
        f"[{index}] {_item_label(item)}\n"
        f"  position: ({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f})\n"
        f"  rotation: {rot:.1f} deg\n"
        f"  dimensions: w={geo[0]:.2f} h={geo[1]:.2f} d={geo[2]:.2f}\n"
        f"  color: {color}\n"
        f"  visible: {vis}"
    )


@mcp.tool()
def get_layout_summary() -> str:
    """Get a layout summary: counts, furniture breakdown, hidden count, bounding box."""
    data = _load_layout()
    items = data["items"]
    if not items:
        return "Layout is empty."

    type_counts: dict[str, int] = {}
    furniture_counts: dict[str, int] = {}
    hidden = 0

    x_vals, z_vals = [], []
    for item in items:
        item_type = str(item.get("type", "object"))
        type_counts[item_type] = type_counts.get(item_type, 0) + 1

        if item_type == "furniture":
            ft = str(item.get("furnitureType", "unknown"))
            furniture_counts[ft] = furniture_counts.get(ft, 0) + 1

        if not item.get("visible", True):
            hidden += 1

        x, _, z = item["pos"]
        x_vals.append(x)
        z_vals.append(z)

    lines = [f"Total objects: {len(items)}"]
    for item_type, count in sorted(type_counts.items()):
        lines.append(f"  {item_type}: {count}")
    if furniture_counts:
        lines.append("Furniture breakdown:")
        for ft, count in sorted(furniture_counts.items()):
            lines.append(f"  {ft}: {count}")
    if hidden:
        lines.append(f"Hidden: {hidden}")

    lines.append(
        f"XZ bounding box: X=[{min(x_vals):.2f}, {max(x_vals):.2f}] "
        f"Z=[{min(z_vals):.2f}, {max(z_vals):.2f}]"
    )
    return "\n".join(lines)


@mcp.tool()
def resize_object(
    index: int,
    width: float | None = None,
    height: float | None = None,
    depth: float | None = None,
) -> str:
    """Resize an object. Only provided dimensions are changed. Minimum 0.05m."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    item = data["items"][index]
    geo = list(item.get("geo", [1.0, 1.0, 1.0]))
    if width is not None:
        geo[0] = max(0.05, width)
    if height is not None:
        geo[1] = max(0.05, height)
    if depth is not None:
        geo[2] = max(0.05, depth)

    item["geo"] = geo
    item["pos"][1] = geo[1] / 2

    err = _save_layout(data)
    if err:
        return err

    return f"Resized [{index}] to w={geo[0]:.2f} h={geo[1]:.2f} d={geo[2]:.2f}."


@mcp.tool()
def set_color(index: int, color: str) -> str:
    """Set an object's color via hex string (e.g. '#ff0000')."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    try:
        parsed = int(color.lstrip("#"), 16)
    except ValueError:
        return f"Error: invalid color '{color}'. Use hex like '#ff0000'."

    data["items"][index]["color"] = parsed
    err = _save_layout(data)
    if err:
        return err

    return f"Set [{index}] color to {color}."


@mcp.tool()
def set_visibility(index: int, visible: bool) -> str:
    """Show or hide an object."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    data["items"][index]["visible"] = visible
    err = _save_layout(data)
    if err:
        return err

    state = "visible" if visible else "hidden"
    return f"Set [{index}] to {state}."


@mcp.tool()
def duplicate_object(index: int, x: float, z: float) -> str:
    """Duplicate an object to a new position, preserving all properties."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    original = json.loads(json.dumps(data["items"][index]))
    original["pos"][0] = x
    original["pos"][2] = z
    data["items"].append(original)

    err = _save_layout(data)
    if err:
        return err

    new_idx = len(data["items"]) - 1
    return f"Duplicated [{index}] {_item_label(original)} to ({x}, {z}) as [{new_idx}]."


@mcp.tool()
def batch_move(indices: list[int], dx: float, dz: float) -> str:
    """Move multiple objects by a relative offset."""
    data = _load_layout()
    for idx in indices:
        if msg := _validate_index(data, idx):
            return f"{msg} No objects moved."

    for idx in indices:
        data["items"][idx]["pos"][0] += dx
        data["items"][idx]["pos"][2] += dz

    err = _save_layout(data)
    if err:
        return err

    return f"Moved {len(indices)} objects by dx={dx}, dz={dz}."


@mcp.tool()
def measure_distance(index1: int, index2: int) -> str:
    """XZ Euclidean distance between two object centers."""
    data = _load_layout()
    if msg := _validate_index(data, index1):
        return msg
    if msg := _validate_index(data, index2):
        return msg

    p1, p2 = data["items"][index1], data["items"][index2]
    dist = _distance_xz(p1, p2)
    return f"Distance between [{index1}] and [{index2}]: {dist:.3f}m"


@mcp.tool()
def find_objects_in_area(x_min: float, z_min: float, x_max: float, z_max: float) -> str:
    """Find all objects whose center falls within an XZ bounding box."""
    data = _load_layout()
    found: list[str] = []

    for i, item in enumerate(data["items"]):
        x, _, z = item["pos"]
        if x_min <= x <= x_max and z_min <= z <= z_max:
            found.append(f"  [{i}] {_item_label(item)} at ({x:.2f}, {z:.2f})")

    if not found:
        return "No objects found in the specified area."
    return f"Found {len(found)} objects:\n" + "\n".join(found)


@mcp.tool()
def check_overlap(index1: int, index2: int) -> str:
    """AABB overlap check on XZ plane between two objects."""
    data = _load_layout()
    if msg := _validate_index(data, index1):
        return msg
    if msg := _validate_index(data, index2):
        return msg

    overlap = _rect_intersects(_item_rect(data["items"][index1]), _item_rect(data["items"][index2]))
    if overlap:
        return f"Objects [{index1}] and [{index2}] OVERLAP on XZ plane."
    return f"Objects [{index1}] and [{index2}] do NOT overlap."


@mcp.tool()
def find_nearest(index: int, count: int = 3) -> str:
    """Find N nearest objects by XZ distance, sorted."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    base = data["items"][index]
    distances: list[tuple[float, int]] = []
    for i, item in enumerate(data["items"]):
        if i == index:
            continue
        distances.append((_distance_xz(base, item), i))

    distances.sort(key=lambda d: d[0])
    results = distances[: max(0, count)]

    if not results:
        return "No other objects in layout."

    lines = []
    for dist, idx in results:
        lines.append(f"  [{idx}] {_item_label(data['items'][idx])} — {dist:.3f}m")
    return f"Nearest {len(results)} objects to [{index}]:\n" + "\n".join(lines)


@mcp.tool()
def align_objects(indices: list[int], axis: str, reference: str = "center") -> str:
    """Align objects along an axis ('x' or 'z')."""
    if axis not in ("x", "z"):
        return "Error: axis must be 'x' or 'z'."
    if reference not in ("min", "max", "center"):
        return "Error: reference must be 'min', 'max', or 'center'."
    if not indices:
        return "Error: indices must not be empty."

    data = _load_layout()
    for idx in indices:
        if msg := _validate_index(data, idx):
            return f"{msg} No changes made."

    comp = 0 if axis == "x" else 2
    values = [data["items"][idx]["pos"][comp] for idx in indices]

    if reference == "min":
        target = min(values)
    elif reference == "max":
        target = max(values)
    else:
        target = sum(values) / len(values)

    for idx in indices:
        data["items"][idx]["pos"][comp] = target

    err = _save_layout(data)
    if err:
        return err

    return f"Aligned {len(indices)} objects on {axis}={target:.3f} (ref={reference})."


@mcp.tool()
def distribute_objects(indices: list[int], axis: str) -> str:
    """Evenly space objects along an axis. First/last stay as anchors."""
    if axis not in ("x", "z"):
        return "Error: axis must be 'x' or 'z'."
    if len(indices) < 3:
        return "Error: need at least 3 objects to distribute."

    data = _load_layout()
    for idx in indices:
        if msg := _validate_index(data, idx):
            return f"{msg} No changes made."

    comp = 0 if axis == "x" else 2
    ordered = sorted(indices, key=lambda idx: data["items"][idx]["pos"][comp])

    start = data["items"][ordered[0]]["pos"][comp]
    end = data["items"][ordered[-1]]["pos"][comp]
    step = (end - start) / (len(ordered) - 1)

    for i, idx in enumerate(ordered):
        data["items"][idx]["pos"][comp] = start + i * step

    err = _save_layout(data)
    if err:
        return err

    return f"Distributed {len(indices)} objects along {axis} from {start:.3f} to {end:.3f}."


@mcp.tool()
def snap_to_grid(indices: list[int], grid_size: float = 0.25) -> str:
    """Round object positions to nearest grid multiple."""
    if grid_size <= 0:
        return "Error: grid_size must be positive."

    data = _load_layout()
    for idx in indices:
        if msg := _validate_index(data, idx):
            return f"{msg} No changes made."

    for idx in indices:
        pos = data["items"][idx]["pos"]
        pos[0] = round(pos[0] / grid_size) * grid_size
        pos[2] = round(pos[2] / grid_size) * grid_size

    err = _save_layout(data)
    if err:
        return err

    return f"Snapped {len(indices)} objects to {grid_size}m grid."


@mcp.tool()
def rename_object(index: int, name: str) -> str:
    """Assign a human-readable label to an object. Empty string removes it."""
    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    if name:
        data["items"][index]["name"] = name
    else:
        data["items"][index].pop("name", None)

    err = _save_layout(data)
    if err:
        return err

    if name:
        return f"Renamed [{index}] to '{name}'."
    return f"Cleared name for [{index}]."


@mcp.tool()
def find_by_name(name: str) -> str:
    """Case-insensitive substring search on object names."""
    data = _load_layout()
    found: list[str] = []

    for i, item in enumerate(data["items"]):
        item_name = str(item.get("name", ""))
        if item_name and name.lower() in item_name.lower():
            p = item["pos"]
            found.append(f"  [{i}] \"{item_name}\" ({_item_label(item)}) at ({p[0]:.2f}, {p[2]:.2f})")

    if not found:
        return f"No objects found matching '{name}'."
    return f"Found {len(found)} matching objects:\n" + "\n".join(found)


@mcp.tool()
def tag_room(indices: list[int], room_name: str) -> str:
    """Assign a room label to objects."""
    data = _load_layout()
    for idx in indices:
        if msg := _validate_index(data, idx):
            return f"{msg} No changes made."

    for idx in indices:
        data["items"][idx]["room"] = room_name

    err = _save_layout(data)
    if err:
        return err

    return f"Tagged {len(indices)} objects as '{room_name}'."


@mcp.tool()
def list_rooms() -> str:
    """List all room labels with their object indices and bounding-box area."""
    data = _load_layout()
    rooms: dict[str, list[str]] = {}

    for i, item in enumerate(data["items"]):
        room = item.get("room")
        if room:
            rooms.setdefault(str(room), []).append(f"[{i}] {_item_label(item)}")

    if not rooms:
        return "No rooms defined. Use tag_room to assign rooms."

    lines = []
    for room_name, objs in sorted(rooms.items()):
        ext = _room_extents(data, room_name)
        area = 0.0
        if ext is not None:
            area = max(0.0, ext[2] - ext[0]) * max(0.0, ext[3] - ext[1])
        lines.append(f"  {room_name} ({area:.1f}m²): {', '.join(objs)}")

    return f"{len(rooms)} rooms:\n" + "\n".join(lines)


@mcp.tool()
def compute_room_area(room_name: str) -> str:
    """Compute the bounding-box area of a room from tagged objects."""
    data = _load_layout()
    ext = _room_extents(data, room_name)
    if ext is None:
        return f"Error: no objects tagged with room '{room_name}'."

    width = ext[2] - ext[0]
    depth = ext[3] - ext[1]
    area = width * depth
    return (
        f"Room '{room_name}' bounding box:\n"
        f"  X: {ext[0]:.2f} to {ext[2]:.2f} ({width:.2f}m)\n"
        f"  Z: {ext[1]:.2f} to {ext[3]:.2f} ({depth:.2f}m)\n"
        f"  Area: {area:.2f}m²"
    )


@mcp.tool()
def swap_furniture(index: int, new_type: str) -> str:
    """Replace furniture type while keeping position, rotation, visibility, name, and room."""
    if new_type not in FURNITURE_CATALOG:
        return f"Error: unknown type '{new_type}'. Use list_furniture_catalog()."

    data = _load_layout()
    if msg := _validate_index(data, index):
        return msg

    item = data["items"][index]
    spec = FURNITURE_CATALOG[new_type]
    old_type = _item_label(item)

    item["type"] = "furniture"
    item["furnitureType"] = new_type
    item["geo"] = [spec["w"], spec["h"], spec["d"]]
    item["color"] = spec["color"]
    item["pos"][1] = spec["h"] / 2

    err = _save_layout(data)
    if err:
        return err

    return f"Swapped [{index}] from {old_type} to {new_type}."


@mcp.tool()
def check_sightline(
    index_from: int,
    index_to: int,
    safety_margin: float = 0.05,
    include_hidden: bool = False,
) -> str:
    """Check if the line of sight between two objects is blocked by others."""
    data = _load_layout()
    if msg := _validate_index(data, index_from):
        return msg
    if msg := _validate_index(data, index_to):
        return msg

    blockers = _collect_sightline_blockers(
        data,
        index_from,
        index_to,
        safety_margin=max(0.0, safety_margin),
        include_hidden=include_hidden,
    )

    if not blockers:
        return f"Sightline [{index_from}] -> [{index_to}] is CLEAR."

    lines = [f"Sightline [{index_from}] -> [{index_to}] is BLOCKED by {len(blockers)} object(s):"]
    for blocker in blockers[:10]:
        lines.append(
            f"  [{blocker['index']}] {blocker['type']} at {blocker['distance']:.2f}m from source"
        )
    return "\n".join(lines)


@mcp.tool()
def suggest_furniture_placement(
    furniture_type: str,
    near_index: int | None = None,
    face_index: int | None = None,
    room_name: str = "",
    min_distance: float = 1.0,
    max_distance: float = 4.0,
    require_clear_sightline: bool = False,
    max_candidates: int = 5,
    grid_size: float = 0.25,
) -> str:
    """Suggest placement candidates by simulating layout constraints."""
    if min_distance < 0:
        return "Error: min_distance must be >= 0."
    if max_distance <= 0 or max_distance < min_distance:
        return "Error: max_distance must be >= min_distance and > 0."

    data = _load_layout()
    candidates, err = _simulate_candidates(
        data=data,
        furniture_type=furniture_type,
        room_name=room_name,
        near_index=near_index,
        face_index=face_index,
        min_distance=min_distance,
        max_distance=max_distance,
        require_clear_sightline=require_clear_sightline,
        max_candidates=max(1, max_candidates),
        grid_size=max(0.1, grid_size),
    )
    if err:
        return err
    if not candidates:
        return "No valid placements found for the requested constraints."

    lines = [f"Top {len(candidates)} placement candidate(s) for {furniture_type}:"]
    for i, cand in enumerate(candidates, start=1):
        sight = "clear" if not cand["blockers"] else f"blocked by {len(cand['blockers'])}"
        near_info = (
            f", dist={cand['distance_to_reference_m']:.2f}m"
            if cand["distance_to_reference_m"] is not None
            else ""
        )
        clearance = cand["nearest_clearance_m"]
        clear_text = f", nearest_clearance={clearance:.2f}m" if clearance is not None else ""
        accessibility = cand.get("accessibility_score")
        acc_text = f", accessibility={accessibility:.2f}" if accessibility is not None else ""
        lines.append(
            f"  {i}. x={cand['x']:.2f}, z={cand['z']:.2f}, rot={cand['rotation_deg']:.1f}°, "
            f"score={cand['score']:.3f}, sightline={sight}{near_info}{clear_text}{acc_text}"
        )
    return "\n".join(lines)


@mcp.tool()
def auto_place_furniture(
    furniture_type: str,
    near_index: int | None = None,
    face_index: int | None = None,
    room_name: str = "",
    min_distance: float = 1.0,
    max_distance: float = 4.0,
    require_clear_sightline: bool = False,
    candidate_rank: int = 1,
    grid_size: float = 0.25,
) -> str:
    """Auto-place furniture using the best simulated candidate."""
    data = _load_layout()
    candidates, err = _simulate_candidates(
        data=data,
        furniture_type=furniture_type,
        room_name=room_name,
        near_index=near_index,
        face_index=face_index,
        min_distance=min_distance,
        max_distance=max_distance,
        require_clear_sightline=require_clear_sightline,
        max_candidates=max(1, candidate_rank),
        grid_size=max(0.1, grid_size),
    )
    if err:
        return err
    if not candidates:
        return "No valid placements found for the requested constraints."

    idx = max(1, candidate_rank) - 1
    if idx >= len(candidates):
        return f"Error: candidate_rank {candidate_rank} exceeds {len(candidates)} available candidate(s)."

    chosen = candidates[idx]
    item = _build_furniture_item(
        furniture_type=furniture_type,
        x=chosen["x"],
        z=chosen["z"],
        rotation_deg=chosen["rotation_deg"],
    )
    data["items"].append(item)

    save_err = _save_layout(data)
    if save_err:
        return save_err

    new_index = len(data["items"]) - 1
    return (
        f"Placed {furniture_type} as [{new_index}] at ({chosen['x']:.2f}, {chosen['z']:.2f}), "
        f"rot={chosen['rotation_deg']:.1f}°, score={chosen['score']:.3f}."
    )


@mcp.tool()
def simulate_layout_options(requirement: str, room_name: str = "", max_options: int = 3) -> str:
    """Generate simulated multi-object layout options for vague natural-language intents."""
    req = requirement.lower().strip()
    data = _load_layout()

    if not req:
        return "Error: requirement must not be empty."

    tv_index: int | None = None
    for i, item in enumerate(data["items"]):
        t = _item_label(item).lower()
        n = str(item.get("name", "")).lower()
        if "tv" in t or "tv" in n:
            tv_index = i
            break

    sofa_type = "sofa_3"
    if "sofa_l" in req or "l-sofa" in req or "l sofa" in req:
        sofa_type = "sofa_l"
    elif "2-seat" in req or "2 seat" in req or "sofa_2" in req:
        sofa_type = "sofa_2"

    needs_sightline = "see" in req or "view" in req or "sight" in req
    if needs_sightline and tv_index is None:
        return "Error: could not infer a TV target for sightline simulation. Add/tag a TV object first."

    candidates, err = _simulate_candidates(
        data=data,
        furniture_type=sofa_type,
        room_name=room_name,
        near_index=tv_index,
        face_index=tv_index,
        min_distance=1.6,
        max_distance=3.6,
        require_clear_sightline=needs_sightline,
        max_candidates=max(1, max_options),
        grid_size=0.25,
    )
    if err:
        return err
    if not candidates:
        return "No viable simulated options found for this requirement."

    options: list[dict[str, Any]] = []
    for cand in candidates:
        items = [
            _build_furniture_item(
                sofa_type,
                cand["x"],
                cand["z"],
                cand["rotation_deg"],
            )
        ]

        if "coffee" in req or "living" in req:
            sofa_item = items[0]
            angle = sofa_item["rot"]
            forward_x = math.cos(-angle)
            forward_z = math.sin(-angle)
            cx = sofa_item["pos"][0] + forward_x * 0.9
            cz = sofa_item["pos"][2] + forward_z * 0.9
            coffee = _build_furniture_item("coffee", cx, cz, cand["rotation_deg"])
            coffee_rect = _item_rect(coffee, padding=0.02)

            blocked = False
            for base in data["items"] + items:
                if _rect_intersects(coffee_rect, _item_rect(base, padding=0.02)):
                    blocked = True
                    break
            if not blocked:
                items.append(coffee)

        options.append(
            {
                "score": cand["score"],
                "items": items,
                "summary": (
                    f"{sofa_type} at ({cand['x']:.2f},{cand['z']:.2f}) "
                    f"rot={cand['rotation_deg']:.1f}°"
                ),
                "sightline_blockers": cand["blockers"],
            }
        )

    _SIMULATION_CACHE.clear()
    _SIMULATION_CACHE.extend(options)

    lines = [f"Generated {len(options)} simulated option(s):"]
    for i, option in enumerate(options, start=1):
        blockers = option["sightline_blockers"]
        blocker_text = "clear sightline" if not blockers else f"{len(blockers)} blocker(s)"
        lines.append(
            f"  {i}. {option['summary']}, score={option['score']:.3f}, {blocker_text}, "
            f"adds {len(option['items'])} object(s)"
        )
    lines.append("Use apply_simulated_option(option_index=1) to apply one option.")
    return "\n".join(lines)


@mcp.tool()
def apply_simulated_option(option_index: int = 1) -> str:
    """Apply one previously generated simulation option to the live layout."""
    if option_index < 1:
        return "Error: option_index is 1-based and must be >= 1."
    if not _SIMULATION_CACHE:
        return "Error: no simulated options found. Run simulate_layout_options first."

    idx = option_index - 1
    if idx >= len(_SIMULATION_CACHE):
        return f"Error: option_index {option_index} out of range (1-{len(_SIMULATION_CACHE)})."

    data = _load_layout()
    option = _SIMULATION_CACHE[idx]
    items_to_add = option["items"]

    for pending in items_to_add:
        pending_rect = _item_rect(pending, padding=0.02)
        for existing in data["items"]:
            if not existing.get("visible", True):
                continue
            if _rect_intersects(pending_rect, _item_rect(existing, padding=0.02)):
                return (
                    "Error: simulation option now collides with current layout. "
                    "Re-run simulate_layout_options to refresh candidates."
                )
        data["items"].append(pending)

    err = _save_layout(data)
    if err:
        return err

    return f"Applied simulated option {option_index}. Added {len(items_to_add)} object(s)."


def run_server() -> None:
    """Start the MCP server on stdio."""
    mcp.run()
