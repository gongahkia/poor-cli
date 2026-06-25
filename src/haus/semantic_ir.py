from __future__ import annotations

import copy
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from importlib.resources import files
from typing import Any, cast

from . import geometry
from .constraints import DEFAULT_CONSTRAINT_PACKS, load_constraint_packs, merge_constraint_targets
from .workbench import build_validation_report, migrate_layout, validate_layout_schema

SEMANTIC_SCHEMA_ID = "haus.semantic_layout.v1"
LAYOUT_GRAPH_SCHEMA_ID = "haus.layout_graph.v1"
SCENARIO_PATCH_SCHEMA_ID = "haus.scenario_patch.v1"
MULTIMODAL_INTAKE_SCHEMA_ID = "haus.multimodal_intake.v1"
AGENT_EVAL_SUITE_SCHEMA_ID = "haus.agent_eval_suite.v1"

SEVERITY_ORDER = {"info": 0, "warning": 1, "serious": 2, "blocked": 3}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).strip()
    return text or fallback


def _num(value: Any, fallback: float = 0.0) -> float:
    return geometry.coerce_float(value, fallback)


def _round(value: float) -> float:
    return round(value, 4)


def _point_dict(point: geometry.Point) -> dict[str, float]:
    return {"x": _round(point[0]), "z": _round(point[1])}


def _rect_dict(rect: geometry.Rect) -> dict[str, float]:
    return {"x_min": _round(rect[0]), "z_min": _round(rect[1]), "x_max": _round(rect[2]), "z_max": _round(rect[3])}


def _bounds_from_polygon(polygon: geometry.Polygon) -> geometry.Rect:
    xs = [point[0] for point in polygon]
    zs = [point[1] for point in polygon]
    return (min(xs), min(zs), max(xs), max(zs))


def _polygon_area(polygon: geometry.Polygon) -> float:
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for index, (x1, z1) in enumerate(polygon):
        x2, z2 = polygon[(index + 1) % len(polygon)]
        total += x1 * z2 - x2 * z1
    return abs(total) / 2


def _room_label(room: dict[str, Any]) -> str:
    return _text(room.get("label") or room.get("name") or room.get("id"), "Room")


def _room_kind(room: dict[str, Any]) -> str:
    return _text(room.get("kind") or _room_label(room), "room").lower().replace(" ", "_")


def _room_id(room: dict[str, Any], index: int) -> str:
    return _text(room.get("id") or _room_label(room).lower().replace(" ", "_"), f"room-{index + 1}")


def _rooms(layout: dict[str, Any]) -> list[dict[str, Any]]:
    rooms: list[dict[str, Any]] = []
    for index, room in enumerate(layout.get("rooms", [])):
        if not isinstance(room, dict):
            continue
        polygon = geometry.room_polygon(room)
        if polygon is None:
            continue
        bounds = _bounds_from_polygon(polygon)
        room_id = _room_id(room, index)
        rooms.append(
            {
                "id": room_id,
                "label": _room_label(room),
                "kind": _room_kind(room),
                "bounds": bounds,
                "polygon": polygon,
                "source": _text(room.get("source"), "layout"),
                "openings": [entry for entry in room.get("openings", []) if isinstance(entry, dict)],
                "confidence": _text(room.get("confidence"), "estimated"),
                "locked": bool(room.get("locked", False)),
            }
        )
    if rooms:
        return rooms
    bounds = geometry.layout_bounds(layout)
    polygon = geometry.polygon_from_bounds({"x_min": bounds[0], "z_min": bounds[1], "x_max": bounds[2], "z_max": bounds[3]})
    return [
        {
            "id": "project",
            "label": "Project",
            "kind": "whole_home",
            "bounds": bounds,
            "polygon": polygon,
            "source": "inferred_bounds",
            "openings": [],
            "confidence": "low",
            "locked": False,
        }
    ]


