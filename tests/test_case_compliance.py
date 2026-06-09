"""Tests for src/haus/case/compliance.py — SPEC-HTTP-CASE.md section 5."""
from __future__ import annotations

from haus.case.compliance import (
    SEVERITY_ERROR,
    has_errors,
    rule_structural_wall_protected,
    rule_walkway_accessibility,
    run_compliance,
)
from haus.case.ingest import load_case_from_library

LIBRARY_3 = "corpus/library/3.json"
BRIEF = {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist",
    "constraints": [],
    "must_keep_rooms": [],
}


def _fresh_case():
    return load_case_from_library(LIBRARY_3, brief=BRIEF)


def test_clean_case_has_no_findings():
    case = _fresh_case()
    assert run_compliance(case) == []
    assert not has_errors([])


def test_removing_shelter_wall_28_fires_structural_rule():
    case = _fresh_case()
    case["items"] = [it for it in case["items"] if it.get("name") != "wall_28"]
    findings = rule_structural_wall_protected(case)
    assert len(findings) == 1
    f = findings[0]
    assert f["rule_id"] == "structural_wall_protected"
    assert f["severity"] == SEVERITY_ERROR
    assert f["element_name"] == "wall_28"
    assert f["machine_hint"]["action"] == "do_not_remove"
    assert f["machine_hint"]["hdb_type"] == "shelter"
    # SPEC 2.4: machine_hint is what the planner consumes programmatically
    assert "alternative" in f["machine_hint"]


def test_removing_partition_wall_does_not_fire_structural_rule():
    case = _fresh_case()
    # any partition wall (color 9211040 maps to partition)
    partition_name = next(
        it["name"] for it in case["items"] if it.get("color") == 9211040 and it.get("name")
    )
    case["items"] = [it for it in case["items"] if it.get("name") != partition_name]
    assert rule_structural_wall_protected(case) == []


def test_removing_multiple_protected_walls_fires_multiple_findings():
    case = _fresh_case()
    # remove all 3 shelter walls
    shelter_names = [b["name"] for b in case["_baseline_protected_walls"] if b["hdb_type"] == "shelter"]
    assert len(shelter_names) == 3
    case["items"] = [it for it in case["items"] if it.get("name") not in shelter_names]
    findings = rule_structural_wall_protected(case)
    assert len(findings) == 3
    assert {f["element_name"] for f in findings} == set(shelter_names)


def test_walkway_rule_clean_when_no_furniture():
    case = _fresh_case()
    assert rule_walkway_accessibility(case) == []


def test_walkway_rule_fires_on_blocking_furniture():
    case = _fresh_case()
    # huge wardrobe at the living-dining boundary midpoint
    case["items"].append({
        "type": "furniture",
        "name": "blocking_wardrobe",
        "pos": [0.67, 0.5, 2.4],
        "rot": 0.0,
        "visible": True,
        "geo": [2.5, 2.0, 2.5],
        "color": 8000000,
    })
    findings = rule_walkway_accessibility(case)
    assert len(findings) >= 1
    blocked = [f for f in findings if f["coords"]["from_room"] == "living" and f["coords"]["to_room"] == "dining"]
    assert blocked, "expected a living->dining walkway finding"
    f = blocked[0]
    assert f["severity"] == SEVERITY_ERROR
    assert f["machine_hint"]["action"] == "do_not_block_walkway"


def test_run_compliance_concatenates_all_rules():
    case = _fresh_case()
    # remove wall_28 AND add a blocking wardrobe -> both rules fire
    case["items"] = [it for it in case["items"] if it.get("name") != "wall_28"]
    case["items"].append({
        "type": "furniture", "name": "blocking_wardrobe", "pos": [0.67, 0.5, 2.4],
        "rot": 0.0, "visible": True, "geo": [2.5, 2.0, 2.5], "color": 8000000,
    })
    findings = run_compliance(case)
    rule_ids = {f["rule_id"] for f in findings}
    assert "structural_wall_protected" in rule_ids
    assert "walkway_accessibility" in rule_ids
    assert has_errors(findings)


def test_compliance_is_idempotent():
    # SPEC 4.2: idempotent (pure read over current items + rules; same input -> same findings).
    case = _fresh_case()
    case["items"] = [it for it in case["items"] if it.get("name") != "wall_28"]
    a = run_compliance(case)
    b = run_compliance(case)
    assert a == b


def test_finding_is_replayable_into_revise():
    # SPEC 5.3: findings replay contract — the output of /compliance is a valid
    # input for /revise unchanged. Verify the shape carries machine_hint.
    case = _fresh_case()
    case["items"] = [it for it in case["items"] if it.get("name") != "wall_28"]
    findings = run_compliance(case)
    for f in findings:
        if f["severity"] == SEVERITY_ERROR:
            assert isinstance(f.get("machine_hint"), dict)
            assert "action" in f["machine_hint"]
