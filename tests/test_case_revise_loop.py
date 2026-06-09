"""Tests for src/haus/case/revise_loop.py — SPEC-HTTP-CASE.md sections 4.2/4.4 + Appendix A.

The integration test (test_appendix_a_round_trip) is the canonical proof that
the implementation matches the contract walkthrough.
"""
from __future__ import annotations

import pytest

from haus.case import (
    DesignAgent,
    InvalidStateTransition,
    ReviseLoop,
    load_case_from_library,
    patch_approval,
    step_compliance,
    step_design,
    step_revise,
)

LIBRARY_3 = "corpus/library/3.json"
PROPOSALS_DIR = "tests/fixtures/proposals"
BRIEF = {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist",
    "constraints": [],
    "must_keep_rooms": [],
}


def _make(pinned: str | None) -> tuple[dict, ReviseLoop]:
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id=pinned)
    return case, ReviseLoop(DesignAgent(proposals_dir=PROPOSALS_DIR), max_revise=3)


def test_appendix_a_round_trip():
    """SPEC Appendix A: 10-step lifecycle from create -> approved via N=3 escalation."""
    case, loop = _make(pinned="demo_3room_remove_wall_28")
    assert case["design_status"] == "intake" and case["revise_count"] == 0

    case = loop.design(case)
    assert case["design_status"] == "compliance_pending" and case["revise_count"] == 0

    case = loop.compliance(case)
    assert case["design_status"] == "revising"
    assert len(case["compliance_findings"]) == 1
    assert case["compliance_findings"][0]["element_name"] == "wall_28"

    for expected_count in (1, 2, 3):
        case = loop.revise(case)
        assert case["design_status"] == "compliance_pending"
        assert case["revise_count"] == expected_count

        case = loop.compliance(case)
        if expected_count < 3:
            assert case["design_status"] == "revising"
        else:
            assert case["design_status"] == "awaiting_human_approval"
            assert case["approval_state"] is not None
            assert "Auto-revise exhausted" in case["approval_state"]["escalation_reason"]

    case = patch_approval(case, decision="approved", reviewer="coordinator_alice", notes="ok")
    assert case["design_status"] == "approved"
    assert case["approval_state"]["reviewer"] == "coordinator_alice"
    assert case["approval_state"]["decided_at"] is not None


def test_clean_design_goes_straight_to_human_approval():
    case, loop = _make(pinned="demo_3room_keep_walls")
    case = loop.design(case)
    case = loop.compliance(case)
    assert case["design_status"] == "awaiting_human_approval"
    assert case["compliance_findings"] == []
    # SPEC 2.5: escalation_reason is None on the clean path
    assert case["approval_state"]["escalation_reason"] is None


def test_run_to_human_drives_full_loop():
    case, loop = _make(pinned="demo_3room_remove_wall_28")
    case = loop.run_to_human(case)
    assert case["design_status"] == "awaiting_human_approval"
    assert case["revise_count"] == 3


def test_invalid_state_transition_raises_on_wrong_prestate():
    case, loop = _make(pinned="demo_3room_remove_wall_28")
    # cannot run compliance before design
    with pytest.raises(InvalidStateTransition):
        loop.compliance(case)
    # cannot revise before there are findings (status is intake)
    with pytest.raises(InvalidStateTransition):
        loop.revise(case, findings=[])
    # cannot approve before reaching awaiting_human_approval
    with pytest.raises(InvalidStateTransition):
        patch_approval(case, decision="approved", reviewer="x")


def test_revise_increment_count_false_does_not_advance_counter():
    case, loop = _make(pinned="demo_3room_remove_wall_28")
    case = loop.design(case)
    case = loop.compliance(case)
    assert case["revise_count"] == 0
    case = loop.revise(case, increment_count=False)
    assert case["revise_count"] == 0


def test_revise_consumes_findings_as_hints():
    # The Design Agent's pinned path ignores hints, but the revise call must accept
    # them as input (SPEC 4.2 — findings list passed explicitly so caller can replay).
    case, loop = _make(pinned="demo_3room_remove_wall_28")
    case = loop.design(case)
    case = loop.compliance(case)
    case = loop.revise(case, findings=case["compliance_findings"])
    assert case["design_status"] == "compliance_pending"


def test_n_can_be_overridden_for_demo():
    # SPEC 4.4: "Demo script may override to N=1 to force fast escalation."
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    loop = ReviseLoop(DesignAgent(proposals_dir=PROPOSALS_DIR), max_revise=1)
    case = loop.run_to_human(case)
    assert case["revise_count"] == 1
    assert case["design_status"] == "awaiting_human_approval"


def test_step_functions_are_callable_independent_of_orchestrator():
    # The HTTP layer will call step_design / step_compliance / step_revise directly.
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    case = step_design(case, agent)
    case = step_compliance(case, max_revise=3)
    assert case["design_status"] == "revising"
    case = step_revise(case, findings=case["compliance_findings"], design_agent=agent)
    assert case["revise_count"] == 1
