"""Tests for src/haus/case/ingest.py — SPEC-HTTP-CASE.md sections 2 and 3."""
from __future__ import annotations

from collections import Counter

import pytest

from haus.case.ingest import (
    CASE_SCHEMA_VERSION,
    PROTECTED_HDB_TYPES,
    _HDB_BY_COLOR,
    load_case_from_library,
    touch,
)

LIBRARY_3 = "corpus/library/3.json"
BRIEF = {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist",
    "constraints": [],
    "must_keep_rooms": [],
}


def test_inverse_color_map_covers_all_hdb_types():
    assert set(_HDB_BY_COLOR.values()) == {"ferrolite", "partition", "structural", "shelter"}
    # spot-check the demo-fixture shelter color
    assert _HDB_BY_COLOR[7874600] == "shelter"


def test_load_case_returns_spec_shape():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    # SPEC section 2.2 required top-level keys
    for key in [
        "version", "case_schema_version", "case_id", "created_at", "updated_at",
        "brief", "design_status", "revise_count", "compliance_findings",
        "approval_state", "vendor_handoff", "pinned_proposal_id", "vendor_cache_key",
        "metadata", "rooms", "items",
    ]:
        assert key in case, f"missing top-level key {key!r}"
    assert case["case_schema_version"] == CASE_SCHEMA_VERSION
    assert case["design_status"] == "intake"
    assert case["revise_count"] == 0
    assert case["compliance_findings"] == []
    assert case["approval_state"] is None
    assert case["vendor_handoff"] is None


def test_load_case_enriches_wall_28_with_shelter_hdb_type():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    wall_28 = next(it for it in case["items"] if it.get("name") == "wall_28")
    assert wall_28["hdb_type"] == "shelter"


def test_load_case_carries_full_baseline_items_for_viewer_diff():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    assert case["_baseline_items"] == case["items"]
    assert case["_baseline_items"] is not case["items"]
    baseline_wall_28 = next(it for it in case["_baseline_items"] if it.get("name") == "wall_28")
    assert baseline_wall_28["hdb_type"] == "shelter"


def test_baseline_protected_walls_matches_known_counts():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    baseline = case["_baseline_protected_walls"]
    by_type = Counter(b["hdb_type"] for b in baseline)
    # corpus/library/3.json has 15 structural + 3 shelter; verified out-of-band
    assert by_type == {"structural": 15, "shelter": 3}
    assert all(b["hdb_type"] in PROTECTED_HDB_TYPES for b in baseline)
    assert all(b["name"] for b in baseline)  # SPEC 2.4: name is canonical identity


def test_load_case_accepts_pinned_proposal_id():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="x")
    assert case["pinned_proposal_id"] == "x"


def test_load_case_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_case_from_library("corpus/library/does_not_exist.json", brief=BRIEF)


def test_touch_bumps_updated_at():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    case["updated_at"] = "2000-01-01T00:00:00Z"  # known-older value
    touch(case)
    assert case["updated_at"] != "2000-01-01T00:00:00Z"
