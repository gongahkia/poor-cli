from __future__ import annotations

import copy
import html
import json
import math
import re
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LAYOUT_SCHEMA_ID = "haus.layout.v2"
PROJECT_SCHEMA_ID = "haus.project.v1"
CURRENT_LAYOUT_SCHEMA_VERSION = 2
CURRENT_PROJECT_SCHEMA_VERSION = 1
PROJECT_STATUSES = ("draft", "applied", "revised", "exported", "imported")
VALIDATION_SEVERITIES = ("info", "warning", "serious", "blocked")

JOURNEYS = {
    "renovation": "Renovation Concept Pack",
    "accessibility": "Accessibility Checker",
    "furniture_fit": "Furniture Fit Planner",
    "designer": "Designer Pre-Sales Assistant",
    "blank": "Blank Project",
}

PRODUCT_SAFE_DISCLAIMER = (
    "Haus is a concept planning and spatial validation workbench. It is not BIM "
    "authoring, code certification, medical advice, occupational therapy "
    "assessment, contractor-ready documentation, or a substitute for professional "
    "site verification."
)

ACCESSIBILITY_DISCLAIMER = (
    "Accessibility checks are planning guidance only. They are not ADA "
    "certification, medical advice, or an occupational therapy assessment."
)

RENOVATION_DISCLAIMER = (
    "Renovation wall, opening, plumbing, electrical, stair, and structural ideas "
    "are concept-only until verified by qualified professionals on site."
)

FIXED_ELEMENT_TYPES = {
    "structural_wall",
    "partition_wall",
    "column",
    "household_shelter",
    "plumbing_stack",
    "cabinet",
    "appliance",
    "fixture",
}

ACCESSIBILITY_PROFILES: dict[str, dict[str, Any]] = {
    "general_aging_ready": {
        "label": "General aging-ready",
        "doorway_min_m": 0.80,
        "path_min_m": 0.85,
        "turning_circle_m": 1.20,
        "source_type": "practical_guidance",
    },
    "cane": {
        "label": "Cane",
        "doorway_min_m": 0.80,
        "path_min_m": 0.85,
        "turning_circle_m": 1.20,
        "source_type": "practical_guidance",
    },
    "walker": {
        "label": "Walker",
        "doorway_min_m": 0.86,
        "path_min_m": 0.90,
        "turning_circle_m": 1.35,
        "source_type": "practical_guidance",
    },
    "wheelchair": {
        "label": "Wheelchair",
        "doorway_min_m": 0.915,
        "path_min_m": 0.915,
        "turning_circle_m": 1.50,
        "source_type": "formal_code_inspired_screening",
    },
    "caregiver_assisted": {
        "label": "Caregiver-assisted",
        "doorway_min_m": 0.915,
        "path_min_m": 1.05,
        "turning_circle_m": 1.65,
        "source_type": "practical_guidance",
    },
    "low_vision": {
        "label": "Low-vision",
        "doorway_min_m": 0.80,
        "path_min_m": 0.90,
        "turning_circle_m": 1.20,
        "source_type": "practical_guidance",
    },
    "fall_risk_bathroom": {
        "label": "Fall-risk bathroom",
        "doorway_min_m": 0.86,
        "path_min_m": 0.90,
        "turning_circle_m": 1.35,
        "source_type": "practical_guidance",
    },
}

