"""Compliance Agent v0 — emits structured findings per SPEC-HTTP-CASE.md sections 2.4 and 5.

Two rules in scope:
- rule_structural_wall_protected: diffs current items[] against the baseline snapshot;
  fires on removed, moved, rotated, or resized structural/shelter walls.
- rule_walkway_accessibility: scores walkways between adjacent rooms using a corridor
  polygon and item-blocking distance. (SPEC 5.2; backup failure mode.)
"""
from __future__ import annotations

import math
from typing import Any

# Polygon helpers live in mcp_server.py as battle-tested private utilities. Importing
# them couples to FastMCP instance creation at import time (one-time cost; acceptable
# for v0). Refactoring to a shared geometry module is out of scope here.
from ..mcp_server import _item_polygon, _distance_point_to_polygon


SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"

WALKWAY_MIN_WIDTH_M = 0.9
WALKWAY_SCORE_THRESHOLD_ERROR = 0.3
WALKWAY_SCORE_THRESHOLD_WARN = 0.5
PROTECTED_WALL_POSITION_TOLERANCE_M = 0.05
PROTECTED_WALL_GEOMETRY_TOLERANCE_M = 0.05
PROTECTED_WALL_ROTATION_TOLERANCE_RAD = math.radians(1.0)


def rule_structural_wall_protected(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Fires for protected baseline walls that were removed or geometrically changed.

    Identity by `name` per SPEC section 2.4 (element_name is canonical, element_index is hint).
    Newly-added walls with hdb_type=None fail open by virtue of not being in the baseline.
    """
    baseline = case.get("_baseline_protected_walls", [])
    if not baseline:
        return []

    current_walls_by_name: dict[str, dict[str, Any]] = {}
    current_indexes_by_name: dict[str, int] = {}
    for idx, it in enumerate(case.get("items", [])):
        if it.get("type") != "wall":
            continue
        name = it.get("name")
        if not name:
            continue
        current_walls_by_name[name] = it
        current_indexes_by_name[name] = idx

    findings: list[dict[str, Any]] = []
    for protected in baseline:
        name = protected["name"]
        current = current_walls_by_name.get(name)
        if current is None:
            findings.append(_protected_wall_finding(
                protected,
                current=None,
                element_index=None,
                action="do_not_remove",
                change_type="remove",
                reason_action="remove",
            ))
            continue

        element_index = current_indexes_by_name[name]
        pos_delta = _max_abs_delta(protected.get("pos"), current.get("pos"))
        rot_delta = _rotation_delta(protected.get("rot"), current.get("rot"))
        geo_delta = _max_abs_delta(protected.get("geo"), current.get("geo"))
        if pos_delta > PROTECTED_WALL_POSITION_TOLERANCE_M or rot_delta > PROTECTED_WALL_ROTATION_TOLERANCE_RAD:
            change_type = "rotate" if pos_delta <= PROTECTED_WALL_POSITION_TOLERANCE_M else "move"
            findings.append(_protected_wall_finding(
                protected,
                current=current,
                element_index=element_index,
                action="do_not_move",
                change_type=change_type,
                reason_action="move or rotate",
            ))
        if geo_delta > PROTECTED_WALL_GEOMETRY_TOLERANCE_M:
            findings.append(_protected_wall_finding(
                protected,
                current=current,
                element_index=element_index,
                action="do_not_resize",
                change_type="resize",
                reason_action="resize",
            ))
    return findings


def _protected_wall_finding(
    protected: dict[str, Any],
    *,
    current: dict[str, Any] | None,
    element_index: int | None,
    action: str,
    change_type: str,
    reason_action: str,
) -> dict[str, Any]:
    name = str(protected["name"])
    hdb_type = str(protected["hdb_type"])
    wall_kind = "load-bearing structural" if hdb_type == "structural" else "load-bearing shelter"
    coords: dict[str, Any] = {
        "pos": list(protected.get("pos", [])),
        "rot": protected.get("rot", 0.0),
        "geo": list(protected.get("geo", [])),
    }
    if current is not None:
        coords["current"] = {
            "pos": list(current.get("pos", [])),
            "rot": current.get("rot", 0.0),
            "geo": list(current.get("geo", [])),
        }
    return {
        "rule_id": "structural_wall_protected",
        "severity": SEVERITY_ERROR,
        "element_index": element_index,
        "element_name": name,
        "coords": coords,
        "reason": (
            f"Cannot {reason_action} {hdb_type} wall '{name}' "
            f"(HDB {wall_kind} wall; protected under HDB renovation rules)."
        ),
        "machine_hint": {
            "action": action,
            "constraint": "structural_wall",
            "hdb_type": hdb_type,
            "element_name": name,
            "change_type": change_type,
            "alternative": "reshape using partition walls (hdb_type=partition) instead",
        },
    }


def _float_list(value: Any) -> list[float] | None:
    if not isinstance(value, list):
        return None
    out: list[float] = []
    for raw in value:
        try:
            out.append(float(raw))
        except (TypeError, ValueError):
            return None
    return out


def _max_abs_delta(a: Any, b: Any) -> float:
    aa = _float_list(a)
    bb = _float_list(b)
    if aa is None or bb is None or len(aa) != len(bb):
        return float("inf")
    if not aa:
        return 0.0
    return max(abs(x - y) for x, y in zip(aa, bb))


def _rotation_delta(a: Any, b: Any) -> float:
    try:
        aa = float(a or 0.0)
        bb = float(b or 0.0)
    except (TypeError, ValueError):
        return float("inf")
    raw = abs(aa - bb) % (math.pi * 2.0)
    return min(raw, math.pi * 2.0 - raw)


def _room_center(room: dict[str, Any]) -> tuple[float, float] | None:
    b = room.get("bounds")
    if not isinstance(b, dict):
        return None
    try:
        cx = (float(b["x_min"]) + float(b["x_max"])) / 2.0
        cz = (float(b["z_min"]) + float(b["z_max"])) / 2.0
    except (KeyError, ValueError, TypeError):
        return None
    return cx, cz


def _rooms_are_adjacent(a: dict[str, Any], b: dict[str, Any], tol: float = 0.3) -> bool:
    """Two rooms are adjacent if their axis-aligned bounds touch or nearly touch."""
    ba, bb = a.get("bounds"), b.get("bounds")
    if not isinstance(ba, dict) or not isinstance(bb, dict):
        return False
    try:
        ax1, ax2 = float(ba["x_min"]), float(ba["x_max"])
        az1, az2 = float(ba["z_min"]), float(ba["z_max"])
        bx1, bx2 = float(bb["x_min"]), float(bb["x_max"])
        bz1, bz2 = float(bb["z_min"]), float(bb["z_max"])
    except (KeyError, ValueError, TypeError):
        return False
    # rectangles overlap or touch (within tol) on both axes
    x_overlap = (ax1 - tol) <= bx2 and (bx1 - tol) <= ax2
    z_overlap = (az1 - tol) <= bz2 and (bz1 - tol) <= az2
    return x_overlap and z_overlap


def _score_walkway_corridor(
    items: list[dict[str, Any]],
    x1: float,
    z1: float,
    x2: float,
    z2: float,
    min_width: float,
) -> tuple[float, list[dict[str, Any]]]:
    """Sample the corridor between two points; return (score in [0,1], blockers)."""
    dx = x2 - x1
    dz = z2 - z1
    length = math.hypot(dx, dz)
    if length < 0.01:
        return 1.0, []

    polygons: list[tuple[int, dict[str, Any], list[tuple[float, float]]]] = []
    for i, item in enumerate(items):
        if item.get("type") == "wall":
            continue  # the walkway between adjacent rooms passes through their shared wall(s)
        if not item.get("visible", True):
            continue
        polygons.append((i, item, _item_polygon(item)))

    steps = max(4, int(length / 0.25))
    narrowest = float("inf")
    blockers_seen: dict[int, dict[str, Any]] = {}
    for s in range(steps + 1):
        t = s / steps
        px = x1 + dx * t
        pz = z1 + dz * t
        for i, item, poly in polygons:
            d = _distance_point_to_polygon((px, pz), poly)
            if d < narrowest:
                narrowest = d
            if d < min_width / 2.0:
                blockers_seen[i] = item

    if narrowest == float("inf"):
        return 1.0, []
    score = max(0.0, min(1.0, narrowest / (min_width / 2.0)))
    blockers = [{"index": i, "name": it.get("name") or it.get("type") or "<unnamed>"} for i, it in blockers_seen.items()]
    return round(score, 3), blockers


def rule_walkway_accessibility(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Score walkways between each pair of adjacent rooms; emit findings below threshold.

    Walls are excluded from blocker candidates (the walkway is *expected* to cross at
    least one wall plane — that is the doorway). Furniture and other placed items count.
    """
    rooms = case.get("rooms", [])
    items = case.get("items", [])
    if len(rooms) < 2:
        return []

    findings: list[dict[str, Any]] = []
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            ra, rb = rooms[i], rooms[j]
            if not _rooms_are_adjacent(ra, rb):
                continue
            ca = _room_center(ra)
            cb = _room_center(rb)
            if ca is None or cb is None:
                continue
            score, blockers = _score_walkway_corridor(
                items, ca[0], ca[1], cb[0], cb[1], WALKWAY_MIN_WIDTH_M,
            )
            if score >= WALKWAY_SCORE_THRESHOLD_WARN:
                continue
            severity = SEVERITY_ERROR if score < WALKWAY_SCORE_THRESHOLD_ERROR else SEVERITY_WARN
            blocker_summary = (
                ", ".join(b["name"] for b in blockers[:3]) + (f" (+{len(blockers) - 3} more)" if len(blockers) > 3 else "")
            ) if blockers else "no specific blocker identified"
            primary = blockers[0] if blockers else None
            findings.append({
                "rule_id": "walkway_accessibility",
                "severity": severity,
                "element_index": primary["index"] if primary else None,
                "element_name": primary["name"] if primary else None,
                "coords": {
                    "from_room": ra.get("id"),
                    "to_room": rb.get("id"),
                    "from_xz": list(ca),
                    "to_xz": list(cb),
                },
                "reason": (
                    f"Walkway between '{ra.get('label') or ra.get('id')}' and "
                    f"'{rb.get('label') or rb.get('id')}' scores {score} "
                    f"(min width {WALKWAY_MIN_WIDTH_M}m); blockers: {blocker_summary}."
                ),
                "machine_hint": {
                    "action": "do_not_block_walkway",
                    "constraint": "min_walkway_width_m",
                    "min_walkway_width_m": WALKWAY_MIN_WIDTH_M,
                    "from_room": ra.get("id"),
                    "to_room": rb.get("id"),
                    "blocker_indexes": [b["index"] for b in blockers],
                },
            })
    return findings


_RULES = (rule_structural_wall_protected, rule_walkway_accessibility)


def run_compliance(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Run all v0 rules; return concatenated findings.

    Per SPEC section 4.2 POST /case/{id}/compliance: idempotent (pure read over current
    items + rules; same input -> same findings). This is what makes findings safely
    replayable into /revise.
    """
    out: list[dict[str, Any]] = []
    for rule in _RULES:
        out.extend(rule(case))
    return out


def has_errors(findings: list[dict[str, Any]]) -> bool:
    """SPEC section 2.4: only severity=='error' triggers the revise loop / escalation."""
    return any(f.get("severity") == SEVERITY_ERROR for f in findings)
