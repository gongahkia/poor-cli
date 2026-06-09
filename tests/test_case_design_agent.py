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
    wall_0 = next(it for it in case["items"] if it.get("name") == "wall_0")
    assert wall_0["hdb_type"] == "structural"
    assert case["design_agent_trace"]["source"] == "pinned"


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
    assert case["design_agent_trace"]["source"] == "deterministic"


def test_live_mode_applies_mocked_structured_operations(monkeypatch):
    import haus.chat_server as chat_server

    def fake_chat(api_key, messages, model, dispatch):
        assert api_key == "test-key"
        assert model == "mock-model"
        assert "protected_walls" in messages[0]["content"]
        return (
            '{"operations":[{"action":"add_item","item":{'
            '"type":"furniture","furnitureType":"desk","name":"live_desk",'
            '"pos":[0,0.375,0],"rot":0,"visible":true,"geo":[1.2,0.75,0.6],'
            '"color":8947848}}]}'
        ), []

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(chat_server, "_CHAT_FNS", {**chat_server._CHAT_FNS, "openai": fake_chat})

    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    agent = DesignAgent(
        proposals_dir=PROPOSALS_DIR,
        mode="live",
        provider="openai",
        model="mock-model",
    )
    case = agent.propose(case)

    assert any(item.get("name") == "live_desk" for item in case["items"])
    assert case["design_agent_trace"]["source"] == "live"


def test_live_mode_falls_back_to_deterministic_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR, mode="live", provider="openai")
    case = agent.propose(case)

    assert case["design_agent_trace"]["source"] == "deterministic"
    assert "OPENAI_API_KEY" in case["design_agent_trace"]["fallback_reason"]
    assert any(item.get("type") == "furniture" for item in case["items"])


def test_pinned_proposal_path_isolates_items_from_disk_payload():
    # mutating the returned case must not corrupt the on-disk proposal
    agent = DesignAgent(proposals_dir=PROPOSALS_DIR)
    a = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    a = agent.propose(a)
    a["items"].clear()
    b = load_case_from_library(LIBRARY_3, brief=BRIEF, pinned_proposal_id="demo_3room_remove_wall_28")
    b = agent.propose(b)
    assert len(b["items"]) == 112
