"""Tests for src/haus/case/design_agent.py — SPEC-HTTP-CASE.md sections 2.8, 4.2, 6."""
from __future__ import annotations

import pytest

from haus.case.design_agent import DesignAgent, PinnedProposalNotFound
from haus.case.ingest import load_case_from_library

LIBRARY_3 = "corpus/library/3.json"
PROPOSALS_DIR = "tests/fixtures/proposals"
BRIEF = {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist",
    "constraints": [],
    "must_keep_rooms": [],
}


def test_pinned_proposal_loads_and_replaces_items():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    case = agent.propose(case)
    assert case["design_status"] == "compliance_pending"
    # wall_28 removed by the pinned proposal -> 112 items (was 113)
    assert len(case["items"]) == 112
    assert all(it.get("name") != "wall_28" for it in case["items"])


def test_pinned_proposal_is_deterministic():
    # SPEC section 6: "if non-null, /design MUST be deterministic for this Case"
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    a = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    a = agent.propose(a)
    b = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    b = agent.propose(b)
    assert a["items"] == b["items"]


def test_clean_pinned_proposal_keeps_all_walls():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_keep_walls")
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    case = agent.propose(case)
    assert len(case["items"]) == 113


def test_missing_pinned_proposal_raises():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="does_not_exist")
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    with pytest.raises(PinnedProposalNotFound):
        agent.propose(case)


def test_pinned_proposal_id_set_without_proposals_dir_raises():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="anything")
    agent = DesignAgent(proposals_dir=None)
    with pytest.raises(PinnedProposalNotFound):
        agent.propose(case)


def test_deterministic_fallback_preserves_walls_and_adds_furniture():
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)  # no pinned_proposal_id
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    case = agent.propose(case)
    assert case["design_status"] == "compliance_pending"
    walls = [it for it in case["items"] if it.get("type") == "wall"]
    furniture = [it for it in case["items"] if it.get("type") == "furniture"]
    assert len(walls) == 113  # all walls preserved
    assert len(furniture) > 0  # plan_room produced items


def test_pinned_proposal_path_isolates_items_from_disk_payload():
    # mutating the returned case must not corrupt the on-disk proposal
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    a = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    a = agent.propose(a)
    a["items"].clear()
    b = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    b = agent.propose(b)
    assert len(b["items"]) == 112