COMMON_SMALL_APARTMENT_PRODUCTS: list[dict[str, Any]] = [
    {
        "id": "fixture-queen-bed",
        "name": "Queen bed",
        "category": "bed",
        "width_m": 1.52,
        "depth_m": 2.03,
        "height_m": 0.60,
        "clearance_m": 0.60,
    },
    {
        "id": "fixture-single-bed",
        "name": "Single bed",
        "category": "bed",
        "width_m": 0.91,
        "depth_m": 1.91,
        "height_m": 0.55,
        "clearance_m": 0.55,
    },
    {
        "id": "fixture-sofa",
        "name": "Three-seat sofa",
        "category": "sofa",
        "width_m": 2.10,
        "depth_m": 0.90,
        "height_m": 0.85,
        "clearance_m": 0.60,
    },
    {
        "id": "fixture-desk",
        "name": "Work desk",
        "category": "desk",
        "width_m": 1.20,
        "depth_m": 0.60,
        "height_m": 0.75,
        "clearance_m": 0.75,
    },
    {
        "id": "fixture-wardrobe",
        "name": "Wardrobe",
        "category": "wardrobe",
        "width_m": 1.20,
        "depth_m": 0.60,
        "height_m": 2.00,
        "clearance_m": 0.80,
    },
    {
        "id": "fixture-dining-table",
        "name": "Dining table",
        "category": "table",
        "width_m": 1.40,
        "depth_m": 0.80,
        "height_m": 0.75,
        "clearance_m": 0.90,
    },
    {
        "id": "fixture-storage-shelf",
        "name": "Storage shelf",
        "category": "storage",
        "width_m": 0.80,
        "depth_m": 0.35,
        "height_m": 1.80,
        "clearance_m": 0.45,
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).strip()
    return text or fallback


def _num(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return fallback
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(parsed):
        return fallback
    return parsed


def _item_dimensions(item: dict[str, Any]) -> tuple[float, float, float]:
    geo = item.get("geo")
    if isinstance(geo, list) and len(geo) >= 3:
        return (
            max(0.01, _num(geo[0], 1.0)),
            max(0.01, _num(geo[1], 1.0)),
            max(0.01, _num(geo[2], 1.0)),
        )
    return (
        max(0.01, _num(item.get("width_m"), 1.0)),
        max(0.01, _num(item.get("height_m"), 1.0)),
        max(0.01, _num(item.get("depth_m"), 1.0)),
    )


def _item_center(item: dict[str, Any]) -> tuple[float, float]:
    pos = item.get("pos")
    if isinstance(pos, list) and len(pos) >= 3:
        return (_num(pos[0]), _num(pos[2]))
    return (_num(item.get("x")), _num(item.get("z")))


def item_rect(item: dict[str, Any], padding: float = 0.0) -> tuple[float, float, float, float]:
    width, _, depth = _item_dimensions(item)
    x, z = _item_center(item)
    return (
        x - width / 2 - padding,
        z - depth / 2 - padding,
        x + width / 2 + padding,
        z + depth / 2 + padding,
    )


def _rect_intersects(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _rect_gap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dz = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dz)


def _layout_bounds(layout: dict[str, Any]) -> tuple[float, float, float, float]:
    rects = [item_rect(item) for item in layout.get("items", []) if isinstance(item, dict)]
    for room in layout.get("rooms", []):
        bounds = room.get("bounds") if isinstance(room, dict) else None
        if isinstance(bounds, dict):
            rects.append(
                (
                    _num(bounds.get("x_min")),
                    _num(bounds.get("z_min")),
                    _num(bounds.get("x_max")),
                    _num(bounds.get("z_max")),
                )
            )
    if not rects:
        return (-2.0, -2.0, 2.0, 2.0)
    return (
        min(rect[0] for rect in rects),
        min(rect[1] for rect in rects),
        max(rect[2] for rect in rects),
        max(rect[3] for rect in rects),
    )


def _room_label(room: dict[str, Any]) -> str:
    return _text(room.get("label") or room.get("name") or room.get("id"), "Unassigned")


def migrate_layout(raw: Any) -> dict[str, Any]:
    layout = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    layout.setdefault("version", 1)
    layout["schema"] = LAYOUT_SCHEMA_ID
    layout["layout_schema_version"] = CURRENT_LAYOUT_SCHEMA_VERSION
    layout.setdefault("items", [])
    layout.setdefault("rooms", [])
    layout.setdefault("metadata", {})
    layout.setdefault("assumptions", [])
    layout.setdefault("validation_reports", [])
    layout.setdefault("exports", [])
    layout.setdefault("layout_versions", [])
    layout.setdefault("scenarios", [])

    if not isinstance(layout["items"], list):
        layout["items"] = []
    if not isinstance(layout["rooms"], list):
        layout["rooms"] = []
    if not isinstance(layout["metadata"], dict):
        layout["metadata"] = {}

    metadata = layout["metadata"]
    calibration = metadata.get("calibration")
    if not isinstance(calibration, dict):
        scale = metadata.get("scale_m_per_px")
        calibration = {
            "scale_m_per_px": scale,
            "confidence": "estimated" if scale else "unknown",
            "source": "legacy_metadata" if scale else "missing",
            "user_confirmed": False,
        }
        metadata["calibration"] = calibration
    calibration.setdefault("confidence", "confirmed" if calibration.get("user_confirmed") else "estimated")
    metadata.setdefault("units", "m")

    for index, item in enumerate(layout["items"]):
        if not isinstance(item, dict):
            continue
        item.setdefault("id", f"item-{index + 1}")
        item.setdefault("confidence", "estimated")
        if item.get("type") == "wall":
            item.setdefault("structural_status", "unknown")
            item.setdefault("structural_confidence", "unknown")
        if item.get("type") in {"door", "opening"} or item.get("room_capture_opening"):
            item.setdefault("confidence", "estimated")

    for index, room in enumerate(layout["rooms"]):
        if not isinstance(room, dict):
            continue
        room.setdefault("id", f"room-{index + 1}")
        room.setdefault("label", _room_label(room))
        room.setdefault("kind", "room")
        room.setdefault("confidence", "estimated")
        room.setdefault("locked", False)
        if isinstance(room.get("openings"), list):
            for opening_index, opening in enumerate(room["openings"]):
                if isinstance(opening, dict):
                    opening.setdefault("id", f"{room['id']}-opening-{opening_index + 1}")
                    opening.setdefault("confidence", "estimated")

    return layout


def validate_layout_schema(raw: Any) -> dict[str, Any]:
    layout = migrate_layout(raw)
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(raw, dict):
        errors.append("Layout must be a JSON object.")
    if not isinstance(layout.get("items"), list):
        errors.append("Layout items must be an array.")
    for index, item in enumerate(layout.get("items", [])):
        if not isinstance(item, dict):
            errors.append(f"Item {index} must be an object.")
            continue
        geo = item.get("geo")
        pos = item.get("pos")
        if not isinstance(geo, list) or len(geo) < 3:
            errors.append(f"Item {index} is missing geo [width,height,depth].")
        if not isinstance(pos, list) or len(pos) < 3:
            errors.append(f"Item {index} is missing pos [x,y,z].")
        if item.get("type") == "wall" and item.get("structural_status") == "unknown":
            warnings.append(f"Wall {index} has unknown structural status.")

    calibration = layout.get("metadata", {}).get("calibration", {})
    if not calibration.get("scale_m_per_px"):
        warnings.append("Scale is missing or estimated.")

    return {
        "ok": not errors,
        "schema": LAYOUT_SCHEMA_ID,
        "layout": layout,
        "errors": errors,
        "warnings": warnings,
    }


def new_project(title: str = "Untitled Haus Project", journey: str = "blank", layout: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_journey = journey if journey in JOURNEYS else "blank"
    migrated = migrate_layout(layout or {"version": 1, "items": []})
    project = {
        "schema": PROJECT_SCHEMA_ID,
        "project_schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "id": f"project-{uuid.uuid4().hex[:10]}",
        "title": _text(title, "Untitled Haus Project"),
        "journey": clean_journey,
        "journey_label": JOURNEYS[clean_journey],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "source_file": migrated.get("metadata", {}).get("source_filename"),
        "calibration": migrated.get("metadata", {}).get("calibration", {}),
        "rooms": migrated.get("rooms", []),
        "layout": migrated,
        "layout_versions": [],
        "assumptions": [],
        "unknowns": [],
        "validation_reports": [],
        "exports": [],
        "scenarios": [],
        "intake": {
            "dwelling_type": "",
            "country_or_region": "",
            "units": "m",
            "household_profile": "",
            "budget_range": "",
            "timeline": "",
            "main_goal": "",
        },
        "chat_context": {"journey": clean_journey, "journey_label": JOURNEYS[clean_journey]},
    }
    capture_project_version(project, "draft", migrated, note="Initial draft")
    base = create_scenario("Base", clean_journey, migrated, status="draft")
    project["scenarios"].append(base)
    return project


def capture_project_version(
    project: dict[str, Any], status: str, layout: dict[str, Any], note: str = ""
) -> dict[str, Any]:
    clean_status = status if status in PROJECT_STATUSES else "draft"
    migrated = migrate_layout(layout)
    entry = {
        "id": f"version-{uuid.uuid4().hex[:8]}",
        "status": clean_status,
        "created_at": _now_iso(),
        "note": note,
        "item_count": len(migrated.get("items", [])),
        "room_count": len(migrated.get("rooms", [])),
        "layout": migrated,
    }
    project.setdefault("layout_versions", []).append(entry)
    project["updated_at"] = _now_iso()
    return entry


def create_scenario(
    name: str,
    journey: str,
    layout: dict[str, Any],
    *,
    status: str = "draft",
    parent_scenario_id: str | None = None,
) -> dict[str, Any]:
    migrated = migrate_layout(layout)
    scores = scenario_scores(migrated, journey)
    return {
        "id": f"scenario-{uuid.uuid4().hex[:8]}",
        "name": _text(name, "Scenario"),
        "journey": journey if journey in JOURNEYS else "blank",
        "status": status,
        "created_at": _now_iso(),
        "applied_at": _now_iso() if status == "applied" else None,
        "parent_scenario_id": parent_scenario_id,
        "layout": migrated,
        "score": scores,
        "warnings": build_validation_report(migrated, journey=journey)["warnings"],
    }


def duplicate_scenario(scenario: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    clone = copy.deepcopy(scenario)
    clone["id"] = f"scenario-{uuid.uuid4().hex[:8]}"
    clone["name"] = name or f"{scenario.get('name', 'Scenario')} copy"
    clone["status"] = "draft"
    clone["created_at"] = _now_iso()
    clone["applied_at"] = None
    clone["parent_scenario_id"] = scenario.get("id")
    return clone


def scenario_scores(layout: dict[str, Any], journey: str = "blank") -> dict[str, Any]:
    report = build_validation_report(layout, journey=journey)
    warnings = report["warnings"]
    blocked = sum(1 for item in warnings if item["severity"] == "blocked")
    serious = sum(1 for item in warnings if item["severity"] == "serious")
    warning = sum(1 for item in warnings if item["severity"] == "warning")
    item_count = len(layout.get("items", []))
    confidence = 100
    confidence -= blocked * 30 + serious * 18 + warning * 8
    if report["unknowns"]:
        confidence -= min(30, len(report["unknowns"]) * 6)
    confidence = max(0, min(100, confidence))
    return {
        "fit": max(0, 100 - blocked * 35 - serious * 20 - warning * 10),
        "circulation": max(0, 100 - blocked * 40 - serious * 18 - warning * 8),
        "accessibility": max(0, 100 - blocked * 45 - serious * 20 - warning * 8),
        "cost_complexity": min(100, item_count * 3 + serious * 15 + warning * 8),
        "confidence": confidence,
    }


def unknowns_for_layout(layout: dict[str, Any]) -> list[dict[str, str]]:
    migrated = migrate_layout(layout)
    unknowns: list[dict[str, str]] = []
    calibration = migrated.get("metadata", {}).get("calibration", {})
    if not calibration.get("user_confirmed"):
        unknowns.append(
            {
                "field": "scale",
                "message": "Scale is estimated rather than user-confirmed.",
                "fix": "Calibrate a known-length segment before buying or renovating.",
            }
        )
    if not migrated.get("rooms"):
        unknowns.append(
            {
                "field": "rooms",
                "message": "Room boundaries are missing or unconfirmed.",
                "fix": "Trace rooms manually or confirm extracted rooms.",
            }
        )
    if not any(_door_width(item) for item in migrated.get("items", [])):
        unknowns.append(
            {
                "field": "door_widths",
                "message": "Door widths are missing.",
                "fix": "Enter widths for entry, corridor, bedroom, and bathroom doors.",
            }
        )
    for item in migrated.get("items", []):
        catalog = item.get("catalog") if isinstance(item, dict) else None
        if isinstance(catalog, dict) and catalog.get("source_confidence") in {None, "unknown", "estimated"}:
            unknowns.append(
                {
                    "field": "product_dimensions",
                    "message": f"{_text(item.get('name') or item.get('furnitureType'), 'Product')} dimensions are unverified.",
                    "fix": "Confirm product dimensions from the retailer or manual measurement.",
                }
            )
    return unknowns


def _warning(
    severity: str,
    code: str,
    message: str,
    explanation: str,
    suggested_fix: str,
    *,
    room: str = "Project",
    geometry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_severity = severity if severity in VALIDATION_SEVERITIES else "warning"
    return {
        "severity": clean_severity,
        "code": code,
        "room": room,
        "message": message,
        "explanation": explanation,
        "suggested_fix": suggested_fix,
        "geometry": geometry or {},
    }


def build_validation_report(
    layout: dict[str, Any],
    *,
    journey: str = "blank",
    accessibility_profile: str = "general_aging_ready",
) -> dict[str, Any]:
    migrated = migrate_layout(layout)
    warnings: list[dict[str, Any]] = []
    unknowns = unknowns_for_layout(migrated)
    items = [item for item in migrated.get("items", []) if isinstance(item, dict) and item.get("visible", True)]

    if unknowns:
        warnings.append(
            _warning(
                "warning",
                "missing_measurements",
                "Some measurements are missing or unconfirmed.",
                "Haus can still plan, but spatial checks become less reliable when scale, rooms, door widths, or product dimensions are unknown.",
                "Open the assumptions and unknowns panels, then confirm scale, doors, room boundaries, and product dimensions.",
                geometry={"unknowns": unknowns},
            )
        )

    for i, item in enumerate(items):
        for j, other in enumerate(items[i + 1 :], start=i + 1):
            if _rect_intersects(item_rect(item), item_rect(other)):
                room = _text(item.get("room") or other.get("room"), "Unassigned")
                warnings.append(
                    _warning(
                        "serious",
                        "overlap",
                        f"{_object_label(item)} overlaps {_object_label(other)}.",
                        "Overlapping footprints can mean the plan is impossible or needs manual adjustment.",
                        "Move, resize, or remove one of the overlapping objects, then regenerate validation.",
                        room=room,
                        geometry={
                            "items": [item.get("id"), other.get("id")],
                            "blocked_area": _union_rect(item_rect(item), item_rect(other)),
                        },
                    )
                )

    profile = ACCESSIBILITY_PROFILES.get(accessibility_profile, ACCESSIBILITY_PROFILES["general_aging_ready"])
    if journey == "accessibility":
        warnings.extend(accessibility_warnings(migrated, profile_name=accessibility_profile))
    else:
        min_gap = 0.75
        for i, item in enumerate(items):
            for other in items[i + 1 :]:
                gap = _rect_gap(item_rect(item), item_rect(other))
                if 0 < gap < min_gap:
                    warnings.append(
                        _warning(
                            "warning",
                            "tight_clearance",
                            f"{_object_label(item)} is only {gap:.2f}m from {_object_label(other)}.",
                            "Narrow gaps reduce comfortable circulation and make cleaning or furniture use harder.",
                            "Target at least 0.75m for everyday compact circulation unless this is intentional.",
                            room=_text(item.get("room") or other.get("room"), "Unassigned"),
                            geometry={"clearance_m": round(gap, 2), "target_m": min_gap},
                        )
                    )

    if journey == "renovation":
        for item in items:
            if item.get("type") == "wall" and item.get("structural_status", "unknown") == "unknown":
                warnings.append(
                    _warning(
                        "serious",
                        "structural_unknown",
                        "A wall has unknown structural status.",
                        "Floor-plan images do not prove whether a wall is structural.",
                        "Treat wall changes as concept-only until a qualified professional verifies the wall.",
                        geometry={"item_id": item.get("id"), "footprint": _rect_dict(item_rect(item))},
                    )
                )

    room_summaries = summarize_rooms(migrated, warnings)
    report = {
        "id": f"validation-{uuid.uuid4().hex[:8]}",
        "generated_at": _now_iso(),
        "journey": journey,
        "accessibility_profile": profile["label"],
        "severity_model": list(VALIDATION_SEVERITIES),
        "warnings": warnings,
        "unknowns": unknowns,
        "room_summaries": room_summaries,
        "overlays": validation_overlays(migrated, warnings, profile),
        "disclaimers": [PRODUCT_SAFE_DISCLAIMER],
    }
    if journey == "accessibility":
        report["disclaimers"].append(ACCESSIBILITY_DISCLAIMER)
    if journey == "renovation":
        report["disclaimers"].append(RENOVATION_DISCLAIMER)
    return report


def _object_label(item: dict[str, Any]) -> str:
    return _text(item.get("name") or item.get("furnitureType") or item.get("type"), "object")


def _union_rect(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> dict[str, float]:
    return _rect_dict((min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])))


def _rect_dict(rect: tuple[float, float, float, float]) -> dict[str, float]:
    return {"x_min": round(rect[0], 3), "z_min": round(rect[1], 3), "x_max": round(rect[2], 3), "z_max": round(rect[3], 3)}


def summarize_rooms(layout: dict[str, Any], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = [_room_label(room) for room in layout.get("rooms", []) if isinstance(room, dict)]
    if not labels:
        labels = sorted({_text(item.get("room"), "Unassigned") for item in layout.get("items", []) if isinstance(item, dict)})
    if not labels:
        labels = ["Project"]
    summaries = []
    for label in labels:
        room_warnings = [warning for warning in warnings if warning.get("room") in {label, "Project"}]
        highest = "info"
        for severity in VALIDATION_SEVERITIES:
            if any(warning["severity"] == severity for warning in room_warnings):
                highest = severity
        summaries.append(
            {
                "room": label,
                "warning_count": len(room_warnings),
                "highest_severity": highest,
                "summary": "No blocking issues found." if not room_warnings else f"{len(room_warnings)} issue(s) need review.",
            }
        )
    return summaries


def validation_overlays(
    layout: dict[str, Any], warnings: list[dict[str, Any]], profile: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    bounds = _layout_bounds(layout)
    walkway_width = _num(profile.get("path_min_m"), 0.85)
    turning = _num(profile.get("turning_circle_m"), 1.2)
    footprints = []
    for item in layout.get("items", []):
        if isinstance(item, dict):
            width, _, depth = _item_dimensions(item)
            footprints.append(
                {
                    "item_id": item.get("id"),
                    "label": _object_label(item),
                    "rect": _rect_dict(item_rect(item)),
                    "measurement": f"{width:.2f}m x {depth:.2f}m",
                }
            )
    return {
        "walkway_corridors": [
            {
                "from": {"x": round(bounds[0], 3), "z": round((bounds[1] + bounds[3]) / 2, 3)},
                "to": {"x": round(bounds[2], 3), "z": round((bounds[1] + bounds[3]) / 2, 3)},
                "width_m": walkway_width,
                "measurement": f"{walkway_width:.2f}m target corridor",
            }
        ],
        "blocked_areas": [
            warning["geometry"]["blocked_area"]
            for warning in warnings
            if isinstance(warning.get("geometry"), dict) and "blocked_area" in warning["geometry"]
        ],
        "door_clearances": [
            {"item_id": item.get("id"), "width_m": _door_width(item), "measurement": f"{_door_width(item):.2f}m"}
            for item in layout.get("items", [])
            if isinstance(item, dict) and _door_width(item)
        ],
        "turning_circles": [
            {
                "center": {"x": round((bounds[0] + bounds[2]) / 2, 3), "z": round((bounds[1] + bounds[3]) / 2, 3)},
                "diameter_m": turning,
                "measurement": f"{turning:.2f}m turning circle",
            }
        ],
        "product_footprints": footprints,
    }


def extraction_inference_summary(layout: dict[str, Any]) -> dict[str, Any]:
    migrated = migrate_layout(layout)
    items = migrated.get("items", [])
    walls = [item for item in items if isinstance(item, dict) and item.get("type") == "wall"]
    doors = [item for item in items if isinstance(item, dict) and item.get("type") in {"door", "opening"}]
    return {
        "wall_count": len(walls),
        "room_count": len(migrated.get("rooms", [])),
        "door_or_opening_count": len(doors),
        "scale_confidence": migrated.get("metadata", {}).get("calibration", {}).get("confidence", "unknown"),
        "can_infer": [
            "approximate wall geometry" if walls else "floor plan image only until traced",
            "room labels and bounds" if migrated.get("rooms") else "room labels need manual tracing",
            "clearance checks after door widths and scale are confirmed",
        ],
    }


def command_route(message: str) -> str:
    text = message.lower()
    if re.search(r"\b(apply|use this|commit scenario)\b", text):
        return "apply_plan"
    if re.search(r"\b(revise|make it|cheaper|more storage|less renovation|more accessible)\b", text):
        return "revise_plan"
    if re.search(r"\b(export|download|report|brief|shopping list)\b", text):
        return "export_report"
    if re.search(r"\b(validate|check|sanity|risk|warning|fit)\b", text):
        return "validate_layout"
    if re.search(r"\b(move|rotate|resize|delete|lock|unlock|edit)\b", text):
        return "edit_object"
    if re.search(r"\b(draft|design|generate|plan|scenario|concept)\b", text):
        return "draft_plan"
    return "ask_question"


def journey_system_prompt(journey: str, metadata: dict[str, Any] | None = None) -> str:
    clean = journey if journey in JOURNEYS else "blank"
    context = json.dumps(metadata or {}, sort_keys=True)
    boundaries = [PRODUCT_SAFE_DISCLAIMER]
    if clean == "accessibility":
        boundaries.append(ACCESSIBILITY_DISCLAIMER)
    if clean == "renovation":
        boundaries.append(RENOVATION_DISCLAIMER)
    return (
        f"You are Haus planning for {JOURNEYS[clean]}. Use active project metadata: {context}. "
        "Draft before applying, keep assumptions editable, cite source URLs when web research influences a recommendation, "
        "and preserve these boundaries: "
        + " ".join(boundaries)
    )


def llm_review_badge(planner: dict[str, Any] | None) -> str:
    if isinstance(planner, dict) and planner.get("mode") in {"llm_reviewed", "llm_structured"} and planner.get("provider_reviewed"):
        return "LLM reviewed"
    return "Deterministic"


def _door_width(item: dict[str, Any]) -> float:
    if item.get("width_m") is not None:
        return _num(item.get("width_m"))
    opening = item.get("room_capture_opening")
    if isinstance(opening, dict) and opening.get("width_m") is not None:
        return _num(opening.get("width_m"))
    if item.get("type") in {"door", "opening"}:
        width, _, _ = _item_dimensions(item)
        return width
    return 0.0


def accessibility_warnings(layout: dict[str, Any], profile_name: str = "general_aging_ready") -> list[dict[str, Any]]:
    profile = ACCESSIBILITY_PROFILES.get(profile_name, ACCESSIBILITY_PROFILES["general_aging_ready"])
    warnings: list[dict[str, Any]] = []
    door_min = _num(profile["doorway_min_m"], 0.8)
    path_min = _num(profile["path_min_m"], 0.85)
    turning = _num(profile["turning_circle_m"], 1.2)
    doors = [item for item in layout.get("items", []) if isinstance(item, dict) and _door_width(item)]
    items = [item for item in layout.get("items", []) if isinstance(item, dict)]

    for door in doors:
        width = _door_width(door)
        if width < door_min:
            warnings.append(
                _warning(
                    "blocked",
                    "doorway_width",
                    f"{_object_label(door)} is {width:.2f}m wide; target is {door_min:.2f}m.",
                    "The selected profile may not pass through this doorway comfortably.",
                    "Verify the door width on site and consider widening, removing the door, or changing the route.",
                    room=_text(door.get("room"), "Project"),
                    geometry={"width_m": width, "target_m": door_min, "item_id": door.get("id")},
                )
            )

    for i, item in enumerate(items):
        for other in items[i + 1 :]:
            gap = _rect_gap(item_rect(item), item_rect(other))
            if 0 < gap < path_min:
                warnings.append(
                    _warning(
                        "serious",
                        "path_clearance",
                        f"Route gap is {gap:.2f}m; target is {path_min:.2f}m.",
                        "The selected profile needs a wider continuous route between major areas.",
                        "Move furniture, remove hazards, or mark a renovation option to create a wider path.",
                        room=_text(item.get("room") or other.get("room"), "Project"),
                        geometry={"clearance_m": gap, "target_m": path_min},
                    )
                )

    bounds = _layout_bounds(layout)
    if min(bounds[2] - bounds[0], bounds[3] - bounds[1]) < turning:
        warnings.append(
            _warning(
                "serious",
                "turning_circle",
                f"No obvious {turning:.2f}m turning circle fits in the current layout bounds.",
                "Wheelchair and caregiver-assisted profiles need clear turning space in key rooms.",
                "Clear furniture from a turning zone or verify room dimensions manually.",
                geometry={"diameter_m": turning},
            )
        )

    warnings.extend(_bed_transfer_warnings(items, profile))
    warnings.extend(_bathroom_access_warnings(items, profile))
    warnings.extend(_kitchen_access_warnings(items, profile))
    warnings.extend(_door_swing_warnings(items))
    warnings.extend(_trip_hazard_warnings(items))
    warnings.extend(_lighting_recommendations(layout))
    warnings.append(
        _warning(
            "info",
            "storage_reach_height",
            "Review storage reach heights for daily-use items.",
            "Reach height is a non-geometric recommendation unless shelf heights are entered.",
            "Move daily-use storage between knee and shoulder height for the target user.",
        )
    )
    return warnings


def _bed_transfer_warnings(items: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    clearance = max(0.75, _num(profile.get("path_min_m"), 0.85))
    beds = [item for item in items if str(item.get("furnitureType", "")).startswith("bed")]
    for bed in beds:
        gaps = [_rect_gap(item_rect(bed), item_rect(other)) for other in items if other is not bed]
        free = min(gaps) if gaps else clearance
        if free < clearance:
            warnings.append(
                _warning(
                    "serious",
                    "bed_transfer",
                    f"Bed transfer side clearance appears below {clearance:.2f}m.",
                    "At least one side and the foot of the bed should remain reachable for the selected profile.",
                    "Shift the bed or remove nearby furniture to preserve transfer and caregiver access.",
                    room=_text(bed.get("room"), "Bedroom"),
                    geometry={"clearance_m": free, "target_m": clearance},
                )
            )
    return warnings


def _bathroom_access_warnings(items: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    targets = {"toilet": "toilet_transfer", "shower": "shower_access", "sink": "vanity_approach"}
    clearance = max(0.75, _num(profile.get("path_min_m"), 0.85))
    for item in items:
        ftype = item.get("furnitureType")
        if ftype in targets:
            nearest = min(
                (_rect_gap(item_rect(item), item_rect(other)) for other in items if other is not item),
                default=clearance,
            )
            if nearest < clearance:
                warnings.append(
                    _warning(
                        "serious",
                        targets[ftype],
                        f"{_object_label(item)} approach clearance is {nearest:.2f}m.",
                        "Bathroom fixtures need clear approach and transfer space for safe use.",
                        "Move nearby objects, reverse door swing, or treat this as a renovation item.",
                        room=_text(item.get("room"), "Bathroom"),
                        geometry={"clearance_m": nearest, "target_m": clearance},
                    )
                )
    return warnings


def _kitchen_access_warnings(items: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    kitchen_types = {"fridge", "sink", "kitchen_counter", "stove", "washer"}
    warnings = []
    clearance = _num(profile.get("path_min_m"), 0.85)
    for item in items:
        if item.get("furnitureType") in kitchen_types:
            nearest = min(
                (_rect_gap(item_rect(item), item_rect(other)) for other in items if other is not item),
                default=clearance,
            )
            if nearest < clearance:
                warnings.append(
                    _warning(
                        "warning",
                        "kitchen_reach_access",
                        f"{_object_label(item)} has tight approach clearance.",
                        "Kitchen appliances and counters need reachable front access.",
                        "Move mobile furniture or revise cabinet/appliance placement.",
                        room=_text(item.get("room"), "Kitchen"),
                        geometry={"clearance_m": nearest, "target_m": clearance},
                    )
                )
    return warnings


def _door_swing_warnings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    doors = [item for item in items if item.get("type") == "door" or item.get("swing_direction")]
    for door in doors:
        swing = _text(door.get("swing_direction"), "")
        if swing and swing != "sliding":
            swing_rect = item_rect(door, padding=max(_door_width(door), 0.75))
            for other in items:
                if other is door:
                    continue
                if _rect_intersects(swing_rect, item_rect(other)):
                    warnings.append(
                        _warning(
                            "warning",
                            "door_swing_conflict",
                            f"{_object_label(door)} swing conflicts with {_object_label(other)}.",
                            "Door swings can block bathroom, bedroom, or corridor routes.",
                            "Reverse the swing, use a sliding/no-door opening, or move the obstruction.",
                            room=_text(door.get("room") or other.get("room"), "Project"),
                            geometry={"door_id": door.get("id"), "conflict_id": other.get("id")},
                        )
                    )
    return warnings


def _trip_hazard_warnings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings = []
    hazard_types = {"rug", "threshold", "clutter", "loose_obstacle"}
    for item in items:
        if item.get("hazard") or item.get("furnitureType") in hazard_types:
            warnings.append(
                _warning(
                    "warning",
                    "trip_hazard",
                    f"{_object_label(item)} is marked as a trip hazard.",
                    "Rugs, thresholds, clutter zones, tight gaps, and loose obstacles increase fall risk.",
                    "Remove or secure the hazard and keep the walking route clear.",
                    room=_text(item.get("room"), "Project"),
                    geometry={"item_id": item.get("id"), "footprint": _rect_dict(item_rect(item))},
                )
            )
    return warnings


def _lighting_recommendations(layout: dict[str, Any]) -> list[dict[str, Any]]:
    rooms = [_room_label(room).lower() for room in layout.get("rooms", []) if isinstance(room, dict)]
    targets = ["entry", "corridor", "bathroom", "stairs", "night path"]
    missing = [target for target in targets if not any(target in room for room in rooms)]
    return [
        _warning(
            "info",
            "lighting_recommendation",
            "Add lighting review markers for entry, corridor, bathroom, stairs, and night path.",
            "Lighting risk is not fully geometric without fixture and switch locations.",
            f"Verify lighting for: {', '.join(missing or targets)}.",
        )
    ]


def accessibility_fix_list(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups = {
        "move_furniture": [],
        "remove_hazard": [],
        "change_product": [],
        "renovate": [],
        "verify_on_site": [],
    }
    for warning in report.get("warnings", []):
        code = warning.get("code")
        if code in {"path_clearance", "bed_transfer", "kitchen_reach_access"}:
            groups["move_furniture"].append(warning)
        elif code == "trip_hazard":
            groups["remove_hazard"].append(warning)
        elif code in {"doorway_width", "turning_circle", "toilet_transfer", "shower_access", "vanity_approach"}:
            groups["renovate"].append(warning)
        elif code == "missing_measurements":
            groups["verify_on_site"].append(warning)
        else:
            groups["change_product"].append(warning)
    return groups


def caregiver_route_simulations(layout: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _route_simulation(layout, "bedroom", "bathroom", "caregiver-assisted bedroom to bathroom route"),
        _route_simulation(layout, "entry", "living", "caregiver-assisted entry to living route"),
    ]


def night_route_simulation(layout: dict[str, Any]) -> dict[str, Any]:
    return _route_simulation(layout, "bed", "bathroom", "night route from bed to bathroom")


def _route_simulation(layout: dict[str, Any], start: str, end: str, label: str) -> dict[str, Any]:
    report = build_validation_report(layout, journey="accessibility", accessibility_profile="caregiver_assisted")
    blockers = [warning for warning in report["warnings"] if warning["severity"] in {"blocked", "serious"}]
    return {
        "label": label,
        "start": start,
        "end": end,
        "status": "blocked" if blockers else "clear_with_assumptions",
        "blockers": blockers[:5],
    }


def bathroom_safety_checklist(layout: dict[str, Any]) -> list[dict[str, Any]]:
    items = [item for item in migrate_layout(layout).get("items", []) if isinstance(item, dict)]
    has_shower = any(item.get("furnitureType") == "shower" for item in items)
    has_grab_bar = any("grab" in _object_label(item).lower() for item in items)
    has_non_slip = any(item.get("non_slip_surface") for item in items)
    door_swing = any(item.get("swing_direction") for item in items if item.get("type") == "door")
    return [
        {"item": "Walk-in or curbless shower label", "ok": has_shower, "note": "Confirm step-in, walk-in, or curbless shower type."},
        {"item": "Grab bar locations", "ok": has_grab_bar, "note": "Mark placeholder grab bars before renovation discussions."},
        {"item": "Non-slip surface", "ok": has_non_slip, "note": "Mark non-slip surface as a material note."},
        {"item": "Door swing direction", "ok": door_swing, "note": "Out-swing, sliding, or no-door options can reduce trapped-fall risk."},
    ]


def flag_structural_uncertainty(layout: dict[str, Any]) -> dict[str, Any]:
    migrated = migrate_layout(layout)
    for item in migrated.get("items", []):
        if isinstance(item, dict) and item.get("type") == "wall":
            item.setdefault("structural_status", "unknown")
            item.setdefault("structural_confidence", "unknown")
            item.setdefault("concept_only", True)
    return migrated


def lock_elements(layout: dict[str, Any], ids: Iterable[str]) -> dict[str, Any]:
    migrated = migrate_layout(layout)
    lock_ids = set(ids)
    for item in migrated.get("items", []):
        if isinstance(item, dict) and item.get("id") in lock_ids:
            item["locked"] = True
            item["do_not_touch"] = True
    for room in migrated.get("rooms", []):
        if isinstance(room, dict) and room.get("id") in lock_ids:
            room["locked"] = True
            room["do_not_touch"] = True
    return migrated


def renovation_intake_schema() -> dict[str, Any]:
    return {
        "goals": "",
        "must_keep_rooms": [],
        "must_change_rooms": [],
        "budget_band": "unknown",
        "style": "",
        "household_profile": "",
        "constraints": "",
        "allowed_wall_changes": ["no_wall_changes", "non_structural_only", "exploratory_concept"],
        "room_priorities": [
            "storage",
            "open_space",
            "work_from_home",
            "child_friendly",
            "entertaining",
            "rental",
            "resale",
            "aging_ready",
        ],
    }


def renovation_scenarios(layout: dict[str, Any], intake: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    migrated = flag_structural_uncertainty(layout)
    details = {**renovation_intake_schema(), **(intake or {})}
    scenarios = []
    specs = [
        ("conservative", "low", "Keep walls and services fixed; improve storage, furniture, and room functions.", 0.78),
        ("balanced", "medium", "Explore non-structural openings, better zoning, and room reassignment.", 0.64),
        ("ambitious", "high", "Conceptual open-plan and service-zone ideas needing professional verification.", 0.46),
    ]
    for name, cost_tier, summary, confidence in specs:
        scenario = create_scenario(name, "renovation", migrated, status="draft")
        scenario.update(
            {
                "summary": summary,
                "allowed_wall_changes": details.get("allowed_wall_changes", "no_wall_changes"),
                "room_priorities": details.get("room_priorities", []),
                "cost_tier": cost_tier,
                "cost_tier_explanation": cost_tier_explanation(cost_tier),
                "confidence": confidence,
                "scores": {
                    "disruption": {"low": 25, "medium": 55, "high": 85}[cost_tier],
                    "likely_cost_tier": cost_tier,
                    "confidence": round(confidence * 100),
                    "storage_gain": 30 if name == "conservative" else 55 if name == "balanced" else 70,
                    "circulation_quality": 65 if name == "conservative" else 75 if name == "balanced" else 70,
                    "accessibility_impact": 35 if name == "conservative" else 55 if name == "balanced" else 60,
                },
                "proposed_wall_changes": _proposed_wall_changes(migrated, name),
                "storage_plan": storage_plan(migrated),
                "kitchen_work_zone": kitchen_work_zone_check(migrated),
                "bathroom_clearance": bathroom_fixture_clearance_check(migrated),
                "open_plan_concepts": open_plan_concept(migrated),
                "room_reassignments": room_function_reassignments(migrated),
                "before_after_annotations": before_after_annotations(migrated),
                "contractor_questions": renovation_questions(migrated),
                "fixed_service_zones": fixed_service_zone_tags(migrated),
                "materials_and_finishes": materials_finishes_placeholder(),
            }
        )
        scenarios.append(scenario)
    return scenarios


def _proposed_wall_changes(layout: dict[str, Any], scenario_name: str) -> list[dict[str, Any]]:
    if scenario_name == "conservative":
        return []
    changes = []
    for item in layout.get("items", []):
        if isinstance(item, dict) and item.get("type") == "wall":
            changes.append(
                {
                    "item_id": item.get("id"),
                    "action": "review_opening" if scenario_name == "balanced" else "review_removal",
                    "concept_only": True,
                    "requires_professional_verification": True,
                    "structural_status": item.get("structural_status", "unknown"),
                }
            )
            if changes:
                break
    return changes


def storage_plan(layout: dict[str, Any]) -> dict[str, Any]:
    rooms = [_room_label(room) for room in layout.get("rooms", []) if isinstance(room, dict)] or ["Project"]
    zones = []
    for room in rooms:
        items = [item for item in layout.get("items", []) if isinstance(item, dict) and item.get("room") == room]
        storage_items = [item for item in items if "wardrobe" in str(item.get("furnitureType", "")) or "storage" in _object_label(item).lower()]
        zones.append(
            {
                "room": room,
                "storage_item_count": len(storage_items),
                "status": "under_served" if len(storage_items) == 0 else "served",
                "recommendation": "Add closed storage or built-in placeholder." if len(storage_items) == 0 else "Keep existing storage accessible.",
            }
        )
    return {"zones": zones, "under_served_rooms": [zone["room"] for zone in zones if zone["status"] == "under_served"]}


def kitchen_work_zone_check(layout: dict[str, Any]) -> dict[str, Any]:
    required = {"fridge", "sink", "kitchen_counter"}
    present = {item.get("furnitureType") for item in layout.get("items", []) if isinstance(item, dict)}
    missing = sorted(required - present)
    return {
        "present": sorted(required & present),
        "missing": missing,
        "conflicts": [
            warning
            for warning in build_validation_report(layout, journey="renovation")["warnings"]
            if warning["code"] in {"overlap", "tight_clearance"} and warning.get("room") == "Kitchen"
        ],
        "status": "needs_inputs" if missing else "review_clearances",
    }


def bathroom_fixture_clearance_check(layout: dict[str, Any]) -> dict[str, Any]:
    required = {"shower", "toilet", "sink"}
    present = {item.get("furnitureType") for item in layout.get("items", []) if isinstance(item, dict)}
    missing = sorted(required - present)
    return {"present": sorted(required & present), "missing": missing, "status": "needs_inputs" if missing else "review_clearances"}


def open_plan_concept(layout: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": "visual_zoning",
            "description": "Use furniture, rugs, lighting, and storage edges to create open-plan zones without assuming structural feasibility.",
            "structural_assumption": "unknown",
            "concept_only": True,
        }
    ]


def room_function_reassignments(layout: dict[str, Any]) -> list[dict[str, Any]]:
    rooms = [_room_label(room) for room in layout.get("rooms", []) if isinstance(room, dict)] or ["Spare room"]
    targets = ["study", "nursery", "guest room", "storage room", "dining", "flex space"]
    return [{"room": room, "candidate_functions": targets[:3], "note": "Confirm household priorities before applying."} for room in rooms[:3]]


def before_after_annotations(layout: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "item_id": item.get("id"),
            "status": "unchanged" if item.get("locked") else "candidate",
            "annotation": "moved, added, removed, and unchanged tags are tracked per scenario",
        }
        for item in layout.get("items", [])
        if isinstance(item, dict)
    ]


def renovation_questions(layout: dict[str, Any]) -> list[str]:
    questions = [
        "Which walls are confirmed non-structural?",
        "Where are plumbing stacks, floor traps, and electrical risers?",
        "Which rooms or fixtures are do-not-touch?",
        "What budget band and timeline should constrain the option?",
    ]
    if unknowns_for_layout(layout):
        questions.append("Which missing measurements can be verified on site before quoting?")
    return questions


def renovation_scope_brief(project: dict[str, Any], scenario: dict[str, Any]) -> str:
    lines = [
        "# Renovation Scope Brief",
        "",
        f"Project: {project.get('title', 'Untitled')}",
        f"Selected option: {scenario.get('name', 'Scenario')}",
        "",
        "## Goals",
        _text(project.get("intake", {}).get("main_goal"), "Not specified"),
        "",
        "## Constraints",
        _text(project.get("intake", {}).get("constraints"), "Confirm constraints before quoting."),
        "",
        "## Scenario Summary",
        _text(scenario.get("summary"), "No summary."),
        "",
        "## Assumptions",
    ]
    assumptions = project.get("assumptions") or scenario.get("assumptions") or ["Measurements and wall status need confirmation."]
    lines.extend(f"- {assumption}" for assumption in assumptions)
    lines.extend(["", "## Open Questions"])
    lines.extend(f"- {question}" for question in scenario.get("contractor_questions", renovation_questions(project.get("layout", {}))))
    lines.extend(["", "## Disclaimer", PRODUCT_SAFE_DISCLAIMER, RENOVATION_DISCLAIMER])
    return "\n".join(lines)


def renovation_sanity_check(scenario: dict[str, Any]) -> dict[str, Any]:
    issues = []
    for change in scenario.get("proposed_wall_changes", []):
        if change.get("requires_professional_verification"):
            issues.append("Wall/opening change is concept-only and needs professional verification.")
        if change.get("structural_status") == "unknown":
            issues.append("Wall structural status is unknown.")
    if scenario.get("cost_tier") == "unknown":
        issues.append("Cost tier is unknown.")
    return {"ok": not issues, "issues": issues, "confidence": scenario.get("confidence", 0.5)}


def fixed_service_zone_tags(layout: dict[str, Any]) -> list[dict[str, Any]]:
    zones = []
    for item in layout.get("items", []):
        if isinstance(item, dict) and item.get("furnitureType") in {"sink", "toilet", "shower", "washer", "fridge"}:
            zones.append({"item_id": item.get("id"), "tag": "fixed_service_zone", "high_risk_modification": True})
    return zones


def materials_finishes_placeholder() -> dict[str, Any]:
    return {
        "status": "placeholder",
        "note": "Collect materials and finishes as qualitative notes; Haus does not estimate exact costs.",
        "fields": ["flooring", "wall_finish", "countertop", "cabinetry", "lighting", "hardware"],
    }


def cost_tier_explanation(tier: str) -> str:
    return {
        "low": "Low: furniture, storage, finishes, and minor non-invasive changes; exact prices are not estimated.",
        "medium": "Medium: likely trade coordination or non-structural changes; verify scope and quantities.",
        "high": "High: wall, wet-area, service, or major built-in concepts; professional pricing required, not exact prices.",
        "unknown": "Unknown: missing scope or measurement data prevents even tier-level confidence.",
    }.get(tier, "Unknown: missing scope or measurement data prevents even tier-level confidence.")


def revise_renovation_scenario(scenario: dict[str, Any], command: str) -> dict[str, Any]:
    revised = copy.deepcopy(scenario)
    text = command.lower()
    revised["status"] = "revised"
    revised["revision_command"] = command
    if "cheaper" in text or "less renovation" in text:
        revised["cost_tier"] = "low"
        revised["summary"] = "Revised toward lower disruption, fewer fixed-service changes, and furniture/storage moves."
    if "more storage" in text:
        revised.setdefault("room_priorities", []).append("storage")
        revised["storage_plan"] = scenario.get("storage_plan", {})
    if "more accessible" in text:
        revised.setdefault("room_priorities", []).append("aging_ready")
        revised["accessibility_impact_note"] = "Prioritize wider paths, bathroom safety, and fewer trip hazards."
    return revised


def apply_renovation_scenario(
    layout: dict[str, Any], scenario: dict[str, Any], *, confirm_wall_changes: bool = False
) -> dict[str, Any]:
    if scenario.get("proposed_wall_changes") and not confirm_wall_changes:
        return {
            "ok": False,
            "blocked": True,
            "reason": "Wall removal or opening suggestions require explicit confirmation and professional verification.",
            "layout": migrate_layout(layout),
        }
    applied = migrate_layout(scenario.get("layout", layout))
    applied.setdefault("metadata", {})["applied_scenario"] = scenario.get("id")
    return {"ok": True, "layout": applied}


def product_dimension(
    *,
    name: str,
    width_m: float,
    depth_m: float,
    height_m: float,
    clearance_need_m: float = 0.6,
    orientation: str = "either",
    source_url: str = "",
    source_confidence: str = "manual",
    last_checked_date: str | None = None,
    price: float | None = None,
    retailer: str = "",
) -> dict[str, Any]:
    return {
        "id": f"product-{uuid.uuid4().hex[:8]}",
        "name": _text(name, "Product"),
        "width_m": round(max(0.01, width_m), 4),
        "depth_m": round(max(0.01, depth_m), 4),
        "height_m": round(max(0.01, height_m), 4),
        "clearance_need_m": round(max(0.0, clearance_need_m), 4),
        "orientation": orientation,
        "source_url": source_url,
        "source_confidence": source_confidence,
        "last_checked_date": last_checked_date or _now_iso()[:10],
        "price": price,
        "retailer": retailer,
    }


def parse_product_dimensions(text: str) -> dict[str, float] | None:
    lower = text.lower()
    labels = {
        "width_m": r"\b(?:width|w)\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m|in|inch|inches)",
        "depth_m": r"\b(?:depth|d)\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m|in|inch|inches)",
        "height_m": r"\b(?:height|h)\b\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m|in|inch|inches)",
    }
    dims: dict[str, float] = {}
    for key, pattern in labels.items():
        match = re.search(pattern, lower)
        if match:
            dims[key] = _unit_to_m(float(match.group(1)), match.group(2))
    compact = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*[x×]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[x×]\s*([0-9]+(?:\.[0-9]+)?))?\s*(mm|cm|m|in|inch|inches)",
        lower,
    )
    if compact:
        unit = compact.group(4)
        dims.setdefault("width_m", _unit_to_m(float(compact.group(1)), unit))
        dims.setdefault("depth_m", _unit_to_m(float(compact.group(2)), unit))
        dims.setdefault("height_m", _unit_to_m(float(compact.group(3) or 75), unit))
    if {"width_m", "depth_m", "height_m"} <= set(dims):
        return {key: round(max(0.01, value), 4) for key, value in dims.items()}
    return None


def _unit_to_m(value: float, unit: str) -> float:
    normalized = unit.lower()
    if normalized == "mm":
        return value / 1000
    if normalized == "cm":
        return value / 100
    if normalized in {"in", "inch", "inches"}:
        return value * 0.0254
    return value


def manual_product_entry(data: dict[str, Any]) -> dict[str, Any]:
    return product_dimension(
        name=_text(data.get("name"), "Manual product"),
        width_m=_num(data.get("width_m"), 1.0),
        depth_m=_num(data.get("depth_m"), 1.0),
        height_m=_num(data.get("height_m"), 1.0),
        clearance_need_m=_num(data.get("clearance_need_m"), 0.6),
        orientation=_text(data.get("orientation"), "either"),
        source_url=_text(data.get("source_url")),
        source_confidence=_text(data.get("source_confidence"), "manual"),
        price=data.get("price"),
        retailer=_text(data.get("retailer")),
    )


def import_product_from_url(url: str, *, timeout_seconds: int = 6) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only public HTTPS product URLs can be imported.")
    req = Request(url, headers={"User-Agent": "Haus product dimension importer"})
    try:
        with urlopen(req, timeout=timeout_seconds) as res:  # noqa: S310 - user-requested public HTTPS import.
            body = res.read(500_000).decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Could not fetch product URL: {exc}") from exc
    title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
    name = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else "Imported product"
    dims = parse_product_dimensions(re.sub(r"<[^>]+>", " ", body))
    if not dims:
        raise ValueError("Could not extract width, depth, and height from product page.")
    return product_dimension(name=name, source_url=url, source_confidence="fetched", **dims)


def load_product_cache(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return raw if isinstance(raw, list) else []


def save_product_cache(path: Path, products: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(products, indent=2), encoding="utf-8")


def furniture_fit_intake_schema() -> dict[str, Any]:
    return {
        "room": "",
        "budget": "",
        "style": "",
        "household_needs": "",
        "existing_furniture": [],
        "must_buy_items": [],
        "preferred_retailers": [],
    }


def product_card(product: dict[str, Any], fit: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": product["name"],
        "dimensions": f"{product['width_m']:.2f}m W x {product['depth_m']:.2f}m D x {product['height_m']:.2f}m H",
        "source": product.get("source_url") or product.get("retailer") or "manual",
        "price": product.get("price"),
        "fit_status": (fit or {}).get("status", "unchecked"),
    }


def check_product_fit(layout: dict[str, Any], product: dict[str, Any], room_name: str = "") -> dict[str, Any]:
    migrated = migrate_layout(layout)
    bounds = _room_or_layout_bounds(migrated, room_name)
    orientations = product_orientations(product)
    results = []
    for width, depth, label in orientations:
        clearance = _num(product.get("clearance_need_m"), 0.6)
        fits_room = width + clearance * 2 <= bounds[2] - bounds[0] and depth + clearance * 2 <= bounds[3] - bounds[1]
        conflicts = []
        test_rect = (
            (bounds[0] + bounds[2]) / 2 - width / 2,
            (bounds[1] + bounds[3]) / 2 - depth / 2,
            (bounds[0] + bounds[2]) / 2 + width / 2,
            (bounds[1] + bounds[3]) / 2 + depth / 2,
        )
        for item in migrated.get("items", []):
            if isinstance(item, dict) and item.get("locked"):
                if _rect_intersects(test_rect, item_rect(item, padding=clearance)):
                    conflicts.append(_object_label(item))
        results.append({"orientation": label, "fits_room": fits_room, "locked_conflicts": conflicts})
    ok = any(result["fits_room"] and not result["locked_conflicts"] for result in results)
    return {
        "status": "fits" if ok else "fails",
        "room": room_name or "layout",
        "clearance_m": _num(product.get("clearance_need_m"), 0.6),
        "door_swing": "check door swing overlays before buying",
        "walkway": "clear" if ok else "at risk",
        "usable_orientations": [result for result in results if result["fits_room"]],
        "all_orientations": results,
    }


def _room_or_layout_bounds(layout: dict[str, Any], room_name: str) -> tuple[float, float, float, float]:
    for room in layout.get("rooms", []):
        if not isinstance(room, dict):
            continue
        if room_name and _room_label(room).lower() != room_name.lower():
            continue
        bounds = room.get("bounds")
        if isinstance(bounds, dict):
            return (
                _num(bounds.get("x_min")),
                _num(bounds.get("z_min")),
                _num(bounds.get("x_max")),
                _num(bounds.get("z_max")),
            )
    return _layout_bounds(layout)


def product_orientations(product: dict[str, Any]) -> list[tuple[float, float, str]]:
    width = _num(product.get("width_m"), 1.0)
    depth = _num(product.get("depth_m"), 1.0)
    orientation = product.get("orientation", "either")
    if orientation == "fixed":
        return [(width, depth, "fixed")]
    return [(width, depth, "0deg"), (depth, width, "90deg")]


def delivery_path_check(layout: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
    min_side = min(_num(product.get("width_m"), 1.0), _num(product.get("depth_m"), 1.0))
    openings = []
    for item in migrate_layout(layout).get("items", []):
        if isinstance(item, dict) and _door_width(item):
            openings.append({"name": _object_label(item), "width_m": _door_width(item)})
    checkpoints = ["entry door", "corridor", "bedroom door", "elevator placeholder", "stair placeholder"]
    blockers = [opening for opening in openings if opening["width_m"] < min_side]
    return {
        "status": "fits_path" if not blockers else "path_blocked",
        "required_min_width_m": round(min_side, 3),
        "checkpoints": checkpoints,
        "openings": openings,
        "blockers": blockers,
        "overlays": [{"type": "delivery_path", "measurement": f"{min_side:.2f}m product side"}],
    }


def assembly_clearance(product: dict[str, Any]) -> dict[str, Any]:
    category = _text(product.get("category"), "").lower()
    defaults = {"bed": 0.75, "wardrobe": 0.90, "desk": 0.75, "table": 0.90, "sofa": 0.75}
    need = defaults.get(category, _num(product.get("clearance_need_m"), 0.6))
    return {"category": category or "furniture", "required_clearance_m": need, "note": "Confirm assembly clearance around beds, wardrobes, desks, dining tables, and sofas."}


def pullout_clearance(product: dict[str, Any]) -> dict[str, Any]:
    category = _text(product.get("category"), "").lower()
    defaults = {"wardrobe": 0.75, "desk": 0.75, "table": 0.90, "sofa_bed": 1.20, "storage": 0.60}
    need = defaults.get(category, _num(product.get("clearance_need_m"), 0.6))
    return {"category": category or "furniture", "required_clearance_m": need, "note": "Check drawers, wardrobe doors, dining chairs, desk chairs, and sofa beds."}


def suggest_substitutes(product: dict[str, Any], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    width = _num(product.get("width_m"), 1.0)
    depth = _num(product.get("depth_m"), 1.0)
    category = product.get("category")
    candidates = [
        item
        for item in catalog
        if item.get("category") == category
        and (_num(item.get("width_m"), 99) < width or _num(item.get("depth_m"), 99) < depth)
    ]
    return sorted(candidates, key=lambda item: _num(item.get("width_m"), 99) * _num(item.get("depth_m"), 99))[:5]


def compare_product_alternatives(products: list[dict[str, Any]], layout: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for product in products:
        fit = check_product_fit(layout, product)
        rows.append(
            {
                "name": product["name"],
                "dimensions": f"{product['width_m']:.2f} x {product['depth_m']:.2f} x {product['height_m']:.2f}m",
                "price": product.get("price"),
                "fit_score": 100 if fit["status"] == "fits" else 25,
                "clearance_risk": fit["walkway"],
            }
        )
    return rows


def shopping_list_export(products: list[dict[str, Any]], fit_results: dict[str, dict[str, Any]] | None = None) -> str:
    lines = ["Product,Width m,Depth m,Height m,Quantity,Source URL,Fit notes"]
    fit_results = fit_results or {}
    for product in products:
        fit = fit_results.get(product["id"], {})
        lines.append(
            ",".join(
                [
                    _csv(product["name"]),
                    f"{product['width_m']:.2f}",
                    f"{product['depth_m']:.2f}",
                    f"{product['height_m']:.2f}",
                    str(product.get("quantity", 1)),
                    _csv(product.get("source_url", "")),
                    _csv(fit.get("status", "unchecked")),
                ]
            )
        )
    return "\n".join(lines)


def _csv(value: Any) -> str:
    text = str(value or "")
    if any(ch in text for ch in ',\n"'):
        return '"' + text.replace('"', '""') + '"'
    return text


def buy_nothing_yet_warning(layout: dict[str, Any], product: dict[str, Any]) -> str | None:
    unknowns = unknowns_for_layout(layout)
    if unknowns or product.get("source_confidence") in {"unknown", "estimated"}:
        return "Buy nothing yet: confirm scale, doorway width, and product dimensions first."
    return None


def room_layout_optimizer(room_kind: str) -> list[str]:
    kind = room_kind.lower()
    if "living" in kind:
        return ["Place sofa facing TV sightline.", "Keep the primary walkway behind or beside seating.", "Avoid blocking balcony or entry doors."]
    if "bed" in kind:
        return ["Keep bed transfer side clear.", "Keep wardrobe pull-out zone open.", "Use daylight side for desk when possible."]
    if "dining" in kind:
        return ["Keep chair pull-out clearance.", "Avoid crossing the kitchen work path.", "Prefer a direct route to serving surfaces."]
    return ["Preserve entry path.", "Keep fixed fixtures accessible.", "Validate after each edit."]


def budget_estimate(products: list[dict[str, Any]]) -> dict[str, Any]:
    known = [float(item["price"]) for item in products if item.get("price") is not None]
    unknown = [item["name"] for item in products if item.get("price") is None]
    return {"known_total": round(sum(known), 2), "unknown_prices": unknown, "currency": "unknown"}


def measurement_checklist(layout: dict[str, Any], products: list[dict[str, Any]] | None = None) -> list[str]:
    checklist = ["Confirm one known-length segment on the floor plan.", "Measure entry door, corridor, bedroom door, and elevator/stair constraints."]
    if unknowns_for_layout(layout):
        checklist.append("Confirm unverified room and door measurements in the unknowns panel.")
    if products:
        checklist.append("Confirm product width, depth, height, assembly clearance, and pull-out clearance.")
    return checklist


def build_html_report(
    project: dict[str, Any],
    report: dict[str, Any],
    *,
    include_assumptions: bool = True,
    include_warnings: bool = True,
    include_shopping_list: bool = True,
    include_scenarios: bool = True,
    include_images: bool = True,
) -> str:
    title = html.escape(project.get("title", "Haus Report"))
    sections = [f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"]
    sections.append(
        "<style>body{font-family:system-ui,sans-serif;margin:32px;line-height:1.45;color:#1f2937}"
        "h1,h2{color:#111827}.warning{border-left:4px solid #b45309;padding:8px 12px;background:#fffbeb}"
        ".blocked{border-left-color:#b91c1c;background:#fef2f2}.info{border-left-color:#2563eb;background:#eff6ff}"
        "@media print{button{display:none}body{margin:18mm}}</style></head><body>"
    )
    sections.append(f"<h1>{title}</h1>")
    sections.append(f"<p>{html.escape(PRODUCT_SAFE_DISCLAIMER)}</p>")
    for disclaimer in report.get("disclaimers", []):
        if disclaimer != PRODUCT_SAFE_DISCLAIMER:
            sections.append(f"<p>{html.escape(disclaimer)}</p>")
    if include_assumptions:
        sections.append("<h2>Assumptions</h2><ul>")
        for assumption in project.get("assumptions", []) or ["No assumptions entered."]:
            sections.append(f"<li>{html.escape(str(assumption))}</li>")
        sections.append("</ul>")
    if include_warnings:
        sections.append("<h2>Warnings</h2>")
        for warning in report.get("warnings", []):
            cls = html.escape(warning.get("severity", "warning"))
            sections.append(
                f"<div class='warning {cls}'><strong>{html.escape(warning.get('message', 'Warning'))}</strong>"
                f"<p>{html.escape(warning.get('explanation', ''))}</p>"
                f"<p>Suggested fix: {html.escape(warning.get('suggested_fix', ''))}</p></div>"
            )
    if include_scenarios:
        sections.append("<h2>Scenarios</h2><ul>")
        for scenario in project.get("scenarios", []):
            sections.append(f"<li>{html.escape(scenario.get('name', 'Scenario'))}: {html.escape(scenario.get('status', 'draft'))}</li>")
        sections.append("</ul>")
    if include_shopping_list and project.get("shopping_list_csv"):
        sections.append("<h2>Shopping List</h2><pre>")
        sections.append(html.escape(project["shopping_list_csv"]))
        sections.append("</pre>")
    if include_images:
        sections.append("<h2>Images</h2><p>Attach exported annotated PNG snapshots when available.</p>")
    sections.append("<button onclick='window.print()'>Print / Save PDF</button></body></html>")
    return "\n".join(sections)


def report_export_record(kind: str, filename: str) -> dict[str, Any]:
    return {"kind": kind, "filename": filename, "created_at": _now_iso(), "disclaimer": PRODUCT_SAFE_DISCLAIMER}


def accessibility_report(layout: dict[str, Any], profile: str = "general_aging_ready") -> dict[str, Any]:
    report = build_validation_report(layout, journey="accessibility", accessibility_profile=profile)
    report["title"] = "Home Accessibility Planning Review"
    report["fix_list"] = accessibility_fix_list(report)
    report["quick_wins"] = [warning for warning in report["warnings"] if warning["code"] in {"trip_hazard", "lighting_recommendation"}]
    report["ask_a_professional"] = [
        warning
        for warning in report["warnings"]
        if warning["code"] in {"doorway_width", "turning_circle", "toilet_transfer", "shower_access"}
    ]
    report["caregiver_routes"] = caregiver_route_simulations(layout)
    report["night_route"] = night_route_simulation(layout)
    report["bathroom_safety_checklist"] = bathroom_safety_checklist(layout)
    report["standards_sources"] = [
        {
            "name": "AARP HomeFit-style practical guidance",
            "source_type": "practical_guidance",
            "url": "https://www.aarp.org/livable-communities/housing/info-2020/homefit-guide/",
        },
        {
            "name": "Accessible-route screening threshold",
            "source_type": "formal_code_inspired_screening",
            "url": "",
        },
    ]
    return report


def accessible_fixture_examples() -> dict[str, list[dict[str, Any]]]:
    return {
        "bedroom": [
            {"type": "furniture", "furnitureType": "bed_queen", "room": "Bedroom", "pos": [0, 0.3, 0], "geo": [1.52, 0.6, 2.03], "clearance_note": "Keep one side and foot clear."},
            {"type": "furniture", "furnitureType": "wardrobe", "room": "Bedroom", "pos": [2.0, 1.0, 0], "geo": [1.2, 2.0, 0.6], "pullout_clearance_m": 0.8},
        ],
        "bathroom": [
            {"type": "furniture", "furnitureType": "toilet", "room": "Bathroom", "pos": [0, 0.2, 0], "geo": [0.4, 0.4, 0.7], "transfer_clearance_m": 0.9},
            {"type": "furniture", "furnitureType": "shower", "room": "Bathroom", "pos": [1.2, 1.0, 0], "geo": [1.0, 2.0, 1.0], "shower_label": "walk-in"},
        ],
    }
