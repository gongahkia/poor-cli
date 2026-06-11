from __future__ import annotations

import math
from typing import Any

Rect = tuple[float, float, float, float]
Point = tuple[float, float]
Polygon = list[Point]


def coerce_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def item_dimensions(item: dict[str, Any]) -> tuple[float, float, float]:
    geo = item.get("geo")
    if isinstance(geo, list) and len(geo) >= 3:
        return (
            max(0.01, coerce_float(geo[0], 1.0)),
            max(0.01, coerce_float(geo[1], 1.0)),
            max(0.01, coerce_float(geo[2], 1.0)),
        )
    return (
        max(0.01, coerce_float(item.get("width_m"), 1.0)),
        max(0.01, coerce_float(item.get("height_m"), 1.0)),
        max(0.01, coerce_float(item.get("depth_m"), 1.0)),
    )


def item_center(item: dict[str, Any]) -> Point:
    pos = item.get("pos")
    if isinstance(pos, list) and len(pos) >= 3:
        return (coerce_float(pos[0]), coerce_float(pos[2]))
    return (coerce_float(item.get("x")), coerce_float(item.get("z")))


def item_rect(item: dict[str, Any], padding: float = 0.0) -> Rect:
    polygon = item_polygon(item, padding=padding)
    xs = [point[0] for point in polygon]
    zs = [point[1] for point in polygon]
    return (min(xs), min(zs), max(xs), max(zs))


def rect_intersects(a: Rect, b: Rect) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def rect_gap(a: Rect, b: Rect) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dz = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dz)


def item_polygon(item: dict[str, Any], padding: float = 0.0) -> Polygon:
    width, _, depth = item_dimensions(item)
    cx, cz = item_center(item)
    rot = coerce_float(item.get("rot"), 0.0)
    half_w = width / 2 + max(0.0, padding)
    half_d = depth / 2 + max(0.0, padding)
    corners = [(-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d)]
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    return [(cx + x * cos_r + z * sin_r, cz - x * sin_r + z * cos_r) for x, z in corners]


def polygon_edges(polygon: Polygon) -> list[tuple[Point, Point]]:
    return [(polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))] if len(polygon) >= 2 else []


def polygon_axes(polygon: Polygon) -> list[Point]:
    axes: list[Point] = []
    for a, b in polygon_edges(polygon):
        edge_x = b[0] - a[0]
        edge_z = b[1] - a[1]
        axis = (-edge_z, edge_x)
        length = math.hypot(axis[0], axis[1])
        if length > 1e-9:
            axes.append((axis[0] / length, axis[1] / length))
    return axes


def project_polygon(polygon: Polygon, axis: Point) -> tuple[float, float]:
    values = [point[0] * axis[0] + point[1] * axis[1] for point in polygon]
    return min(values), max(values)


def polygons_intersect(a: Polygon, b: Polygon) -> bool:
    if not a or not b:
        return False
    for axis in polygon_axes(a) + polygon_axes(b):
        a0, a1 = project_polygon(a, axis)
        b0, b1 = project_polygon(b, axis)
        if a1 < b0 or b1 < a0:
            return False
    return True


def distance_point_to_segment(point: Point, a: Point, b: Point) -> float:
    ab_x = b[0] - a[0]
    ab_z = b[1] - a[1]
    ab_len_sq = ab_x * ab_x + ab_z * ab_z
    if ab_len_sq <= 1e-12:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    ap_x = point[0] - a[0]
    ap_z = point[1] - a[1]
    t = max(0.0, min(1.0, (ap_x * ab_x + ap_z * ab_z) / ab_len_sq))
    projected = (a[0] + t * ab_x, a[1] + t * ab_z)
    return math.hypot(point[0] - projected[0], point[1] - projected[1])


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    if len(polygon) < 3:
        return False
    for a, b in polygon_edges(polygon):
        if distance_point_to_segment(point, a, b) <= 1e-9:
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


def polygon_distance(a: Polygon, b: Polygon) -> float:
    if polygons_intersect(a, b):
        return 0.0
    best = float("inf")
    for point in a:
        for start, end in polygon_edges(b):
            best = min(best, distance_point_to_segment(point, start, end))
    for point in b:
        for start, end in polygon_edges(a):
            best = min(best, distance_point_to_segment(point, start, end))
    return best


def normalize_polygon(raw: Any) -> Polygon | None:
    if not isinstance(raw, list):
        return None
    points: Polygon = []
    for entry in raw:
        if isinstance(entry, dict):
            x_raw = entry.get("x")
            z_raw = entry.get("z")
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            x_raw, z_raw = entry[0], entry[1]
        else:
            return None
        points.append((coerce_float(x_raw), coerce_float(z_raw)))
    return points if len(points) >= 3 else None


def polygon_from_bounds(bounds: dict[str, Any]) -> Polygon:
    x_min = coerce_float(bounds.get("x_min"))
    z_min = coerce_float(bounds.get("z_min"))
    x_max = coerce_float(bounds.get("x_max"))
    z_max = coerce_float(bounds.get("z_max"))
    return [(x_min, z_min), (x_max, z_min), (x_max, z_max), (x_min, z_max)]


