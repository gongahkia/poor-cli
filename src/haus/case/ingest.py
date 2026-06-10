"""Case ingest: corpus/library/*.json -> Renovation Design Case payload.

Per SPEC-HTTP-CASE.md sections 2 and 3:
- Base shape is corpus library JSON (version, metadata, rooms[], items[]).
- Added top-level keys per SPEC section 2.2.
- hdb_type enrichment for wall items via inverse of mesh._COLOR_BY_HDB
  (SPEC section 3 prerequisite, library-side enrichment path).
- Baseline snapshot of structural/shelter walls stashed under _baseline_protected_walls
  so the compliance rule can diff current items[] against the original protected set.
  The underscore prefix marks this as an implementation detail not in the public schema.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..mesh import _COLOR_BY_HDB

# inverse of mesh._COLOR_BY_HDB: 24-bit packed RGB -> hdb_type
# (color encodes hdb_type in viewer/library JSON; see SPEC section 3 callout)
_HDB_BY_COLOR: dict[int, str] = {
    (r << 16) | (g << 8) | b: hdb
    for hdb, (r, g, b, _a) in _COLOR_BY_HDB.items()
}

PROTECTED_HDB_TYPES = frozenset({"structural", "shelter"})

CASE_SCHEMA_VERSION = 1


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _enrich_wall_hdb_type(item: dict[str, Any]) -> dict[str, Any]:
    """Add hdb_type to a wall item by inverting its color encoding.

    Non-wall items pass through unchanged. Walls with an unrecognised color
    get hdb_type=None — the structural_wall_protected rule fails open on null
    (see SPEC section 3 safety paragraph).
    """
    if item.get("type") != "wall":
        return item
    if "hdb_type" in item:  # already enriched (or set explicitly upstream)
        return item
    color = item.get("color")
    if isinstance(color, int):
        item = {**item, "hdb_type": _HDB_BY_COLOR.get(color)}
    else:
        item = {**item, "hdb_type": None}
    return item


def enrich_wall_hdb_types(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of layout items with explicit hdb_type on wall items."""
    return [_enrich_wall_hdb_type(dict(it)) for it in items if isinstance(it, dict)]


def _object_list(raw: Any, name: str, path: Path) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"Library JSON field {name!r} must be an array: {path}")
    out: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Library JSON field {name!r}[{index}] must be an object: {path}")
        out.append(dict(item))
    return out


def _metadata(raw: Any, path: Path) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Library JSON field 'metadata' must be an object: {path}")
    return dict(raw)


def _baseline_protected_walls(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Snapshot of {name, hdb_type, pos, geo} for walls that compliance must protect."""
    baseline: list[dict[str, Any]] = []
    for it in items:
        if it.get("type") != "wall":
            continue
        if it.get("hdb_type") not in PROTECTED_HDB_TYPES:
            continue
        name = it.get("name")
        if not name:
            continue  # SPEC section 2.4: name is canonical identity; unnamed walls cannot be tracked
        baseline.append({
            "name": name,
            "hdb_type": it["hdb_type"],
            "pos": list(it.get("pos", [])),
            "geo": list(it.get("geo", [])),
        })
    return baseline


def load_case_from_library(
    library_path: str | Path,
    brief: dict[str, Any],
    *,
    case_id: str | None = None,
    pinned_proposal_id: str | None = None,
    vendor_cache_key: str | None = None,
) -> dict[str, Any]:
    """Build a Renovation Design Case from a corpus/library/*.json file.

    Implements POST /case (library path branch) per SPEC section 4.2:
    - Mints a new case_id (UUID v4) unless one is supplied.
    - Enriches every wall item with hdb_type via the inverse color map.
    - Snapshots baseline structural/shelter walls for the compliance rule.
    - Returns the Case at design_status='intake'. The HTTP layer auto-advances
      to 'designing' on the same call; that transition is the Design Agent's job
      (this function stays focused on schema construction).
    """
    path = Path(library_path)
    if not path.exists():
        raise FileNotFoundError(f"Library JSON not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict):
        raise ValueError(f"Library JSON root must be an object: {path}")

    items = enrich_wall_hdb_types(_object_list(raw.get("items"), "items", path))
    rooms = _object_list(raw.get("rooms"), "rooms", path)
    baseline_items = json.loads(json.dumps(items))

    metadata = _metadata(raw.get("metadata"), path)
    metadata.setdefault("source_library", str(path))

    now = _utcnow_iso()
    case: dict[str, Any] = {
        "version": raw.get("version", 1),
        "case_schema_version": CASE_SCHEMA_VERSION,
        "case_id": case_id or str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
        "design_status": "intake",
        "revise_count": 0,
        "pinned_proposal_id": pinned_proposal_id,
        "vendor_cache_key": vendor_cache_key,
        "brief": dict(brief),
        "metadata": metadata,
        "rooms": rooms,
        "items": items,
        "compliance_findings": [],
        "approval_state": None,
        "vendor_handoff": None,
        "_baseline_items": baseline_items,
        "_baseline_protected_walls": _baseline_protected_walls(items),
    }
    return case


def touch(case: dict[str, Any]) -> dict[str, Any]:
    """Bump updated_at. Called by every mutating endpoint per SPEC section 4.3 rule 4."""
    case["updated_at"] = _utcnow_iso()
    return case