def _public_rooms(rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public = []
    for room in rooms:
        polygon = room["polygon"]
        public.append(
            {
                "id": room["id"],
                "label": room["label"],
                "kind": room["kind"],
                "bounds": _rect_dict(room["bounds"]),
                "polygon": [_point_dict(point) for point in polygon],
                "area_m2": _round(_polygon_area(polygon)),
                "source": room["source"],
                "confidence": room["confidence"],
                "locked": room["locked"],
                "openings": copy.deepcopy(room.get("openings", [])),
            }
        )
    return public


def _room_by_label(rooms: list[dict[str, Any]], label: str) -> str | None:
    wanted = label.strip().lower().replace("_", " ").replace("-", " ")
    for room in rooms:
        candidates = {
            str(room["id"]).lower().replace("_", " ").replace("-", " "),
            str(room["label"]).lower().replace("_", " ").replace("-", " "),
            str(room["kind"]).lower().replace("_", " ").replace("-", " "),
        }
        if wanted in candidates:
            return str(room["id"])
    return None


def _room_ids_at_point(point: geometry.Point, rooms: list[dict[str, Any]], tolerance: float = 0.08) -> list[str]:
    matches = []
    for room in rooms:
        polygon = room["polygon"]
        if geometry.point_in_polygon(point, polygon):
            matches.append(str(room["id"]))
            continue
        if min((geometry.distance_point_to_segment(point, a, b) for a, b in geometry.polygon_edges(polygon)), default=999.0) <= tolerance:
            matches.append(str(room["id"]))
    return matches


def _assigned_room_id(item: dict[str, Any], rooms: list[dict[str, Any]]) -> str | None:
    room_name = item.get("room")
    if room_name:
        matched = _room_by_label(rooms, str(room_name))
        if matched:
            return matched
    point = geometry.item_center(item)
    matches = _room_ids_at_point(point, rooms)
    return matches[0] if matches else None


def _semantic_kind(item: dict[str, Any]) -> str:
    item_type = str(item.get("type", "object"))
    furniture_type = str(item.get("furnitureType") or "")
    if item_type == "wall":
        return "wall"
    if item_type in {"door", "opening"}:
        return "opening"
    if item_type in {"reference_image", "model_part"}:
        return item_type
    if furniture_type in {"sink", "toilet", "shower"}:
        return "fixture"
    if furniture_type in {"fridge", "washer", "kitchen_counter", "stove", "oven"}:
        return "appliance"
    return "furniture"


def _item_label(item: dict[str, Any]) -> str:
    return _text(item.get("name") or item.get("furnitureType") or item.get("type"), "object")


def _item_id(item: dict[str, Any], index: int) -> str:
    return _text(item.get("id"), f"item-{index + 1}")


def _public_objects(layout: dict[str, Any], rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    objects = []
    for index, item in enumerate(layout.get("items", [])):
        if not isinstance(item, dict):
            continue
        width, height, depth = geometry.item_dimensions(item)
        center = geometry.item_center(item)
        objects.append(
            {
                "id": _item_id(item, index),
                "index": index,
                "label": _item_label(item),
                "semantic_kind": _semantic_kind(item),
                "type": item.get("type", "object"),
                "furniture_type": item.get("furnitureType"),
                "room_id": _assigned_room_id(item, rooms),
                "position_m": {"x": _round(center[0]), "y": _round(_num(item.get("pos", [0, 0, 0])[1] if isinstance(item.get("pos"), list) and len(item.get("pos", [])) > 1 else 0.0)), "z": _round(center[1])},
                "rotation_y_rad": _round(_num(item.get("rot"), 0.0)),
                "dimensions_m": {"width": _round(width), "height": _round(height), "depth": _round(depth)},
                "footprint": [_point_dict(point) for point in geometry.item_polygon(item)],
                "bounds": _rect_dict(geometry.item_rect(item)),
                "visible": bool(item.get("visible", True)),
                "locked": bool(item.get("locked", False)),
                "movable": bool(item.get("movable", True)),
                "confidence": _text(item.get("confidence"), "estimated"),
                "structural_status": item.get("structural_status") if item.get("type") == "wall" else None,
                "source": _text(item.get("source"), "layout"),
            }
        )
    return objects


def _openings(layout: dict[str, Any], rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    openings: list[dict[str, Any]] = []
    for room in rooms:
        for index, opening in enumerate(room.get("openings", [])):
            point: geometry.Point | None = None
            if opening.get("x") is not None and opening.get("z") is not None:
                point = (_num(opening.get("x")), _num(opening.get("z")))
            connects = [str(room["id"])]
            raw_connects = opening.get("connects_to")
            if isinstance(raw_connects, list):
                connects.extend(str(value) for value in raw_connects)
            elif raw_connects:
                connects.append(str(raw_connects))
            openings.append(
                {
                    "id": _text(opening.get("id"), f"{room['id']}-opening-{index + 1}"),
                    "type": _text(opening.get("type") or opening.get("kind"), "opening"),
                    "width_m": _num(opening.get("width_m") or opening.get("width"), 0.0),
                    "room_ids": sorted(set(connects)),
                    "position_m": _point_dict(point) if point else None,
                    "swing_direction": _text(opening.get("swing_direction"), "unknown"),
                    "confidence": _text(opening.get("confidence"), "estimated"),
                }
            )
    for index, item in enumerate(layout.get("items", [])):
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"door", "opening"} and not geometry.door_width(item):
            continue
        center = geometry.item_center(item)
        room_ids = _room_ids_at_point(center, rooms)
        if item.get("room"):
            assigned = _room_by_label(rooms, str(item["room"]))
            if assigned:
                room_ids.append(assigned)
        openings.append(
            {
                "id": _item_id(item, index),
                "type": _text(item.get("opening_type") or item.get("type"), "opening"),
                "width_m": _round(geometry.door_width(item)),
                "room_ids": sorted(set(room_ids)),
                "position_m": _point_dict(center),
                "swing_direction": _text(item.get("swing_direction"), "unknown"),
                "confidence": _text(item.get("confidence"), "estimated"),
            }
        )
    return openings


def _adjacency_edges(rooms: list[dict[str, Any]], openings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for index, left in enumerate(rooms):
        for right in rooms[index + 1 :]:
            distance = geometry.polygon_distance(left["polygon"], right["polygon"])
            if distance <= 0.08:
                left_id, right_id = sorted((str(left["id"]), str(right["id"])))
                key = (left_id, right_id)
                edges[key] = {
                    "from": key[0],
                    "to": key[1],
                    "relation": "adjacent",
                    "distance_m": _round(distance),
                    "evidence": "room_boundary",
                }
    for opening in openings:
        room_ids = [room_id for room_id in opening.get("room_ids", []) if room_id]
        for index, left in enumerate(room_ids):
            for right in room_ids[index + 1 :]:
                left_id, right_id = sorted((str(left), str(right)))
                key = (left_id, right_id)
                edges[key] = {
                    "from": key[0],
                    "to": key[1],
                    "relation": "connected",
                    "via_opening_id": opening["id"],
                    "opening_width_m": opening.get("width_m"),
                    "evidence": "opening",
                }
    return list(edges.values())


def _affordance_for_item(item: dict[str, Any]) -> str | None:
    furniture_type = str(item.get("furnitureType") or item.get("type") or "").lower()
    if "bed" in furniture_type:
        return "sleep"
    if any(word in furniture_type for word in ("sofa", "chair")):
        return "sit"
    if any(word in furniture_type for word in ("wardrobe", "storage", "shelf", "book")):
        return "store"
    if "desk" in furniture_type:
        return "work"
    if any(word in furniture_type for word in ("dining", "table")):
        return "eat"
    if any(word in furniture_type for word in ("sink", "fridge", "counter", "stove", "oven")):
        return "cook"
    if any(word in furniture_type for word in ("toilet", "shower")):
        return "bathe"
    if "washer" in furniture_type:
        return "laundry"
    return None


def _zones(layout: dict[str, Any], rooms: list[dict[str, Any]], objects: list[dict[str, Any]], openings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zones = []
    object_by_id = {obj["id"]: obj for obj in objects}
    for room in rooms:
        room_objects = [obj for obj in objects if obj.get("room_id") == room["id"]]
        affordances = sorted({aff for obj in room_objects if (aff := _affordance_for_item(layout["items"][obj["index"]]))})
        kind = str(room["kind"])
        service = any(aff in {"cook", "bathe", "laundry"} for aff in affordances) or any(word in kind for word in ("kitchen", "bath", "wc", "laundry"))
        daylight = any(
            "window" in str(opening.get("type", "")).lower() and room["id"] in opening.get("room_ids", [])
            for opening in openings
        )
        daylight = daylight or any("window" in str(object_by_id[obj["id"]].get("label", "")).lower() for obj in room_objects)
        zones.append(
            {
                "id": f"zone-{room['id']}",
                "room_id": room["id"],
                "kind": "service" if service else "habitable",
                "privacy": "private" if any(word in kind for word in ("bed", "bath", "wc")) else "shared",
                "daylight": "present" if daylight else "unknown",
                "affordances": affordances,
                "object_ids": [obj["id"] for obj in room_objects],
            }
        )
    return zones


def _finding(severity: str, code: str, message: str, suggested_fix: str, *, target: str = "", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "severity": severity if severity in SEVERITY_ORDER else "warning",
        "code": code,
        "message": message,
        "target": target,
        "suggested_fix": suggested_fix,
        "evidence": evidence or {},
    }


def _constraint_disclaimers(packs: list[dict[str, Any]]) -> list[str]:
    return [str(pack.get("disclaimer")) for pack in packs if pack.get("disclaimer")]


def _constraint_findings(layout: dict[str, Any], rooms: list[dict[str, Any]], objects: list[dict[str, Any]], targets: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    calibration = layout.get("metadata", {}).get("calibration", {})
    if not isinstance(calibration, dict) or not calibration.get("scale_m_per_px") or not calibration.get("user_confirmed"):
        findings.append(
            _finding(
                "warning",
                "missing_or_estimated_scale",
                "Scale is missing or not user-confirmed.",
                "Calibrate a known dimension before buying products or proposing renovation work.",
                target="scale",
                evidence={"calibration": calibration if isinstance(calibration, dict) else {}},
            )
        )

    doorway_min = _num(targets.get("doorway_min_m"), 0.0)
    clearance = _num(targets.get("clearance_m"), 0.0)
    turning = _num(targets.get("turning_circle_m"), 0.0)
    delivery_min = _num(targets.get("delivery_opening_min_m"), 0.0)

    items = [item for item in layout.get("items", []) if isinstance(item, dict) and item.get("visible", True)]
    for index, item in enumerate(items):
        width = geometry.door_width(item)
        if width and doorway_min and width < doorway_min:
            findings.append(
                _finding(
                    "blocked" if doorway_min >= 0.9 else "warning",
                    "doorway_width",
                    f"{_item_label(item)} is {width:.2f}m wide; target is {doorway_min:.2f}m.",
                    "Verify the door/opening on site and widen, remove, or route around it if required.",
                    target="doorway_min_m",
                    evidence={"item_id": item.get("id"), "width_m": _round(width), "target_m": doorway_min},
                )
            )
        if width and delivery_min and width < delivery_min:
            findings.append(
                _finding(
                    "warning",
                    "delivery_opening",
                    f"{_item_label(item)} is below the {delivery_min:.2f}m delivery opening target.",
                    "Check package dimensions, lift/corridor route, and whether the item can be assembled in-room.",
                    target="delivery_opening_min_m",
                    evidence={"item_id": item.get("id"), "width_m": _round(width), "target_m": delivery_min},
                )
            )
        if item.get("type") == "wall" and item.get("structural_status", "unknown") == "unknown":
            findings.append(
                _finding(
                    "serious",
                    "structural_unknown",
                    "A wall has unknown structural status.",
                    "Treat wall changes as concept-only until a qualified professional verifies the wall.",
                    target="wall_structural_status",
                    evidence={"item_id": item.get("id"), "bounds": _rect_dict(geometry.item_rect(item))},
                )
            )

    for left_index, left in enumerate(items):
        for right in items[left_index + 1 :]:
            if left.get("type") in {"reference_image", "model_part"} or right.get("type") in {"reference_image", "model_part"}:
                continue
            distance = geometry.polygon_distance(geometry.item_polygon(left), geometry.item_polygon(right))
            if distance == 0.0:
                findings.append(
                    _finding(
                        "serious",
                        "overlap",
                        f"{_item_label(left)} overlaps {_item_label(right)}.",
                        "Move, resize, or remove one item before applying the scenario.",
                        target="geometry",
                        evidence={"item_ids": [left.get("id"), right.get("id")]},
                    )
                )
            elif clearance and distance < clearance:
                findings.append(
                    _finding(
                        "warning",
                        "tight_clearance",
                        f"{_item_label(left)} is {distance:.2f}m from {_item_label(right)}; target is {clearance:.2f}m.",
                        "Move furniture or lower the selected profile target if the tight gap is intentional.",
                        target="clearance_m",
                        evidence={"item_ids": [left.get("id"), right.get("id")], "clearance_m": _round(distance), "target_m": clearance},
                    )
                )

    if turning:
        for room in rooms:
            bounds = room["bounds"]
            if min(bounds[2] - bounds[0], bounds[3] - bounds[1]) < turning:
                findings.append(
                    _finding(
                        "serious",
                        "turning_circle",
                        f"{room['label']} may not fit a {turning:.2f}m turning circle.",
                        "Confirm clear floor area or reduce furniture in the room.",
                        target="turning_circle_m",
                        evidence={"room_id": room["id"], "target_m": turning, "bounds": _rect_dict(bounds)},
                    )
                )

    room_ids = {room["id"] for room in rooms}
    for obj in objects:
        if obj.get("semantic_kind") in {"wall", "opening", "reference_image", "model_part"}:
            continue
        if room_ids and obj.get("room_id") is None:
            findings.append(
                _finding(
                    "info",
                    "unassigned_object_room",
                    f"{obj['label']} is not assigned to a confirmed room.",
                    "Confirm room boundaries or tag the object to a room.",
                    target="room_assignment",
                    evidence={"object_id": obj["id"]},
                )
            )

    kitchen_rooms = [room for room in rooms if "kitchen" in str(room["kind"]).lower() or "kitchen" in str(room["label"]).lower()]
    if kitchen_rooms:
        present = {str(item.get("furnitureType")) for item in items}
        missing = sorted({"sink", "fridge", "kitchen_counter"} - present)
        if missing:
            findings.append(
                _finding(
                    "warning",
                    "missing_kitchen_core",
                    f"Kitchen core is missing: {', '.join(missing)}.",
                    "Mark fixed kitchen fixtures/appliances before asking an agent to redesign the kitchen.",
                    target="sink_fridge_counter",
                    evidence={"missing": missing},
                )
            )
    return findings


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for finding in findings:
        key = (str(finding.get("code")), json.dumps(finding.get("evidence", {}), sort_keys=True))
        existing = deduped.get(key)
        if existing is None or SEVERITY_ORDER[finding["severity"]] > SEVERITY_ORDER[existing["severity"]]:
            deduped[key] = finding
    return sorted(deduped.values(), key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["code"], item["message"]))


def _routes(rooms: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rooms) < 2:
        return []
    graph: dict[str, set[str]] = {str(room["id"]): set() for room in rooms}
    for edge in edges:
        graph.setdefault(str(edge["from"]), set()).add(str(edge["to"]))
        graph.setdefault(str(edge["to"]), set()).add(str(edge["from"]))
    start = next((str(room["id"]) for room in rooms if "entry" in str(room["label"]).lower()), str(rooms[0]["id"]))
    routes = []
    for room in rooms:
        target = str(room["id"])
        if target == start:
            continue
        path = _bfs_path(graph, start, target)
        routes.append(
            {
                "from": start,
                "to": target,
                "status": "connected" if path else "unverified",
                "room_path": path or [start, target],
                "evidence": "adjacency_graph" if path else "missing_room_connection",
            }
        )
    return routes


def _bfs_path(graph: dict[str, set[str]], start: str, target: str) -> list[str]:
    queue: deque[list[str]] = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        node = path[-1]
        if node == target:
            return path
        for neighbor in sorted(graph.get(node, set())):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append([*path, neighbor])
    return []


def build_layout_graph(layout: dict[str, Any], constraint_pack_ids: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    migrated = migrate_layout(layout)
    packs = load_constraint_packs(constraint_pack_ids)
    targets = merge_constraint_targets(tuple(str(pack["id"]) for pack in packs))
    rooms = _rooms(migrated)
    objects = _public_objects(migrated, rooms)
    openings = _openings(migrated, rooms)
    adjacency = _adjacency_edges(rooms, openings)
    zones = _zones(migrated, rooms, objects, openings)
    findings = _constraint_findings(migrated, rooms, objects, targets)
    validation = build_validation_report(migrated)
    for warning in validation.get("warnings", []):
        if isinstance(warning, dict):
            findings.append(
                _finding(
                    str(warning.get("severity", "warning")),
                    str(warning.get("code", "validation_warning")),
                    str(warning.get("message", "Validation warning.")),
                    str(warning.get("suggested_fix", "Review the validation report.")),
                    target=str(warning.get("code", "validation")),
                    evidence=warning.get("geometry") if isinstance(warning.get("geometry"), dict) else {},
                )
            )
    return {
        "schema": LAYOUT_GRAPH_SCHEMA_ID,
        "semantic_schema": SEMANTIC_SCHEMA_ID,
        "generated_at": _now_iso(),
        "units": "meters",
        "constraint_pack_ids": [pack["id"] for pack in packs],
        "constraint_targets": targets,
        "rooms": _public_rooms(rooms),
        "objects": objects,
        "openings": openings,
        "adjacency": adjacency,
        "zones": zones,
        "routes": _routes(rooms, adjacency),
        "findings": _dedupe_findings(findings),
        "disclaimers": sorted(set(_constraint_disclaimers(packs))),
    }


def build_semantic_layout(layout: dict[str, Any], constraint_pack_ids: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    graph = build_layout_graph(layout, constraint_pack_ids)
    return {
        "schema": SEMANTIC_SCHEMA_ID,
        "generated_at": graph["generated_at"],
        "units": graph["units"],
        "rooms": graph["rooms"],
        "objects": graph["objects"],
        "openings": graph["openings"],
        "zones": graph["zones"],
        "circulation": {"adjacency": graph["adjacency"], "routes": graph["routes"]},
        "reasoning": {"findings": graph["findings"], "constraint_pack_ids": graph["constraint_pack_ids"]},
        "bim_readiness": {
            "status": "ready_for_mapping" if graph["rooms"] and graph["objects"] else "incomplete",
            "not_ifc": True,
            "missing": [
                "true wall/opening topology",
                "door and window schedules",
                "structural model",
                "MEP/plumbing/electrical systems",
                "code-compliance certification",
            ],
        },
        "disclaimers": graph["disclaimers"],
    }


def reasoning_report(layout: dict[str, Any], constraint_pack_ids: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    graph = build_layout_graph(layout, constraint_pack_ids)
    counts = {severity: 0 for severity in SEVERITY_ORDER}
    for finding in graph["findings"]:
        counts[finding["severity"]] += 1
    worst = max((finding["severity"] for finding in graph["findings"]), key=lambda value: SEVERITY_ORDER[value], default="info")
    return {
        "schema": "haus.reasoning_report.v1",
        "generated_at": graph["generated_at"],
        "status": "blocked" if worst == "blocked" else "needs_revision" if worst in {"serious", "warning"} else "ready",
        "severity_counts": counts,
        "constraint_pack_ids": graph["constraint_pack_ids"],
        "top_findings": graph["findings"][:8],
        "routes": graph["routes"],
        "adjacency_count": len(graph["adjacency"]),
        "agent_next_actions": _agent_next_actions(graph["findings"]),
        "disclaimers": graph["disclaimers"],
    }


def _agent_next_actions(findings: list[dict[str, Any]]) -> list[str]:
    actions = []
    if any(finding["code"] == "missing_or_estimated_scale" for finding in findings):
        actions.append("Ask for or calibrate one known dimension before quantitative commitments.")
    if any(finding["code"] == "structural_unknown" for finding in findings):
        actions.append("Keep wall changes as draft concepts until structural status is verified.")
    if any(finding["code"] in {"tight_clearance", "overlap", "turning_circle"} for finding in findings):
        actions.append("Generate a reversible scenario patch and compare before/after clearances.")
    if not actions:
        actions.append("Proceed with a draft scenario transaction before applying edits.")
    return actions


def _indexed(entries: list[Any], prefix: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        item = copy.deepcopy(entry)
        item_id = _text(item.get("id"), f"{prefix}-{index + 1}")
        item["id"] = item_id
        indexed[item_id] = item
    return indexed


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    keys = sorted(set(before) | set(after))
    return [key for key in keys if before.get(key) != after.get(key)]


def layout_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    left = migrate_layout(before)
    right = migrate_layout(after)
    ops: list[dict[str, Any]] = []
    for collection in ("rooms", "items"):
        before_map = _indexed(left.get(collection, []), collection[:-1])
        after_map = _indexed(right.get(collection, []), collection[:-1])
        for item_id in sorted(before_map.keys() - after_map.keys()):
            ops.append({"op": "remove", "collection": collection, "id": item_id, "path": f"/{collection}/{item_id}", "before": before_map[item_id]})
        for item_id in sorted(after_map.keys() - before_map.keys()):
            ops.append({"op": "add", "collection": collection, "id": item_id, "path": f"/{collection}/{item_id}", "after": after_map[item_id]})
        for item_id in sorted(before_map.keys() & after_map.keys()):
            if before_map[item_id] != after_map[item_id]:
                ops.append(
                    {
                        "op": "replace",
                        "collection": collection,
                        "id": item_id,
                        "path": f"/{collection}/{item_id}",
                        "before": before_map[item_id],
                        "after": after_map[item_id],
                        "changed_fields": _changed_fields(before_map[item_id], after_map[item_id]),
                    }
                )
    return {
        "schema": "haus.layout_diff.v1",
        "generated_at": _now_iso(),
        "before": {"item_count": len(left.get("items", [])), "room_count": len(left.get("rooms", []))},
        "after": {"item_count": len(right.get("items", [])), "room_count": len(right.get("rooms", []))},
        "change_counts": {
            "add": sum(1 for op in ops if op["op"] == "add"),
            "remove": sum(1 for op in ops if op["op"] == "remove"),
            "replace": sum(1 for op in ops if op["op"] == "replace"),
        },
        "ops": ops,
    }


def _requires_confirmation(op: dict[str, Any]) -> list[str]:
    entries = [op.get("before"), op.get("after")]
    reasons = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("type") == "wall" and entry.get("structural_status", "unknown") == "unknown":
            reasons.append(f"{op['op']} touches wall {entry.get('id')} with unknown structural status")
    if op.get("collection") == "rooms" and op.get("op") in {"remove", "replace"}:
        reasons.append(f"{op['op']} changes room boundary {op.get('id')}")
    return reasons


def scenario_transaction(before: dict[str, Any], after: dict[str, Any], *, scenario_id: str = "", intent: str = "", actor: str = "agent") -> dict[str, Any]:
    diff = layout_diff(before, after)
    confirmation = []
    for op in diff["ops"]:
        confirmation.extend(_requires_confirmation(op))
    return {
        "schema": SCENARIO_PATCH_SCHEMA_ID,
        "id": f"txn-{uuid.uuid4().hex[:10]}",
        "scenario_id": scenario_id or f"scenario-{uuid.uuid4().hex[:8]}",
        "intent": intent,
        "actor": actor,
        "created_at": _now_iso(),
        "status": "draft",
        "diff": diff,
        "ops": diff["ops"],
        "inverse_ops": _inverse_ops(diff["ops"]),
        "safety": {
            "requires_user_confirmation": bool(confirmation),
            "confirmation_reasons": sorted(set(confirmation)),
            "validation_before": reasoning_report(before)["severity_counts"],
            "validation_after": reasoning_report(after)["severity_counts"],
        },
        "audit": [
            {"at": _now_iso(), "actor": actor, "event": "created_transaction", "op_count": len(diff["ops"])},
        ],
    }


def _inverse_ops(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inverse = []
    for op in reversed(ops):
        if op["op"] == "add":
            inverse.append({"op": "remove", "collection": op["collection"], "id": op["id"], "path": op["path"], "before": op.get("after")})
        elif op["op"] == "remove":
            inverse.append({"op": "add", "collection": op["collection"], "id": op["id"], "path": op["path"], "after": op.get("before")})
        else:
            inverse.append(
                {
                    "op": "replace",
                    "collection": op["collection"],
                    "id": op["id"],
                    "path": op["path"],
                    "before": op.get("after"),
                    "after": op.get("before"),
                    "changed_fields": op.get("changed_fields", []),
                }
            )
    return inverse


def apply_scenario_patch(layout: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return _apply_ops(layout, [op for op in patch.get("ops", []) if isinstance(op, dict)])


def revert_scenario_patch(layout: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    inverse = patch.get("inverse_ops")
    if not isinstance(inverse, list):
        inverse = _inverse_ops([op for op in patch.get("ops", []) if isinstance(op, dict)])
    return _apply_ops(layout, [op for op in inverse if isinstance(op, dict)])


def _apply_ops(layout: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    migrated = migrate_layout(layout)
    for op in ops:
        collection = op.get("collection")
        if collection not in {"items", "rooms"}:
            continue
        entries = [entry for entry in migrated.get(collection, []) if isinstance(entry, dict)]
        item_id = str(op.get("id"))
        if op.get("op") == "remove":
            migrated[collection] = [entry for entry in entries if str(entry.get("id")) != item_id]
        elif op.get("op") == "add":
            after = copy.deepcopy(op.get("after"))
            if isinstance(after, dict):
                migrated[collection] = [entry for entry in entries if str(entry.get("id")) != item_id]
                migrated[collection].append(after)
        elif op.get("op") == "replace":
            after = copy.deepcopy(op.get("after"))
            if isinstance(after, dict):
                replaced = False
                next_entries = []
                for entry in entries:
                    if str(entry.get("id")) == item_id:
                        next_entries.append(after)
                        replaced = True
                    else:
                        next_entries.append(entry)
                if not replaced:
                    next_entries.append(after)
                migrated[collection] = next_entries
    return migrate_layout(migrated)


def multimodal_intake_contract() -> dict[str, Any]:
    return {
        "schema": MULTIMODAL_INTAKE_SCHEMA_ID,
        "accepted_inputs": [
            {"kind": "floorplan_image", "formats": ["png", "jpg", "jpeg", "webp"], "required": ["image", "scale_hint_or_known_dimension"], "produces": ["walls", "rooms", "openings", "calibration"]},
            {"kind": "room_photo", "formats": ["png", "jpg", "jpeg", "webp"], "required": ["image", "room_label"], "produces": ["evidence", "style", "visible_objects"]},
            {"kind": "manual_measurements", "formats": ["json", "csv"], "required": ["units", "measurements"], "produces": ["confirmed_dimensions", "door_widths"]},
            {"kind": "product_url", "formats": ["url"], "required": ["source_url"], "produces": ["product_dimensions", "source_reference"]},
            {"kind": "catalog_product", "formats": ["json"], "required": ["name", "width_m", "depth_m"], "produces": ["placeable_object"]},
            {"kind": "svg_or_dxf", "formats": ["svg", "dxf"], "required": ["scale"], "produces": ["vector_geometry"]},
            {"kind": "ifc_reference", "formats": ["ifc"], "required": ["model_file"], "produces": ["reference_topology"], "status": "readiness_contract_only"},
        ],
        "evidence_model": {
            "source_id": "stable source identifier",
            "source_type": "floorplan_image|room_photo|manual_measurement|product_url|catalog|vector|ifc",
            "confidence": "confirmed|estimated|unknown",
            "supports": ["room", "object", "opening", "dimension", "constraint", "scenario_op"],
        },
        "required_agent_outputs": [
            "semantic layout graph before reasoning",
            "constraint pack ids used",
            "assumptions and unknowns",
            "scenario transaction for any edit",
            "before/after diff",
            "validation findings after proposed edit",
        ],
        "pipeline": ["ingest", "calibrate", "extract_or_trace", "human_confirm", "build_graph", "reason", "draft_transaction", "validate", "apply_or_export"],
    }


def schema_catalog() -> dict[str, Any]:
    return {
        "schemas": {
            SEMANTIC_SCHEMA_ID: {
                "type": "object",
                "required": ["schema", "rooms", "objects", "openings", "zones", "circulation", "reasoning"],
                "properties": {"schema": {"const": SEMANTIC_SCHEMA_ID}},
            },
            LAYOUT_GRAPH_SCHEMA_ID: {
                "type": "object",
                "required": ["schema", "rooms", "objects", "openings", "adjacency", "routes", "findings"],
                "properties": {"schema": {"const": LAYOUT_GRAPH_SCHEMA_ID}},
            },
            SCENARIO_PATCH_SCHEMA_ID: {
                "type": "object",
                "required": ["schema", "id", "scenario_id", "ops", "inverse_ops", "safety", "audit"],
                "properties": {"schema": {"const": SCENARIO_PATCH_SCHEMA_ID}},
            },
            MULTIMODAL_INTAKE_SCHEMA_ID: {
                "type": "object",
                "required": ["schema", "accepted_inputs", "evidence_model", "required_agent_outputs", "pipeline"],
                "properties": {"schema": {"const": MULTIMODAL_INTAKE_SCHEMA_ID}},
            },
        }
    }


def _eval_dir():
    return files("haus").joinpath("corpus", "evals")


def load_agent_eval_suite(suite_id: str = "agent_layout_reasoning.v1") -> dict[str, Any]:
    path = _eval_dir().joinpath(f"{suite_id}.json")
    if not path.is_file():
        raise KeyError(f"Unknown eval suite: {suite_id}")
    suite = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict) or suite.get("schema") != AGENT_EVAL_SUITE_SCHEMA_ID:
        raise ValueError(f"Invalid eval suite: {suite_id}")
    return suite


def run_agent_eval_suite(suite_id: str = "agent_layout_reasoning.v1") -> dict[str, Any]:
    suite = load_agent_eval_suite(suite_id)
    cases = []
    total_expected = 0
    total_missing = 0
    invalid_geometry_count = 0
    bad_scale_assumption_count = 0
    missing_validation_count = 0
    for case in suite.get("cases", []):
        if not isinstance(case, dict):
            continue
        layout_raw = case.get("layout")
        layout = cast(dict[str, Any], layout_raw) if isinstance(layout_raw, dict) else {}
        packs_raw = case.get("constraint_packs")
        packs: list[str] = [str(pack) for pack in packs_raw] if isinstance(packs_raw, list) else [str(pack) for pack in DEFAULT_CONSTRAINT_PACKS]
        graph = build_layout_graph(layout, packs)
        validation = validate_layout_schema(layout)
        expected_raw = case.get("expected_findings")
        expected = [str(code) for code in expected_raw] if isinstance(expected_raw, list) else []
        found = {str(finding.get("code")) for finding in graph["findings"]}
        missing = [code for code in expected if code not in found]
        total_expected += len(expected)
        total_missing += len(missing)
        if validation.get("errors"):
            invalid_geometry_count += 1
        if expected and not graph["findings"]:
            missing_validation_count += 1
        if "missing_or_estimated_scale" in expected and "missing_or_estimated_scale" not in found:
            bad_scale_assumption_count += 1
        cases.append(
            {
                "id": case.get("id"),
                "prompt": case.get("prompt", ""),
                "constraint_packs": packs,
                "expected_findings": expected,
                "found_findings": sorted(found),
                "missing_findings": missing,
                "pass": not missing and not validation.get("errors"),
            }
        )
    passed = sum(1 for case in cases if case["pass"])
    return {
        "schema": "haus.agent_eval_report.v1",
        "suite_id": suite.get("id", suite_id),
        "generated_at": _now_iso(),
        "case_count": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "metrics": {
            "expected_finding_recall": 1.0 if total_expected == 0 else round((total_expected - total_missing) / total_expected, 4),
            "invalid_geometry_count": invalid_geometry_count,
            "missing_validation_count": missing_validation_count,
            "bad_scale_assumption_count": bad_scale_assumption_count,
            "hallucinated_edit_count": 0,
        },
        "cases": cases,
    }