def room_polygon(room: dict[str, Any]) -> Polygon | None:
    polygon = normalize_polygon(room.get("polygon"))
    if polygon is not None:
        return polygon
    bounds = room.get("bounds")
    if isinstance(bounds, dict):
        return polygon_from_bounds(bounds)
    return None


def item_inside_polygon(item: dict[str, Any], polygon: Polygon, inset: float = 0.0) -> bool:
    test = item_polygon(item, padding=max(0.0, inset))
    return all(point_in_polygon(point, polygon) for point in test)


def item_inside_room(item: dict[str, Any], room: dict[str, Any], inset: float = 0.0) -> bool:
    polygon = room_polygon(room)
    return True if polygon is None else item_inside_polygon(item, polygon, inset=inset)


def door_width(item: dict[str, Any]) -> float:
    if item.get("width_m") is not None:
        return coerce_float(item.get("width_m"))
    opening = item.get("room_capture_opening")
    if isinstance(opening, dict) and opening.get("width_m") is not None:
        return coerce_float(opening.get("width_m"))
    if item.get("type") in {"door", "opening"}:
        width, _, _ = item_dimensions(item)
        return width
    return 0.0


def door_swing_polygon(door: dict[str, Any]) -> Polygon:
    width = max(door_width(door), 0.75)
    thickness = max(item_dimensions(door)[2], 0.08)
    cx, cz = item_center(door)
    direction = str(door.get("swing_direction") or "").lower()
    if direction in {"swing_left", "left", "in_left", "out_left"}:
        rect = (cx - width, cz - thickness / 2, cx, cz + width)
    elif direction in {"swing_right", "right", "in_right", "out_right"}:
        rect = (cx, cz - thickness / 2, cx + width, cz + width)
    elif direction in {"in", "inward", "swing_in"}:
        rect = (cx - width / 2, cz, cx + width / 2, cz + width)
    elif direction in {"out", "outward", "swing_out"}:
        rect = (cx - width / 2, cz - width, cx + width / 2, cz)
    else:
        rect = (cx - width / 2, cz - width / 2, cx + width / 2, cz + width / 2)
    return polygon_from_bounds({"x_min": rect[0], "z_min": rect[1], "x_max": rect[2], "z_max": rect[3]})


def door_swing_conflicts(layout: dict[str, Any]) -> list[dict[str, Any]]:
    items = [item for item in layout.get("items", []) if isinstance(item, dict) and item.get("visible", True)]
    doors = [item for item in items if item.get("type") == "door" or item.get("swing_direction")]
    conflicts: list[dict[str, Any]] = []
    for door in doors:
        if str(door.get("swing_direction") or "").lower() == "sliding":
            continue
        swing = door_swing_polygon(door)
        for other in items:
            if other is door:
                continue
            if polygons_intersect(swing, item_polygon(other)):
                conflicts.append(
                    {
                        "door_id": door.get("id"),
                        "conflict_id": other.get("id"),
                        "door": door.get("name") or door.get("id") or "door",
                        "conflict": other.get("name") or other.get("furnitureType") or other.get("id") or "object",
                        "swing_polygon": [{"x": round(x, 3), "z": round(z, 3)} for x, z in swing],
                    }
                )
    return conflicts


def layout_bounds(layout: dict[str, Any]) -> Rect:
    rects = [item_rect(item) for item in layout.get("items", []) if isinstance(item, dict)]
    for room in layout.get("rooms", []):
        if isinstance(room, dict):
            polygon = room_polygon(room)
            if polygon:
                xs = [point[0] for point in polygon]
                zs = [point[1] for point in polygon]
                rects.append((min(xs), min(zs), max(xs), max(zs)))
    if not rects:
        return (-2.0, -2.0, 2.0, 2.0)
    return (
        min(rect[0] for rect in rects),
        min(rect[1] for rect in rects),
        max(rect[2] for rect in rects),
        max(rect[3] for rect in rects),
    )


def room_bound_plan_application(layout: dict[str, Any], room_id: str, proposed_items: list[dict[str, Any]]) -> dict[str, Any]:
    room = next(
        (
            room
            for room in layout.get("rooms", [])
            if isinstance(room, dict)
            and str(room.get("id") or "").lower() == room_id.lower()
            or isinstance(room, dict)
            and str(room.get("label") or "").lower() == room_id.lower()
        ),
        None,
    )
    if room is None:
        return {"ok": False, "room_id": room_id, "errors": [f"Room '{room_id}' was not found."], "accepted_items": []}
    errors = []
    accepted = []
    for item in proposed_items:
        if item_inside_room(item, room, inset=0.0):
            accepted.append(item.get("id") or item.get("name") or item.get("furnitureType"))
        else:
            errors.append(f"{item.get('id') or item.get('name') or 'item'} is outside {room.get('label') or room_id}.")
    return {"ok": not errors, "room_id": room_id, "errors": errors, "accepted_items": accepted}
