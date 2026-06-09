"""MCP server for haus floor plan editor.

Exposes tools for AI assistants to manipulate and analyze floor plan layouts.
Reads/writes a JSON layout file that the browser editor can import.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

from mcp.server import FastMCP

from .agent_loop import RoomPlan, RoomZone, plan_flat, plan_room
from .logging_utils import configure_logging

LAYOUT_PATH = Path(os.environ.get("HAUS_LAYOUT_PATH", "viewer/mcp-layout.json"))

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

STANDARD_PROFILES: dict[str, dict[str, Any]] = {
    "compact_hdb": {
        "label": "Compact HDB circulation",
        "min_walkway_m": 0.75,
        "clearance_m": 0.45,
        "turning_space_m": None,
        "notes": "Practical compact planning target; not accessibility compliance.",
    },
    "comfortable_home": {
        "label": "Comfortable home circulation",
        "min_walkway_m": 0.90,
        "clearance_m": 0.60,
        "turning_space_m": None,
        "notes": "Everyday comfort target for repeated use.",
    },
    "accessible": {
        "label": "Accessibility-oriented circulation",
        "min_walkway_m": 0.915,
        "clearance_m": 0.90,
        "turning_space_m": 1.50,
        "notes": "Screening target inspired by accessible-route conventions; not a code-compliance certificate.",
    },
    "kitchen_basic": {
        "label": "Kitchen basic ergonomics",
        "min_walkway_m": 0.90,
        "clearance_m": 0.90,
        "turning_space_m": None,
        "notes": "Checks appliance/counter conflicts and working clearances.",
    },
    "bedroom_basic": {
        "label": "Bedroom basic ergonomics",
        "min_walkway_m": 0.75,
        "clearance_m": 0.60,
        "turning_space_m": None,
        "notes": "Checks access around beds, wardrobes, desks, and chairs.",
    },
    "bathroom_basic": {
        "label": "Bathroom basic ergonomics",
        "min_walkway_m": 0.80,
        "clearance_m": 0.75,
        "turning_space_m": None,
        "notes": "Checks fixture conflicts and compact wet-room circulation.",
    },
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


def _normalize_polygon_points(raw: Any) -> list[tuple[float, float]] | None:
    if not isinstance(raw, list):
        return None

    points: list[tuple[float, float]] = []
    for entry in raw:
        if isinstance(entry, dict):
            x_raw = entry.get("x")
            z_raw = entry.get("z")
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            x_raw, z_raw = entry[0], entry[1]
        else:
            return None
        points.append((_coerce_float(x_raw), _coerce_float(z_raw)))

    if len(points) < 3:
        return None
    return points


def _bounds_from_polygon(polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    zs = [point[1] for point in polygon]
    return (min(xs), min(zs), max(xs), max(zs))


def _normalize_room(raw: Any, default_source: str = "curated") -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    polygon = _normalize_polygon_points(raw.get("polygon"))
    bounds_raw = raw.get("bounds")
    if polygon is not None:
        x_min, z_min, x_max, z_max = _bounds_from_polygon(polygon)
        bounds = {"x_min": x_min, "z_min": z_min, "x_max": x_max, "z_max": z_max}
    elif isinstance(bounds_raw, dict):
        bounds = {
            "x_min": _coerce_float(bounds_raw.get("x_min"), 0.0),
            "z_min": _coerce_float(bounds_raw.get("z_min"), 0.0),
            "x_max": _coerce_float(bounds_raw.get("x_max"), 0.0),
            "z_max": _coerce_float(bounds_raw.get("z_max"), 0.0),
        }
    elif isinstance(bounds_raw, (list, tuple)) and len(bounds_raw) >= 4:
        bounds = {
            "x_min": _coerce_float(bounds_raw[0], 0.0),
            "z_min": _coerce_float(bounds_raw[1], 0.0),
            "x_max": _coerce_float(bounds_raw[2], 0.0),
            "z_max": _coerce_float(bounds_raw[3], 0.0),
        }
    else:
        return None

    if bounds["x_max"] <= bounds["x_min"] or bounds["z_max"] <= bounds["z_min"]:
        return None

    label = str(raw.get("label") or raw.get("name") or raw.get("id") or "Room").strip()
    room_id = str(raw.get("id") or label.lower().replace(" ", "_")).strip()
    kind = str(raw.get("kind") or label).strip().lower().replace(" ", "_")
    source = str(raw.get("source") or default_source).strip() or default_source

    room = {
        "id": room_id,
        "label": label,
        "kind": kind,
        "bounds": bounds,
        "source": source,
    }
    if polygon is not None:
        room["polygon"] = [{"x": round(x, 4), "z": round(z, 4)} for x, z in polygon]
    if isinstance(raw.get("openings"), list):
        room["openings"] = [entry for entry in raw["openings"] if isinstance(entry, dict)]
    return room


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

    layout: dict[str, Any] = {"version": _coerce_int(raw.get("version", 1), 1), "items": normalized_items}
    if isinstance(raw.get("metadata"), dict):
        layout["metadata"] = raw["metadata"]

    rooms_raw = raw.get("rooms", [])
    normalized_rooms: list[dict[str, Any]] = []
    if isinstance(rooms_raw, list):
        for entry in rooms_raw:
            room = _normalize_room(entry)
            if room is not None:
                normalized_rooms.append(room)
    if normalized_rooms:
        layout["rooms"] = normalized_rooms

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


def _polygon_area(polygon: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> float:
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for i, (x1, z1) in enumerate(polygon):
        x2, z2 = polygon[(i + 1) % len(polygon)]
        total += x1 * z2 - x2 * z1
    return abs(total) / 2


def _item_inside_polygon(
    item: dict[str, Any],
    polygon: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    inset: float = 0.0,
) -> bool:
    if not polygon:
        return True
    item_polygon = _item_polygon(item, padding=max(0.0, inset))
    room_polygon = list(polygon)
    return all(_point_in_polygon(point, room_polygon) for point in item_polygon)


def _zone_area(zone: RoomZone) -> float:
    if zone.polygon:
        return _polygon_area(zone.polygon)
    x_min, z_min, x_max, z_max = zone.bounds
    return max(0.0, x_max - x_min) * max(0.0, z_max - z_min)


def _item_inside_room_zone(item: dict[str, Any], zone: RoomZone, inset: float = 0.05) -> bool:
    if not _item_inside_bounds(item, zone.bounds, inset=inset):
        return False
    if zone.polygon:
        return _item_inside_polygon(item, zone.polygon, inset=inset)
    return True


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


def _room_bounds_tuple(room: dict[str, Any]) -> tuple[float, float, float, float]:
    bounds = room["bounds"]
    return (
        _coerce_float(bounds.get("x_min"), 0.0),
        _coerce_float(bounds.get("z_min"), 0.0),
        _coerce_float(bounds.get("x_max"), 0.0),
        _coerce_float(bounds.get("z_max"), 0.0),
    )


def _room_polygon_tuple(room: dict[str, Any]) -> tuple[tuple[float, float], ...] | None:
    polygon = _normalize_polygon_points(room.get("polygon"))
    if polygon is None:
        return None
    return tuple(polygon)


def _room_openings_tuple(room: dict[str, Any]) -> tuple[dict[str, object], ...]:
    raw = room.get("openings")
    if not isinstance(raw, list):
        return ()
    return tuple(dict(entry) for entry in raw if isinstance(entry, dict))


def _zone_key(text: str) -> str:
    return text.strip().lower().replace("_", " ").replace("-", " ")


def _fallback_room_zones(data: dict[str, Any]) -> list[RoomZone]:
    x_min, z_min, x_max, z_max = _layout_bounds(data)
    width = max(4.0, x_max - x_min)
    depth = max(4.0, z_max - z_min)
    center_x = (x_min + x_max) / 2
    center_z = (z_min + z_max) / 2
    left_x = center_x - width * 0.24
    right_x = center_x + width * 0.24
    front_z = center_z - depth * 0.24
    back_z = center_z + depth * 0.24
    half_w = width * 0.23
    half_d = depth * 0.23
    specs = [
        ("living", "Living", "family_living", left_x, front_z),
        ("dining", "Dining", "dining", right_x, front_z),
        ("kitchen", "Kitchen", "kitchen", right_x, center_z),
        ("master_bedroom", "Master Bedroom", "bedroom", left_x, back_z),
        ("study", "Study", "office", right_x, back_z),
    ]
    return [
        RoomZone(
            room_id=room_id,
            label=label,
            kind=kind,
            bounds=(cx - half_w, cz - half_d, cx + half_w, cz + half_d),
            source="inferred",
        )
        for room_id, label, kind, cx, cz in specs
    ]


def _layout_room_zones(data: dict[str, Any]) -> list[RoomZone]:
    zones: list[RoomZone] = []
    for room in data.get("rooms", []):
        normalized = _normalize_room(room)
        if normalized is None:
            continue
        zones.append(
            RoomZone(
                room_id=str(normalized["id"]),
                label=str(normalized["label"]),
                kind=str(normalized["kind"]),
                bounds=_room_bounds_tuple(normalized),
                source=str(normalized.get("source", "curated")),
                polygon=_room_polygon_tuple(normalized),
                openings=_room_openings_tuple(normalized),
            )
        )
    return zones or _fallback_room_zones(data)


def _find_room_zone(data: dict[str, Any], room_id: str) -> RoomZone | None:
    wanted = _zone_key(room_id)
    if not wanted:
        return None
    for zone in _layout_room_zones(data):
        candidates = {
            _zone_key(zone.room_id),
            _zone_key(zone.label),
            _zone_key(zone.kind),
        }
        if wanted in candidates:
            return zone
    return None


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
        zone = _find_room_zone(data, room_name)
        if zone is not None:
            return zone.bounds

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

    room_bounds: tuple[float, float, float, float] | None = None
    room_zone: RoomZone | None = None
    if room_name:
        room_bounds = _room_extents(data, room_name)
        if room_bounds is None:
            zone = _find_room_zone(data, room_name)
            if zone is not None:
                room_zone = zone
                room_bounds = zone.bounds

    bounds = room_bounds or _resolve_search_bounds(data, room_name, near_index, max_distance)
    points = _iter_grid_points(bounds, grid_size)
    face_item = data["items"][face_index] if face_index is not None else None
    near_item = data["items"][near_index] if near_index is not None else None

    candidates: list[dict[str, Any]] = []

    for x, z in points:
        rot_deg = _best_candidate_rot_deg(x, z, face_item)
        candidate = _build_furniture_item(furniture_type, x, z, rot_deg)
        if room_zone is not None and not _item_inside_room_zone(candidate, room_zone, inset=0.02):
            continue
        if room_zone is None and room_bounds is not None and not _item_inside_bounds(candidate, room_bounds, inset=0.02):
            continue
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


def _snap_value(value: float, grid_size: float = 0.25) -> float:
    return round(value / grid_size) * grid_size


def _resolve_design_origin(
    data: dict[str, Any],
    room_id: str,
    origin_x: float | None,
    origin_z: float | None,
) -> tuple[float, float, str | None]:
    if (origin_x is None) != (origin_z is None):
        return 0.0, 0.0, "Error: origin_x and origin_z must be provided together."

    if origin_x is not None and origin_z is not None:
        return _snap_value(origin_x), _snap_value(origin_z), None

    if room_id:
        ext = _room_extents(data, room_id)
        if ext is not None:
            return _snap_value((ext[0] + ext[2]) / 2), _snap_value((ext[1] + ext[3]) / 2), None
        zone = _find_room_zone(data, room_id)
        if zone is not None:
            center_x, center_z = zone.center
            return _snap_value(center_x), _snap_value(center_z), None

    x_min, z_min, x_max, z_max = _layout_bounds(data)
    return _snap_value((x_min + x_max) / 2), _snap_value((z_min + z_max) / 2), None


def _design_collision(
    candidate: dict[str, Any],
    existing_items: list[dict[str, Any]],
    pending_items: list[dict[str, Any]],
) -> bool:
    candidate_poly = _item_polygon(candidate, padding=0.03)
    for other in existing_items + pending_items:
        if not other.get("visible", True):
            continue
        if other.get("type") == "model_part":
            continue
        if _polygons_intersect(candidate_poly, _item_polygon(other, padding=0.03)):
            return True
    return False


def _item_inside_bounds(
    item: dict[str, Any],
    bounds: tuple[float, float, float, float],
    inset: float = 0.05,
) -> bool:
    rect = _item_rect(item)
    return (
        rect[0] >= bounds[0] + inset
        and rect[1] <= bounds[2] - inset
        and rect[2] >= bounds[1] + inset
        and rect[3] <= bounds[3] - inset
    )


def _candidate_clearance(
    candidate: dict[str, Any],
    existing_items: list[dict[str, Any]],
    pending_items: list[dict[str, Any]],
) -> float | None:
    candidate_poly = _item_polygon(candidate, padding=0.02)
    nearest = float("inf")
    for other in existing_items + pending_items:
        if not other.get("visible", True):
            continue
        if other.get("type") == "model_part":
            continue
        nearest = min(nearest, _polygon_distance(candidate_poly, _item_polygon(other, padding=0.02)))
    return nearest if nearest < float("inf") else None


def _candidate_room_inset_score(
    candidate: dict[str, Any],
    bounds: tuple[float, float, float, float],
) -> float:
    rect = _item_rect(candidate)
    nearest_edge = min(rect[0] - bounds[0], bounds[2] - rect[1], rect[2] - bounds[1], bounds[3] - rect[3])
    return max(0.0, min(nearest_edge, 0.75) / 0.75)


def _design_candidate_bounds(
    item: dict[str, Any],
    room_bounds: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float]:
    if room_bounds is not None:
        return room_bounds
    base_x = item["pos"][0]
    base_z = item["pos"][2]
    return (base_x - 2.0, base_z - 2.0, base_x + 2.0, base_z + 2.0)


def _with_clear_design_position(
    item: dict[str, Any],
    existing_items: list[dict[str, Any]],
    pending_items: list[dict[str, Any]],
    room_bounds: tuple[float, float, float, float] | None,
    room_polygon: tuple[tuple[float, float], ...] | None = None,
) -> dict[str, Any] | None:
    base_x = item["pos"][0]
    base_z = item["pos"][2]
    bounds = _design_candidate_bounds(item, room_bounds)
    points = _iter_grid_points(bounds, 0.25)
    points.append((_snap_value(base_x), _snap_value(base_z)))

    scored: list[tuple[float, dict[str, Any]]] = []
    for x, z in points:
        candidate = json.loads(json.dumps(item))
        candidate["pos"][0] = _snap_value(x)
        candidate["pos"][2] = _snap_value(z)
        if room_bounds is not None and not _item_inside_bounds(candidate, room_bounds):
            continue
        if room_polygon is not None and not _item_inside_polygon(candidate, room_polygon, inset=0.02):
            continue
        if _design_collision(candidate, existing_items, pending_items):
            continue

        target_dist = math.hypot(candidate["pos"][0] - base_x, candidate["pos"][2] - base_z)
        target_component = max(0.0, 1.0 - target_dist / 3.0)
        clearance = _candidate_clearance(candidate, existing_items, pending_items)
        clearance_component = min(clearance, 1.2) / 1.2 if clearance is not None else 1.0
        inset_component = _candidate_room_inset_score(candidate, bounds)
        score = target_component * 0.55 + clearance_component * 0.30 + inset_component * 0.15
        scored.append((score, candidate))

    if not scored:
        return None
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return scored[0][1]


def _apply_room_plan(
    data: dict[str, Any],
    plan: RoomPlan,
    trace: list[dict[str, Any]],
) -> tuple[list[int], list[str]]:
    applied_indices: list[int] = []
    skipped: list[str] = []
    pending: list[dict[str, Any]] = []

    trace.append({
        "tool": "choose_furniture_set",
        "args": {
            "room_id": plan.room_id,
            "room_kind": plan.room_kind,
            "style_prompt": plan.style_prompt,
            "constraints": plan.constraints,
            "room_zone_source": plan.zone_source,
            "room_bounds": plan.bounds,
            "room_polygon_points": len(plan.room_polygon or ()),
        },
        "result": plan.rationale,
    })

    for spec in plan.items:
        x = _snap_value(plan.origin_x + spec.dx)
        z = _snap_value(plan.origin_z + spec.dz)
        item = _build_furniture_item(spec.furniture_type, x, z, spec.rotation_deg)
        item["room"] = plan.room_id
        item["name"] = f"{plan.room_id} {spec.name or spec.furniture_type}"
        placed = _with_clear_design_position(item, data["items"], pending, plan.bounds, plan.room_polygon)

        args = {
            "furniture_type": spec.furniture_type,
            "x": x,
            "z": z,
            "rotation_deg": spec.rotation_deg,
            "room": plan.room_id,
            "room_zone_source": plan.zone_source,
        }
        if placed is None:
            skipped.append(spec.furniture_type)
            trace.append({
                "tool": "add_furniture",
                "args": args,
                "result": "skipped: no collision-free room-bounded snapped position found",
            })
            continue

        pending.append(placed)
        new_index = len(data["items"]) + len(pending) - 1
        applied_indices.append(new_index)
        trace.append({
            "tool": "add_furniture",
            "args": {
                **args,
                "x": placed["pos"][0],
                "z": placed["pos"][2],
            },
            "result": f"planned item [{new_index}] tagged as room '{plan.room_id}'",
        })

    data["items"].extend(pending)
    if applied_indices:
        trace.append({
            "tool": "snap_to_grid",
            "args": {"indices": applied_indices, "grid_size": 0.25},
            "result": f"{len(applied_indices)} item(s) snapped to 0.25m grid",
        })
        trace.append({
            "tool": "tag_room",
            "args": {"indices": applied_indices, "room_name": plan.room_id},
            "result": f"Tagged {len(applied_indices)} object(s) as '{plan.room_id}'.",
        })
    return applied_indices, skipped


def _format_design_result(
    *,
    plans: list[RoomPlan],
    applied_by_room: dict[str, list[int]],
    skipped_by_room: dict[str, list[str]],
    trace: list[dict[str, Any]],
) -> str:
    total = sum(len(indices) for indices in applied_by_room.values())
    lines = [
        "Design summary:",
        f"  Rooms designed: {len(plans)}",
        f"  Objects added: {total}",
    ]
    for plan in plans:
        applied = applied_by_room.get(plan.room_id, [])
        skipped = skipped_by_room.get(plan.room_id, [])
        lines.append(
            f"  {plan.room_id}: {plan.room_kind.replace('_', ' ')} "
            f"at ({plan.origin_x:.2f}, {plan.origin_z:.2f}), "
            f"zone={plan.zone_source}, added {len(applied)}"
            + (f", skipped {', '.join(skipped)}" if skipped else "")
        )

    lines.append("Tool-call trace:")
    for i, entry in enumerate(trace, start=1):
        args = json.dumps(entry["args"], sort_keys=True)
        lines.append(f"  {i}. {entry['tool']}({args}) -> {entry['result']}")
    return "\n".join(lines)


@mcp.tool()
def list_furniture_catalog() -> str:
    """List all available furniture types with their dimensions."""
    lines = []
    for name, spec in FURNITURE_CATALOG.items():
        lines.append(f"  {name}: {spec['w']}m x {spec['d']}m (height {spec['h']}m)")
    return "Available furniture types:\n" + "\n".join(lines)


@mcp.tool()
def design_room(
    room_id: str = "",
    style_prompt: str = "minimalist HDB",
    constraints: str = "",
    origin_x: float | None = None,
    origin_z: float | None = None,
) -> str:
    """Furnish one room from a high-level style prompt and constraints.

    The tool reads the current layout, infers a room kit, places furniture,
    snaps placements to a 0.25m grid, tags placed items with *room_id*, and
    returns a concise design summary plus a transparent tool-call trace.
    Provide both *origin_x* and *origin_z* to force the room center; otherwise
    an existing room tag or the layout center is used.
    """
    data = _load_layout()
    origin_x_resolved, origin_z_resolved, err = _resolve_design_origin(data, room_id, origin_x, origin_z)
    if err:
        return err
    zone = _find_room_zone(data, room_id)
    tagged_extents = _room_extents(data, room_id) if room_id and zone is None else None
    plan_bounds = zone.bounds if zone is not None else tagged_extents
    zone_source = zone.source if zone is not None else ("tagged" if tagged_extents is not None else "inferred")
    room_polygon = zone.polygon if zone is not None else None

    trace: list[dict[str, Any]] = [
        {
            "tool": "get_layout_summary",
            "args": {},
            "result": f"read {len(data['items'])} existing layout item(s)",
        }
    ]
    plan = plan_room(
        room_id=room_id,
        style_prompt=style_prompt,
        constraints=constraints,
        origin_x=origin_x_resolved,
        origin_z=origin_z_resolved,
        bounds=plan_bounds,
        zone_source=zone_source,
        room_polygon=room_polygon,
    )
    applied, skipped = _apply_room_plan(data, plan, trace)
    save_err = _save_layout(data)
    if save_err:
        return save_err

    return _format_design_result(
        plans=[plan],
        applied_by_room={plan.room_id: applied},
        skipped_by_room={plan.room_id: skipped},
        trace=trace,
    )


@mcp.tool()
def design_flat(
    style_prompt: str = "minimalist 4-room family flat",
    constraints: str = "",
    target: str = "whole_flat",
) -> str:
    """Furnish a whole flat from a high-level style prompt.

    *target* currently accepts whole-flat wording such as "whole_flat",
    "flat", "home", "apartment", "hdb", or "bto". The tool reads the layout
    bounds, plans multiple room zones, places and tags furniture, and returns
    a summary with a transparent trace.
    """
    normalized_target = target.strip().lower().replace("-", "_").replace(" ", "_") or "whole_flat"
    if normalized_target not in {"whole_flat", "flat", "home", "apartment", "hdb", "bto"}:
        return "Error: target must be a whole-flat target such as 'whole_flat', 'flat', 'hdb', or 'bto'."

    data = _load_layout()
    bounds = _layout_bounds(data)
    zones = _layout_room_zones(data)
    trace: list[dict[str, Any]] = [
        {
            "tool": "get_layout_summary",
            "args": {},
            "result": (
                f"read {len(data['items'])} existing layout item(s), bounds={bounds}, "
                f"room_zones={len(zones)}"
            ),
        }
    ]
    plans = plan_flat(
        style_prompt=style_prompt,
        constraints=constraints,
        target=target,
        bounds=bounds,
        room_zones=zones,
    )

    applied_by_room: dict[str, list[int]] = {}
    skipped_by_room: dict[str, list[str]] = {}
    for plan in plans:
        applied, skipped = _apply_room_plan(data, plan, trace)
        applied_by_room[plan.room_id] = applied
        skipped_by_room[plan.room_id] = skipped

    save_err = _save_layout(data)
    if save_err:
        return save_err

    return _format_design_result(
        plans=plans,
        applied_by_room=applied_by_room,
        skipped_by_room=skipped_by_room,
        trace=trace,
    )


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
    """Compute room area from a curated room polygon/bounds or tagged-object bounds."""
    data = _load_layout()
    zone = _find_room_zone(data, room_name)
    if zone is not None:
        area = _zone_area(zone)
        source = "polygon" if zone.polygon else "bounds"
        x_min, z_min, x_max, z_max = zone.bounds
        return (
            f"Room '{zone.label}' {source} area:\n"
            f"  X: {x_min:.2f} to {x_max:.2f} ({x_max - x_min:.2f}m)\n"
            f"  Z: {z_min:.2f} to {z_max:.2f} ({z_max - z_min:.2f}m)\n"
            f"  Area: {area:.2f}m²"
        )

    ext = _room_extents(data, room_name)
    if ext is None:
        return f"Error: no room zone or tagged objects found for room '{room_name}'."

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


ROOM_TEMPLATES: dict[str, dict[str, Any]] = {
    "work_from_home": {
        "description": "Home office setup with desk, chair, and bookshelf",
        "items": [
            {"type": "desk", "dx": 0.0, "dz": 0.0, "rot": 0},
            {"type": "chair", "dx": 0.0, "dz": 0.8, "rot": 180},
            {"type": "bookshelf", "dx": -1.5, "dz": 0.0, "rot": 0},
        ],
    },
    "family_living": {
        "description": "Family living room with L-sofa, coffee table, and TV console",
        "items": [
            {"type": "sofa_l", "dx": 0.0, "dz": 0.0, "rot": 0},
            {"type": "coffee", "dx": 0.0, "dz": -1.2, "rot": 0},
            {"type": "tv_console", "dx": 0.0, "dz": -2.8, "rot": 0},
        ],
    },
    "family_bedroom": {
        "description": "Master bedroom with queen bed, wardrobe, and two bedsides",
        "items": [
            {"type": "bed_queen", "dx": 0.0, "dz": 0.0, "rot": 0},
            {"type": "wardrobe", "dx": -2.0, "dz": 0.0, "rot": 90},
            {"type": "bedside", "dx": -1.0, "dz": 0.0, "rot": 0},
            {"type": "bedside", "dx": 1.0, "dz": 0.0, "rot": 0},
        ],
    },
    "family_dining": {
        "description": "Dining area with 6-seat table and shoe rack",
        "items": [
            {"type": "dining_6", "dx": 0.0, "dz": 0.0, "rot": 0},
            {"type": "shoe_rack", "dx": -1.8, "dz": 0.0, "rot": 90},
        ],
    },
    "rental_bedroom": {
        "description": "Minimal rental bedroom with single bed, wardrobe, and desk",
        "items": [
            {"type": "bed_single", "dx": 0.0, "dz": 0.0, "rot": 0},
            {"type": "wardrobe_s", "dx": -1.5, "dz": 0.0, "rot": 90},
            {"type": "desk", "dx": 1.5, "dz": 0.0, "rot": 0},
            {"type": "chair", "dx": 1.5, "dz": 0.8, "rot": 180},
        ],
    },
    "rental_studio": {
        "description": "Compact studio with sofa, coffee table, TV console, and single bed",
        "items": [
            {"type": "sofa_2", "dx": 0.0, "dz": 0.0, "rot": 0},
            {"type": "coffee", "dx": 0.0, "dz": -1.0, "rot": 0},
            {"type": "tv_console", "dx": 0.0, "dz": -2.4, "rot": 0},
            {"type": "bed_single", "dx": 3.0, "dz": 0.0, "rot": 0},
        ],
    },
}


@mcp.tool()
def list_room_templates() -> str:
    """List available room-template presets."""
    lines = ["Available room templates:"]
    for name, tpl in ROOM_TEMPLATES.items():
        types = [e["type"] for e in tpl["items"]]
        lines.append(f"  {name}: {tpl['description']} [{', '.join(types)}]")
    return "\n".join(lines)


@mcp.tool()
def apply_room_template(
    template_name: str,
    origin_x: float = 0.0,
    origin_z: float = 0.0,
    room_name: str = "",
) -> str:
    """Place a room-template preset at the given origin.

    Offsets in the template are relative to (origin_x, origin_z).
    If *room_name* is provided, all placed items are tagged with it.
    """
    if template_name not in ROOM_TEMPLATES:
        available = ", ".join(ROOM_TEMPLATES)
        return f"Error: unknown template '{template_name}'. Available: {available}"

    tpl = ROOM_TEMPLATES[template_name]
    data = _load_layout()
    placed: list[str] = []

    for entry in tpl["items"]:
        ft = entry["type"]
        if ft not in FURNITURE_CATALOG:
            continue
        x = origin_x + entry["dx"]
        z = origin_z + entry["dz"]
        item = _build_furniture_item(ft, x, z, entry["rot"])
        if room_name:
            item["room"] = room_name
        cand_poly = _item_polygon(item, padding=0.02)
        collision = False
        for existing in data["items"]:
            if not existing.get("visible", True):
                continue
            if _polygons_intersect(cand_poly, _item_polygon(existing, padding=0.02)):
                collision = True
                break
        if collision:
            placed.append(f"{ft} SKIPPED (collision)")
        else:
            data["items"].append(item)
            placed.append(f"{ft} at ({x:.2f}, {z:.2f})")

    err = _save_layout(data)
    if err:
        return err

    tag = f" in room '{room_name}'" if room_name else ""
    lines = [f"Applied template '{template_name}'{tag}:"]
    for p in placed:
        lines.append(f"  {p}")
    return "\n".join(lines)


@mcp.tool()
def suggest_placement_json(
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
    """Return placement candidates with per-component score breakdowns as JSON.

    Each candidate includes *distance_component*, *sightline_component*,
    and *accessibility_component* so the caller can understand exactly why
    a candidate scored the way it did.
    """
    if min_distance < 0:
        return json.dumps({"error": "min_distance must be >= 0"})
    if max_distance <= 0 or max_distance < min_distance:
        return json.dumps({"error": "max_distance must be >= min_distance and > 0"})

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
        return json.dumps({"error": err})
    if not candidates:
        return json.dumps({"candidates": [], "note": "no valid placements found"})

    enriched: list[dict[str, Any]] = []
    target = (min_distance + max_distance) / 2
    for cand in candidates:
        dist_comp = 0.0
        if cand["distance_to_reference_m"] is not None:
            near_dist = cand["distance_to_reference_m"]
            dist_comp = round(max(0.0, 1.0 - abs(near_dist - target) / max(target, 0.1)) * 0.45, 4)
        sight_comp = 0.0
        if face_index is not None:
            blockers = cand["blockers"]
            sight_comp = round(0.35 if not blockers else max(0.0, 0.22 - 0.03 * len(blockers)), 4)
        acc_comp = 0.0
        if cand.get("accessibility_score") is not None:
            acc_comp = round(cand["accessibility_score"] * 0.20, 4)
        enriched.append({
            "x": cand["x"],
            "z": cand["z"],
            "rotation_deg": cand["rotation_deg"],
            "score": cand["score"],
            "breakdown": {
                "distance_component": dist_comp,
                "distance_weight": 0.45,
                "sightline_component": sight_comp,
                "sightline_weight": 0.35,
                "accessibility_component": acc_comp,
                "accessibility_weight": 0.20,
            },
            "distance_to_reference_m": cand["distance_to_reference_m"],
            "nearest_clearance_m": cand["nearest_clearance_m"],
            "accessibility_score": cand.get("accessibility_score"),
            "blockers": [
                {"index": b["index"], "type": b["type"], "distance": round(b["distance"], 3)}
                for b in cand["blockers"]
            ],
        })

    return json.dumps({"candidates": enriched}, indent=2)


@mcp.tool()
def score_doorway_accessibility(
    door_x: float,
    door_z: float,
    door_width: float = 0.9,
    required_clearance: float = 0.9,
) -> str:
    """Score accessibility around a doorway/opening at a given position.

    Checks both sides of the door for furniture clearance and returns a
    0-1 score.  *required_clearance* is the minimum free radius (metres)
    expected on each side — 0.9 m is a common wheelchair-accessible
    standard.
    """
    data = _load_layout()
    items = data["items"]
    if door_width <= 0 or required_clearance <= 0:
        return "Error: door_width and required_clearance must be > 0."

    half_w = door_width / 2
    check_radius = required_clearance + half_w
    min_clearance = float("inf")
    blocking: list[str] = []

    for i, item in enumerate(items):
        if not item.get("visible", True):
            continue
        poly = _item_polygon(item)
        for corner in poly:
            dist = math.hypot(corner[0] - door_x, corner[1] - door_z)
            if dist < min_clearance:
                min_clearance = dist
        edge_dist = _polygon_distance(
            [(door_x - half_w, door_z), (door_x + half_w, door_z)], poly
        )
        if edge_dist < required_clearance:
            blocking.append(f"[{i}] {_item_label(item)} ({edge_dist:.2f}m)")

    effective = min(min_clearance, check_radius)
    score = round(min(effective / check_radius, 1.0), 3)

    lines = [
        f"Doorway at ({door_x:.2f}, {door_z:.2f}), width={door_width:.2f}m",
        f"Required clearance: {required_clearance:.2f}m",
        f"Nearest furniture distance: {min_clearance:.2f}m" if min_clearance < float("inf") else "No nearby furniture",
        f"Accessibility score: {score}",
    ]
    if blocking:
        lines.append(f"Objects within clearance zone ({len(blocking)}):")
        for b in blocking:
            lines.append(f"  {b}")
    else:
        lines.append("Clearance zone is free.")
    return "\n".join(lines)


def _walkway_corridor_polygon(
    x1: float,
    z1: float,
    x2: float,
    z2: float,
    width: float,
) -> list[tuple[float, float]]:
    dx = x2 - x1
    dz = z2 - z1
    length = math.hypot(dx, dz)
    if length <= 1e-9:
        return []
    nx = -dz / length * width / 2
    nz = dx / length * width / 2
    return [
        (x1 + nx, z1 + nz),
        (x2 + nx, z2 + nz),
        (x2 - nx, z2 - nz),
        (x1 - nx, z1 - nz),
    ]


def _distance_point_to_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> float:
    if _point_in_polygon(point, polygon):
        return 0.0
    return min(
        _distance_point_to_segment(point, edge_a, edge_b)
        for edge_a, edge_b in _polygon_edges(polygon)
    )


@mcp.tool()
def score_walkway(
    x1: float,
    z1: float,
    x2: float,
    z2: float,
    min_width: float = 0.9,
) -> str:
    """Score a walkway/corridor between two points.

    Casts a line from (x1,z1) to (x2,z2) and measures the narrowest gap
    on either side.  Returns a 0-1 score based on whether *min_width* is
    maintained along the full path.
    """
    data = _load_layout()
    items = data["items"]
    if min_width <= 0:
        return "Error: min_width must be > 0."

    dx = x2 - x1
    dz = z2 - z1
    length = math.hypot(dx, dz)
    if length < 0.01:
        return "Error: walkway start and end are the same point."

    corridor = _walkway_corridor_polygon(x1, z1, x2, z2, min_width)
    steps = max(2, int(length / 0.25))
    narrowest = float("inf")
    narrowest_pos: tuple[float, float] = (x1, z1)
    obstructions: list[str] = []

    polygons: list[tuple[int, dict[str, Any], list[tuple[float, float]]]] = []
    for i, item in enumerate(items):
        if item.get("visible", True):
            polygons.append((i, item, _item_polygon(item)))

    for s in range(steps + 1):
        t = s / steps
        px = x1 + dx * t
        pz = z1 + dz * t
        local_min = float("inf")
        for i, item, poly in polygons:
            d = _distance_point_to_polygon((px, pz), poly)
            if d < local_min:
                local_min = d
            if corridor and _polygons_intersect(corridor, poly):
                label = f"[{i}] {_item_label(item)}"
                if label not in obstructions:
                    obstructions.append(label)
        if local_min < narrowest:
            narrowest = local_min
            narrowest_pos = (px, pz)

    effective_width = narrowest * 2
    score = round(min(effective_width / min_width, 1.0), 3) if narrowest < float("inf") else 1.0

    lines = [
        f"Walkway ({x1:.2f},{z1:.2f}) -> ({x2:.2f},{z2:.2f}), length={length:.2f}m",
        f"Required width: {min_width:.2f}m",
        "Method: swept corridor polygon with sampled centerline clearance",
        f"Narrowest gap: {effective_width:.2f}m at ({narrowest_pos[0]:.2f}, {narrowest_pos[1]:.2f})" if narrowest < float("inf") else "No obstructions detected",
        f"Walkway score: {score}",
    ]
    if obstructions:
        lines.append(f"Encroaching objects ({len(obstructions)}):")
        for o in obstructions:
            lines.append(f"  {o}")
    else:
        lines.append("Walkway is clear.")
    return "\n".join(lines)


def _profile(profile: str) -> tuple[str, dict[str, Any]]:
    normalized = profile.strip().lower().replace("-", "_").replace(" ", "_") or "compact_hdb"
    if normalized not in STANDARD_PROFILES:
        normalized = "compact_hdb"
    return normalized, STANDARD_PROFILES[normalized]


def _visible_layout_polygons(data: dict[str, Any]) -> list[tuple[int, dict[str, Any], list[tuple[float, float]]]]:
    return [
        (i, item, _item_polygon(item))
        for i, item in enumerate(data["items"])
        if item.get("visible", True) and item.get("type") != "model_part"
    ]


def _overlap_warnings(data: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    polygons = _visible_layout_polygons(data)
    for pos, (left_idx, left, left_poly) in enumerate(polygons):
        for right_idx, right, right_poly in polygons[pos + 1 :]:
            if _polygons_intersect(left_poly, right_poly):
                warnings.append(f"[{left_idx}] {_item_label(left)} overlaps [{right_idx}] {_item_label(right)}")
    return warnings


def _room_fit_warnings(data: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for i, item in enumerate(data["items"]):
        room_name = str(item.get("room") or "")
        if not room_name:
            continue
        zone = _find_room_zone(data, room_name)
        if zone is None:
            continue
        if not _item_inside_room_zone(item, zone, inset=0.02):
            warnings.append(f"[{i}] {_item_label(item)} is outside room '{zone.label}'")
    return warnings


def _clearance_warnings(data: dict[str, Any], clearance_m: float, profile_name: str) -> list[str]:
    warnings: list[str] = []
    polygons = _visible_layout_polygons(data)
    for pos, (left_idx, left, left_poly) in enumerate(polygons):
        for right_idx, right, right_poly in polygons[pos + 1 :]:
            distance = _polygon_distance(left_poly, right_poly)
            if distance >= clearance_m:
                continue
            left_type = _item_label(left)
            right_type = _item_label(right)
            pair = {left_type, right_type}
            furniture_pair = any(kind in pair for kind in {"bed_queen", "bed_king", "bed_single", "wardrobe", "desk", "chair"})
            kitchen_pair = any(kind in pair for kind in {"fridge", "sink", "kitchen_counter", "washer"})
            bathroom_pair = any(kind in pair for kind in {"toilet", "shower", "sink"})
            if profile_name == "bedroom_basic" and not furniture_pair:
                continue
            if profile_name == "kitchen_basic" and not kitchen_pair:
                continue
            if profile_name == "bathroom_basic" and not bathroom_pair:
                continue
            warnings.append(
                f"[{left_idx}] {left_type} and [{right_idx}] {right_type} have {distance:.2f}m clearance; target is {clearance_m:.2f}m"
            )
    return warnings


def _walkway_summary_for_profile(data: dict[str, Any], min_width: float) -> tuple[float, str]:
    x_min, z_min, x_max, z_max = _layout_bounds(data)
    if abs(x_max - x_min) <= 0.01 and abs(z_max - z_min) <= 0.01:
        return 1.0, "No walkway corridor available because the layout is empty or degenerate."
    result = score_walkway(x_min, z_min, x_max, z_max, min_width=min_width)
    match = None
    for line in result.splitlines():
        if line.startswith("Walkway score:"):
            match = line.split(":", 1)[1].strip()
            break
    try:
        score = float(match or "0")
    except ValueError:
        score = 0.0
    return score, result


def _layout_quality_assessment(profile: str = "compact_hdb") -> dict[str, Any]:
    profile_name, spec = _profile(profile)
    data = _load_layout()
    min_walkway = float(spec["min_walkway_m"])
    clearance = float(spec["clearance_m"])
    walkway_score, walkway_text = _walkway_summary_for_profile(data, min_walkway)

    warnings = []
    warnings.extend(_overlap_warnings(data))
    warnings.extend(_room_fit_warnings(data))
    warnings.extend(_clearance_warnings(data, clearance, profile_name))

    if walkway_score < 1.0:
        warnings.append(f"Primary circulation is below the {min_walkway:.3f}m target.")
    turning_space = spec.get("turning_space_m")
    if turning_space and data["items"]:
        x_min, z_min, x_max, z_max = _layout_bounds(data)
        if (x_max - x_min) < turning_space or (z_max - z_min) < turning_space:
            warnings.append(f"No obvious {turning_space:.2f}m turning-space envelope in current layout bounds.")

    return {
        "profile": profile_name,
        "label": spec["label"],
        "notes": spec["notes"],
        "min_walkway_m": min_walkway,
        "clearance_target_m": clearance,
        "turning_space_m": turning_space,
        "walkway_score": walkway_score,
        "walkway": walkway_text,
        "warning_count": len(warnings),
        "warnings": warnings,
        "status": "ready_to_apply" if not warnings else "needs_revision",
    }


@mcp.tool()
def score_layout(profile: str = "compact_hdb") -> str:
    """Score the current layout against a usability/standards profile."""
    assessment = _layout_quality_assessment(profile)
    lines = [
        f"Layout profile: {assessment['label']} ({assessment['profile']})",
        f"Status: {assessment['status'].replace('_', ' ')}",
        f"Minimum clear route target: {assessment['min_walkway_m']:.3f}m",
        f"Object clearance target: {assessment['clearance_target_m']:.2f}m",
        f"Walkway score: {assessment['walkway_score']:.3f}",
        f"Notes: {assessment['notes']}",
    ]
    if assessment["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in assessment["warnings"])
    else:
        lines.append("No warnings for this profile.")
    return "\n".join(lines)


def _semantic_kind(item: dict[str, Any]) -> str:
    item_type = str(item.get("type", "object"))
    furniture_type = str(item.get("furnitureType") or "")
    if item_type == "wall":
        return "wall"
    if item_type == "model_part":
        return "model_part"
    if furniture_type in {"sink", "toilet", "shower"}:
        return "fixture"
    if furniture_type in {"fridge", "washer", "kitchen_counter"}:
        return "appliance"
    return "furniture"


def _semantic_layout() -> dict[str, Any]:
    data = _load_layout()
    rooms = []
    for zone in _layout_room_zones(data):
        rooms.append(
            {
                "id": zone.room_id,
                "label": zone.label,
                "kind": zone.kind,
                "source": zone.source,
                "bounds": {
                    "x_min": round(zone.bounds[0], 3),
                    "z_min": round(zone.bounds[1], 3),
                    "x_max": round(zone.bounds[2], 3),
                    "z_max": round(zone.bounds[3], 3),
                },
                "polygon": [{"x": round(x, 3), "z": round(z, 3)} for x, z in zone.polygon or ()],
                "openings": list(zone.openings),
                "area_m2": round(_zone_area(zone), 3),
            }
        )

    objects = []
    for i, item in enumerate(data["items"]):
        objects.append(
            {
                "index": i,
                "semantic_kind": _semantic_kind(item),
                "type": item.get("type"),
                "furniture_type": item.get("furnitureType"),
                "name": item.get("name"),
                "room": item.get("room"),
                "position_m": {"x": item["pos"][0], "y": item["pos"][1], "z": item["pos"][2]},
                "rotation_y_rad": item.get("rot", 0.0),
                "dimensions_m": {"width": item["geo"][0], "height": item["geo"][1], "depth": item["geo"][2]},
            }
        )

    assessment = _layout_quality_assessment("compact_hdb")
    return {
        "schema": "haus.semantic_layout.v1",
        "units": "meters",
        "rooms": rooms,
        "objects": objects,
        "circulation_profiles": {
            name: {
                "label": spec["label"],
                "min_walkway_m": spec["min_walkway_m"],
                "clearance_m": spec["clearance_m"],
                "notes": spec["notes"],
            }
            for name, spec in STANDARD_PROFILES.items()
        },
        "bim_readiness": {
            "status": "ready_for_mapping" if rooms and objects else "incomplete",
            "not_ifc": True,
            "missing": [
                "true wall/opening topology",
                "door swings",
                "window metadata",
                "MEP/plumbing/electrical systems",
                "code-compliance certification",
            ],
            "quality_status": assessment["status"],
            "quality_warnings": assessment["warnings"],
        },
    }


@mcp.tool()
def get_semantic_layout_json() -> str:
    """Return semantic layout JSON for future BIM/IFC mapping."""
    return json.dumps(_semantic_layout(), indent=2)


@mcp.tool()
def bim_readiness_report() -> str:
    """Report how ready the current layout is for BIM/IFC-style mapping."""
    semantic = _semantic_layout()
    readiness = semantic["bim_readiness"]
    lines = [
        "BIM readiness report",
        f"Status: {readiness['status']}",
        "This is not an IFC export or compliance certificate.",
        f"Rooms: {len(semantic['rooms'])}",
        f"Objects: {len(semantic['objects'])}",
        f"Quality status: {readiness['quality_status']}",
        "Missing for full BIM:",
    ]
    lines.extend(f"  - {item}" for item in readiness["missing"])
    warnings = readiness["quality_warnings"]
    if warnings:
        lines.append("Quality warnings:")
        lines.extend(f"  - {item}" for item in warnings)
    return "\n".join(lines)


def run_server() -> None:
    """Start the MCP server on stdio."""
    mcp.run()
