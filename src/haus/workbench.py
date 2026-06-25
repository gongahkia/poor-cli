from __future__ import annotations

import copy
import html
import json
import re
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

from . import geometry

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
    return geometry.coerce_float(value, fallback)


def _item_dimensions(item: dict[str, Any]) -> tuple[float, float, float]:
    return geometry.item_dimensions(item)


def _item_center(item: dict[str, Any]) -> tuple[float, float]:
    return geometry.item_center(item)


def item_rect(item: dict[str, Any], padding: float = 0.0) -> tuple[float, float, float, float]:
    return geometry.item_rect(item, padding=padding)


def _rect_intersects(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return geometry.rect_intersects(a, b)


def _rect_gap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    return geometry.rect_gap(a, b)


def _layout_bounds(layout: dict[str, Any]) -> tuple[float, float, float, float]:
    return geometry.layout_bounds(layout)


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
        item.setdefault("movable", item.get("type") not in {"wall", "fixed_element", "reference_image", "model_part"})
        item.setdefault("fixed", item.get("type") in {"wall", "fixed_element"} or bool(item.get("locked")))
        item.setdefault("existing", True)
        item.setdefault("proposed", False)
        item.setdefault("removed", False)
        item.setdefault("locked", bool(item.get("locked", False)))
        item.setdefault("source", item.get("source_confidence") or item.get("source_type") or "layout")
        item.setdefault("scenario_status", "existing")
        if item.get("type") == "wall":
            item.setdefault("structural_status", "unknown")
            item.setdefault("structural_confidence", "unknown")
        if item.get("type") in {"door", "opening"} or item.get("room_capture_opening"):
            item.setdefault("confidence", "estimated")
            item.setdefault("opening_type", item.get("type", "opening"))
            item.setdefault("width_m", geometry.door_width(item) or None)
            item.setdefault("swing_direction", item.get("swing_direction") or "unknown")
            item.setdefault("threshold_height_m", item.get("threshold_height_m", 0.0))

    for index, room in enumerate(layout["rooms"]):
        if not isinstance(room, dict):
            continue
        room.setdefault("id", f"room-{index + 1}")
        room.setdefault("label", _room_label(room))
        room.setdefault("kind", "room")
        room.setdefault("occupancy", "unknown")
        room.setdefault("priority", "normal")
        room.setdefault("confidence", "estimated")
        room.setdefault("locked", False)
        if isinstance(room.get("openings"), list):
            for opening_index, opening in enumerate(room["openings"]):
                if isinstance(opening, dict):
                    opening.setdefault("id", f"{room['id']}-opening-{opening_index + 1}")
                    opening.setdefault("type", opening.get("kind", "opening"))
                    opening.setdefault("width_m", opening.get("width_m") or opening.get("width"))
                    opening.setdefault("swing_direction", opening.get("swing_direction") or "unknown")
                    opening.setdefault("threshold_height_m", opening.get("threshold_height_m", 0.0))
                    opening.setdefault("confidence", "estimated")

    for scenario in layout["scenarios"]:
        if not isinstance(scenario, dict):
            continue
        scenario.setdefault("journey", metadata.get("project", {}).get("journey", "blank") if isinstance(metadata.get("project"), dict) else "blank")
        scenario.setdefault("status", "draft")
        scenario.setdefault("score", {})
        scenario.setdefault("warnings", [])
        scenario.setdefault("created_at", _now_iso())
        scenario.setdefault("applied_at", None)
        scenario.setdefault("parent_scenario_id", None)

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

    for conflict in geometry.door_swing_conflicts(migrated):
        warnings.append(
            _warning(
                "warning",
                "door_swing_conflict",
                f"{conflict['door']} swing conflicts with {conflict['conflict']}.",
                "Door swings can block bathroom, bedroom, or corridor routes.",
                "Reverse the swing, use a sliding/no-door opening, or move the obstruction.",
                geometry=conflict,
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
        "selected_scenarios": [],
        "source_references": [],
        "accessibility_profile": profile["label"],
        "severity_model": list(VALIDATION_SEVERITIES),
        "warnings": warnings,
        "unknowns": unknowns,
        "confidence_explanations": confidence_explanations(migrated),
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
    return geometry.door_width(item)


def confidence_explanations(layout: dict[str, Any]) -> list[dict[str, str]]:
    migrated = migrate_layout(layout)
    reasons: list[dict[str, str]] = []
    calibration = migrated.get("metadata", {}).get("calibration", {})
    if not calibration.get("user_confirmed"):
        reasons.append(
            {
                "reason": "missing_scale",
                "message": "Confidence is low because the plan scale is estimated or missing.",
                "fix": "Calibrate a known-length segment.",
            }
        )
    if migrated.get("metadata", {}).get("extraction_confidence") in {"low", "weak"}:
        reasons.append(
            {
                "reason": "weak_extraction",
                "message": "Confidence is low because vector extraction was marked weak.",
                "fix": "Use the extraction checklist or manual tracing.",
            }
        )
    if not any(_door_width(item) for item in migrated.get("items", []) if isinstance(item, dict)):
        reasons.append(
            {
                "reason": "missing_openings",
                "message": "Confidence is low because door/opening widths are missing.",
                "fix": "Enter entry, corridor, bedroom, and bathroom opening widths.",
            }
        )
    if any(
        isinstance(item, dict)
        and isinstance(item.get("catalog"), dict)
        and item["catalog"].get("source_confidence") in {None, "unknown", "estimated"}
        for item in migrated.get("items", [])
    ):
        reasons.append(
            {
                "reason": "unverified_product_dimensions",
                "message": "Confidence is low because one or more product dimensions are unverified.",
                "fix": "Confirm dimensions from retailer pages or manual measurements.",
            }
        )
    return reasons


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
    for conflict in geometry.door_swing_conflicts({"items": items}):
        warnings.append(
            _warning(
                "warning",
                "door_swing_conflict",
                f"{conflict['door']} swing conflicts with {conflict['conflict']}.",
                "Door swings can block bathroom, bedroom, or corridor routes.",
                "Reverse the swing, use a sliding/no-door opening, or move the obstruction.",
                geometry=conflict,
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
    return product_dimension(
        name=name,
        width_m=dims["width_m"],
        depth_m=dims["depth_m"],
        height_m=dims["height_m"],
        source_url=url,
        source_confidence="fetched",
    )


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
    selected_ids: Iterable[str] | None = None,
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
    if project.get("source_file"):
        sections.append(f"<p>Source: {html.escape(redact_client_paths(str(project.get('source_file'))))}</p>")
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
        for scenario in selected_scenarios(project, selected_ids):
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


def validation_snapshot(project: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "id": f"validation-snapshot-{uuid.uuid4().hex[:8]}",
        "created_at": _now_iso(),
        "report_id": report.get("id"),
        "journey": report.get("journey", project.get("journey", "blank")),
        "warning_codes": [warning.get("code") for warning in report.get("warnings", [])],
        "severity_counts": {
            severity: sum(1 for warning in report.get("warnings", []) if warning.get("severity") == severity)
            for severity in VALIDATION_SEVERITIES
        },
        "unknown_count": len(report.get("unknowns", [])),
        "confidence_explanations": report.get("confidence_explanations", []),
    }
    project.setdefault("validation_snapshots", []).append(snapshot)
    capture_project_version(project, "revised", project.get("layout", {}), note="Validation snapshot captured")
    return snapshot


def diff_validation_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_codes = [warning.get("code") for warning in before.get("warnings", [])]
    after_codes = [warning.get("code") for warning in after.get("warnings", [])]
    return {
        "before_warning_count": len(before_codes),
        "after_warning_count": len(after_codes),
        "resolved": sorted(set(before_codes) - set(after_codes)),
        "introduced": sorted(set(after_codes) - set(before_codes)),
        "unchanged": sorted(set(before_codes) & set(after_codes)),
        "severity_delta": {
            severity: sum(1 for warning in after.get("warnings", []) if warning.get("severity") == severity)
            - sum(1 for warning in before.get("warnings", []) if warning.get("severity") == severity)
            for severity in VALIDATION_SEVERITIES
        },
    }


def layout_from_room_dimensions(rooms: list[dict[str, Any]]) -> dict[str, Any]:
    layout = {"version": 1, "metadata": {"source_type": "manual_dimensions"}, "rooms": [], "items": []}
    cursor_x = 0.0
    for index, room in enumerate(rooms):
        width = max(0.1, _num(room.get("width_m"), 3.0))
        depth = max(0.1, _num(room.get("depth_m"), 3.0))
        label = _text(room.get("label") or room.get("name"), f"Room {index + 1}")
        room_id = _text(room.get("id"), label.lower().replace(" ", "_"))
        bounds = {"x_min": cursor_x, "z_min": 0.0, "x_max": cursor_x + width, "z_max": depth}
        layout["rooms"].append(
            {
                "id": room_id,
                "label": label,
                "kind": _text(room.get("kind"), "room"),
                "bounds": bounds,
                "confidence": "user_entered",
                "source": "manual_dimensions",
            }
        )
        height = max(2.2, _num(room.get("wall_height_m"), 2.6))
        wall_specs = [
            (cursor_x + width / 2, -0.05, width, 0.10),
            (cursor_x + width / 2, depth + 0.05, width, 0.10),
            (cursor_x - 0.05, depth / 2, 0.10, depth),
            (cursor_x + width + 0.05, depth / 2, 0.10, depth),
        ]
        for wall_index, (x, z, wall_width, wall_depth) in enumerate(wall_specs):
            layout["items"].append(
                {
                    "id": f"{room_id}-wall-{wall_index + 1}",
                    "type": "wall",
                    "name": f"{label} wall {wall_index + 1}",
                    "room": label,
                    "pos": [x, height / 2, z],
                    "geo": [wall_width, height, wall_depth],
                    "rot": 0,
                    "visible": True,
                    "confidence": "user_entered",
                    "source": "manual_dimensions",
                }
            )
        cursor_x += width + 0.4
    return migrate_layout(layout)


def import_warnings(layout: dict[str, Any], *, supported_schema_version: int = CURRENT_LAYOUT_SCHEMA_VERSION) -> list[str]:
    warnings: list[str] = []
    version = _num(layout.get("layout_schema_version"), 1)
    if version > supported_schema_version:
        warnings.append(f"Unsupported schema version {version:g}; attempting repair/migration.")
    calibration = layout.get("metadata", {}).get("calibration", {})
    if not isinstance(calibration, dict) or not calibration.get("scale_m_per_px"):
        warnings.append("Missing scale; measurements are estimated until calibrated.")
    catalog_refs = [
        item.get("catalog", {}).get("item_id")
        for item in layout.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("catalog"), dict)
    ]
    if any(not ref for ref in catalog_refs):
        warnings.append("Broken catalog reference found; item remains editable but product provenance is incomplete.")
    return warnings


def repair_layout(raw: Any) -> dict[str, Any]:
    warnings: list[str] = []
    if not isinstance(raw, dict):
        warnings.append("Input was not an object; created an empty layout.")
        raw = {}
    if "items" not in raw:
        warnings.append("Missing items array; created an empty one instead of dropping the import.")
    raw_version = _num(raw.get("layout_schema_version"), CURRENT_LAYOUT_SCHEMA_VERSION)
    if raw_version > CURRENT_LAYOUT_SCHEMA_VERSION:
        warnings.append(f"Unsupported schema version {raw_version:g}; attempting repair/migration.")
    repaired = migrate_layout(raw)
    warnings.extend(import_warnings(repaired))
    return {"ok": True, "layout": repaired, "warnings": warnings}


def import_haus_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        parsed = json.loads(raw)
    else:
        parsed = raw
    if isinstance(parsed, dict) and parsed.get("schema") == PROJECT_SCHEMA_ID:
        project = copy.deepcopy(parsed)
        project["layout"] = migrate_layout(project.get("layout", {}))
        project["scenarios"] = project.get("scenarios") if isinstance(project.get("scenarios"), list) else []
        return {"kind": "project", "project": project, "layout": project["layout"], "warnings": import_warnings(project["layout"])}
    repaired = repair_layout(parsed)
    layout = repaired["layout"]
    if isinstance(parsed, dict) and isinstance(parsed.get("scenarios"), list):
        layout["scenarios"] = parsed["scenarios"]
    return {"kind": "layout", "layout": layout, "warnings": repaired["warnings"]}


def export_scenario_json(scenario: dict[str, Any]) -> str:
    return json.dumps({"schema": "haus.scenario.v1", "scenario": scenario}, indent=2, sort_keys=True)


def validation_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Validation Report: {report.get('journey', 'Haus')}",
        "",
        f"Generated: {report.get('generated_at', '')}",
        "",
        "## Warnings",
    ]
    if not report.get("warnings"):
        lines.append("- No warnings.")
    for warning in report.get("warnings", []):
        lines.append(f"- [{warning.get('severity')}] {warning.get('message')} Suggested fix: {warning.get('suggested_fix')}")
    if report.get("confidence_explanations"):
        lines.extend(["", "## Confidence"])
        lines.extend(f"- {item['message']} {item['fix']}" for item in report["confidence_explanations"])
    lines.extend(["", "## Disclaimers"])
    lines.extend(f"- {item}" for item in report.get("disclaimers", [PRODUCT_SAFE_DISCLAIMER]))
    return "\n".join(lines) + "\n"


def report_filename(project_title: str, journey: str, scenario: str, date: str | None = None, extension: str = "html") -> str:
    day = date or _now_iso()[:10]
    parts = [_slug_filename(project_title), _slug_filename(journey), _slug_filename(scenario), day]
    return "-".join(part for part in parts if part).strip("-") + f".{extension.lstrip('.')}"


def _slug_filename(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")


def selected_scenarios(project: dict[str, Any], selected_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    scenarios = [scenario for scenario in project.get("scenarios", []) if isinstance(scenario, dict)]
    wanted = set(selected_ids or [])
    if wanted:
        return [scenario for scenario in scenarios if scenario.get("id") in wanted]
    return [scenario for scenario in scenarios if scenario.get("status") in {"applied", "selected", "exported"}] or scenarios[:1]


def report_components(
    project: dict[str, Any],
    report: dict[str, Any],
    *,
    selected_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    scenarios = selected_scenarios(project, selected_ids)
    return {
        "title_page": {
            "title": project.get("title", "Haus Report"),
            "journey": report.get("journey", project.get("journey", "blank")),
            "generated_at": report.get("generated_at", _now_iso()),
            "disclaimers": report.get("disclaimers", [PRODUCT_SAFE_DISCLAIMER]),
        },
        "project_summary": {
            "intake": project.get("intake", {}),
            "source_file": redact_client_paths(str(project.get("source_file") or "")),
            "unknown_count": len(report.get("unknowns", [])),
        },
        "scenario_table": [
            {
                "id": scenario.get("id"),
                "name": scenario.get("name"),
                "status": scenario.get("status"),
                "score": scenario.get("score", {}),
            }
            for scenario in scenarios
        ],
        "annotated_plan": {"status": "attach_exported_snapshot", "overlays": report.get("overlays", {})},
        "warnings": report.get("warnings", []),
        "assumptions": project.get("assumptions", []),
        "next_steps": [
            "Confirm scale, openings, and locked fixtures on site.",
            "Review serious and blocked warnings before buying furniture or renovating.",
            "Export or email the static report after selecting a scenario.",
        ],
    }


def report_preview(project: dict[str, Any], report: dict[str, Any], *, selected_ids: Iterable[str] | None = None) -> dict[str, Any]:
    components = report_components(project, report, selected_ids=selected_ids)
    return {
        "filename": report_filename(project.get("title", "haus"), report.get("journey", project.get("journey", "blank")), components["scenario_table"][0]["name"] if components["scenario_table"] else "report"),
        "sections": list(components.keys()),
        "selected_scenario_count": len(components["scenario_table"]),
        "warning_count": len(components["warnings"]),
        "disclaimers": components["title_page"]["disclaimers"],
    }


def render_journey_report(
    project: dict[str, Any],
    journey: str,
    report: dict[str, Any] | None = None,
    *,
    selected_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    active_report = report or build_validation_report(project.get("layout", {}), journey=journey)
    components = report_components(project, active_report, selected_ids=selected_ids)
    scenario_name = components["scenario_table"][0]["name"] if components["scenario_table"] else "report"
    title = {
        "renovation": "Renovation Concept Pack",
        "accessibility": "Home Accessibility Planning Review",
        "furniture_fit": "Furniture Fit Report",
        "designer": "Designer Pre-Sales Pack",
    }.get(journey, "Haus Planning Report")
    export_project = {**project, "title": f"{project.get('title', 'Haus')} - {title}"}
    html_report = build_html_report(export_project, active_report, selected_ids=[row["id"] for row in components["scenario_table"] if row.get("id")])
    return {
        "title": title,
        "journey": journey,
        "filename": report_filename(project.get("title", "haus"), journey, str(scenario_name)),
        "components": components,
        "preview": report_preview(project, active_report, selected_ids=selected_ids),
        "html": html_report,
    }


def export_project_bundle(
    project: dict[str, Any],
    destination: Path,
    *,
    reports: dict[str, str] | None = None,
    screenshots: dict[str, bytes] | None = None,
    source_images: dict[str, bytes] | None = None,
    catalog_cache: dict[str, Any] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("layout.json", json.dumps(project.get("layout", {}), indent=2))
        zf.writestr("project.json", json.dumps(project, indent=2, default=str))
        for name, text in (reports or {}).items():
            zf.writestr(f"reports/{_slug_filename(name) or 'report'}.html", text)
        for name, data in (screenshots or {}).items():
            zf.writestr(f"screenshots/{_slug_filename(name) or 'snapshot'}.png", data)
        for name, data in (source_images or {}).items():
            zf.writestr(f"source-images/{Path(name).name}", data)
        zf.writestr("catalog/cache.json", json.dumps(catalog_cache or {}, indent=2))
    return destination


def redact_client_paths(text: str) -> str:
    text = re.sub(r"(?<!\w)/(?:[^/\s]+/)+([^/\s]+)", r"[redacted]/\1", text)
    text = re.sub(r"[A-Za-z]:\\(?:[^\\\s]+\\)+([^\\\s]+)", r"[redacted]\\\1", text)
    return text


def designer_intake_schema() -> dict[str, Any]:
    return {
        "client_name": "",
        "project_type": "",
        "design_brief": "",
        "style_words": [],
        "budget_band": "",
        "timeline": "",
        "meeting_date": "",
    }


def client_brief_object(
    intake: dict[str, Any],
    *,
    goals: list[str] | None = None,
    constraints: list[str] | None = None,
    assumptions: list[str] | None = None,
    unanswered_questions: list[str] | None = None,
    selected_scenario: str | None = None,
) -> dict[str, Any]:
    base = {**designer_intake_schema(), **(intake or {})}
    return {
        "schema": "haus.client_brief.v1",
        "client_name": _text(base.get("client_name"), "Client"),
        "project_type": _text(base.get("project_type"), "Residential concept"),
        "design_brief": _text(base.get("design_brief"), "Pre-sales planning brief"),
        "style_words": base.get("style_words") if isinstance(base.get("style_words"), list) else _text(base.get("style_words")).split(","),
        "budget_band": _text(base.get("budget_band"), "unknown"),
        "timeline": _text(base.get("timeline"), "unknown"),
        "meeting_date": _text(base.get("meeting_date")),
        "goals": goals or [_text(base.get("design_brief"), "Clarify desired outcome")],
        "constraints": constraints or ["Measurements, scale, and fixed services need confirmation."],
        "assumptions": assumptions or ["Concept planning only until site verification."],
        "unanswered_questions": unanswered_questions or [
            "Which measurements are confirmed?",
            "Which existing fixtures or furniture must stay?",
            "What budget band and timeline should shape option selection?",
        ],
        "selected_scenario": selected_scenario,
    }


def lead_qualification_summary(brief: dict[str, Any], validation_report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = validation_report or {"warnings": []}
    serious = [warning for warning in report.get("warnings", []) if warning.get("severity") in {"serious", "blocked"}]
    return {
        "client_needs": brief.get("goals", []),
        "spatial_risks": [warning.get("message") for warning in serious] or ["No serious spatial risks found yet; confirm measurements."],
        "likely_scope": [
            "concept planning",
            "measurement verification",
            "furniture/layout option review",
            "professional review for structural, plumbing, electrical, stair, or clinical needs",
        ],
        "follow_up_questions": brief.get("unanswered_questions", []),
    }


def branded_report_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = settings or {}
    accent = _text(raw.get("accent_color"), "#2563eb")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = "#2563eb"
    return {
        "logo": _text(raw.get("logo")),
        "business_name": _text(raw.get("business_name"), "Haus Studio"),
        "contact": _text(raw.get("contact")),
        "accent_color": accent,
        "footer_disclaimer": _text(raw.get("footer_disclaimer"), PRODUCT_SAFE_DISCLAIMER),
    }


def mood_board_placeholder() -> dict[str, Any]:
    return {
        "reference_images": [],
        "product_cards": [],
        "style_notes": [],
        "material_notes": [],
        "status": "placeholder",
    }


def proposal_outline_export(brief: dict[str, Any], selected_scenario: dict[str, Any] | None = None) -> str:
    scenario_name = selected_scenario.get("name", "selected scenario") if selected_scenario else "selected scenario"
    lines = [
        "# Proposal Outline",
        "",
        "## Scope",
        f"- Prepare concept options for {brief.get('project_type', 'residential project')}.",
        f"- Review {scenario_name} against assumptions and spatial warnings.",
        "",
        "## Assumptions",
    ]
    lines.extend(f"- {item}" for item in brief.get("assumptions", []))
    lines.extend(
        [
            "",
            "## Exclusions",
            "- BIM authoring, permit drawings, contractor-ready documentation, medical advice, code certification, and site verification.",
            "",
            "## Optional Add-ons",
            "- Site measurement visit",
            "- Product sourcing shortlist",
            "- Contractor or architect coordination pack",
            "",
            "## Next Steps",
            "- Confirm open questions.",
            "- Select scenario direction.",
            "- Verify measurements and fixed constraints.",
        ]
    )
    return "\n".join(lines) + "\n"


def client_questions_export(brief: dict[str, Any]) -> dict[str, list[str]]:
    base_questions = list(brief.get("unanswered_questions", []))
    return {
        "measurements": ["Can you confirm the scale, door widths, ceiling height, and key room dimensions?", *base_questions[:1]],
        "preferences": ["Which style words matter most?", "What must the plan avoid?"],
        "budget": ["What is the comfortable budget band?", "Which add-ons are optional?"],
        "household_routines": ["Who uses each room daily?", "Any night-route, caregiver, pet, child, or work-from-home routines?"],
        "constraints": ["Which walls, windows, services, fixtures, and furniture are locked?", "Are there building rules or landlord limits?"],
    }


def append_revision_log(project: dict[str, Any], from_option: str, to_option: str, reason: str) -> dict[str, Any]:
    entry = {
        "id": f"revision-{uuid.uuid4().hex[:8]}",
        "created_at": _now_iso(),
        "from": from_option,
        "to": to_option,
        "reason": reason,
    }
    project.setdefault("revision_log", []).append(entry)
    return entry


def design_call_script_export(brief: dict[str, Any], scenarios: list[dict[str, Any]]) -> str:
    lines = [
        "# Design Call Script",
        "",
        f"Client: {brief.get('client_name', 'Client')}",
        "",
        "## Opening",
        "- Confirm goals, budget band, timeline, and unanswered questions.",
        "",
        "## Plan Options",
    ]
    for scenario in scenarios:
        lines.append(f"- Walk through {scenario.get('name', 'Scenario')}: status {scenario.get('status', 'draft')}; confidence {scenario.get('score', {}).get('confidence', 'unknown')}.")
    lines.extend(["", "## Warnings", "- Explain serious warnings without exposing internal tool logs.", "", "## Close", "- Agree next measurements, decision owner, and follow-up date."])
    return "\n".join(lines) + "\n"


def screenshot_templates() -> list[dict[str, str]]:
    return [
        {"id": "whole_flat", "label": "Whole flat", "camera": "top", "overlay": "all"},
        {"id": "room_close_up", "label": "Room close-up", "camera": "room", "overlay": "selected_room"},
        {"id": "warning_overlay", "label": "Warning overlay", "camera": "top", "overlay": "warnings"},
        {"id": "selected_scenario", "label": "Selected scenario", "camera": "top", "overlay": "scenario"},
    ]


def client_safe_text(text: str) -> str:
    text = re.sub(r"Tool-call trace:.*?(?:\n\n|$)", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\b(?:args|elapsed_ms|request_id|raw_plan)\b[:=][^\n]*", "", text, flags=re.IGNORECASE)
    return redact_client_paths(text).strip()


def designer_static_report(
    project: dict[str, Any],
    brief: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
) -> str:
    brand = branded_report_settings(settings)
    report = validation_report or build_validation_report(project.get("layout", {}), journey="designer")
    qualification = lead_qualification_summary(brief, report)
    accent = html.escape(brand["accent_color"])
    lines = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(project.get('title', 'Designer Pre-Sales Pack'))}</title>",
        f"<style>body{{font-family:system-ui,sans-serif;margin:32px;color:#1f2937}}h1,h2{{color:{accent}}}.risk{{border-left:4px solid {accent};padding:8px 12px;background:#f8fafc}}</style>",
        "</head><body>",
        f"<h1>{html.escape(brand['business_name'])}</h1>",
        f"<p>{html.escape(brand['contact'])}</p>",
        f"<h2>{html.escape(brief.get('client_name', 'Client'))}: Designer Pre-Sales Pack</h2>",
        "<h2>Client Needs</h2><ul>",
        *(f"<li>{html.escape(client_safe_text(item))}</li>" for item in qualification["client_needs"]),
        "</ul><h2>Spatial Risks</h2>",
        *(f"<div class='risk'>{html.escape(client_safe_text(item))}</div>" for item in qualification["spatial_risks"]),
        "<h2>Follow-up Questions</h2><ul>",
        *(f"<li>{html.escape(client_safe_text(item))}</li>" for item in qualification["follow_up_questions"]),
        "</ul>",
        f"<footer>{html.escape(brand['footer_disclaimer'])}</footer>",
        "</body></html>",
    ]
    return "\n".join(lines)


def designer_project_folder(runtime_root: Path, client_name: str, project_title: str) -> Path:
    folder = runtime_root / "clients" / _slug_filename(client_name or "client") / _slug_filename(project_title or "project")
    for child in ("reports", "screenshots", "source", "catalog"):
        (folder / child).mkdir(parents=True, exist_ok=True)
    return folder
