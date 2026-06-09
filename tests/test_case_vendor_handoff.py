"""Tests for the Stage-1 Vendor/Handoff Agent."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

from haus.case import InvalidStateTransition, load_case_from_library, patch_approval
from haus.case.vendor_handoff import (
    DEFAULT_VENDOR_CACHE_KEY,
    VendorCacheError,
    VendorHandoffAgent,
    step_handoff,
)


LIBRARY_3 = "corpus/library/3.json"
VENDORS_DIR = "tests/fixtures/vendors"
BRIEF = {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist",
    "constraints": [],
    "must_keep_rooms": [],
}


def _approved_case() -> dict:
    case = load_case_from_library(
        LIBRARY_3,
        brief=BRIEF,
        vendor_cache_key=DEFAULT_VENDOR_CACHE_KEY,
    )
    case["design_status"] = "awaiting_human_approval"
    case["approval_state"] = {
        "decision": "pending",
        "reviewer": None,
        "decided_at": None,
        "notes": None,
        "escalation_reason": None,
    }
    return patch_approval(case, decision="approved", reviewer="coordinator_alice")


def _packet_path(packet_uri: str) -> Path:
    parsed = urlparse(packet_uri)
    assert parsed.scheme == "file"
    return Path(parsed.path)


def test_cached_vendor_handoff_writes_packet_zip(tmp_path: Path) -> None:
    case = _approved_case()
    agent = VendorHandoffAgent(vendor_cache_dir=VENDORS_DIR, handoff_root=tmp_path)

    case = step_handoff(case, handoff_agent=agent)

    assert case["design_status"] == "handoff_complete"
    assert case["vendor_handoff"]["cached"] is True
    assert case["vendor_handoff"]["vendor_id"] == "vendor_haus_001"
    packet_path = _packet_path(case["vendor_handoff"]["packet_uri"])
    assert packet_path.exists()

    with zipfile.ZipFile(packet_path) as zf:
        handoff = json.loads(zf.read("handoff.json"))
        summary = zf.read("summary.md").decode("utf-8")

    assert handoff["case_id"] == case["case_id"]
    assert handoff["vendor"]["vendor_name"] == "Keystone HDB Renovation Pte Ltd"
    assert handoff["cached"] is True
    assert "Renovation Handoff" in summary


def test_handoff_can_select_vendor_by_id(tmp_path: Path) -> None:
    case = _approved_case()
    agent = VendorHandoffAgent(vendor_cache_dir=VENDORS_DIR, handoff_root=tmp_path)

    case = step_handoff(case, handoff_agent=agent, vendor_id="vendor_haus_002")

    assert case["vendor_handoff"]["vendor_id"] == "vendor_haus_002"
    assert case["vendor_handoff"]["vendor_name"] == "Northstar Interior Works"


def test_cache_miss_uses_live_search_stub(tmp_path: Path) -> None:
    case = _approved_case()
    agent = VendorHandoffAgent(vendor_cache_dir=tmp_path / "missing-cache", handoff_root=tmp_path)

    case = step_handoff(case, handoff_agent=agent, vendor_cache_key="not_cached")

    assert case["design_status"] == "handoff_complete"
    assert case["vendor_handoff"]["cached"] is False
    assert case["vendor_handoff"]["vendor_id"] == "live_search_stub"


def test_handoff_requires_approved_state(tmp_path: Path) -> None:
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    agent = VendorHandoffAgent(vendor_cache_dir=VENDORS_DIR, handoff_root=tmp_path)

    with pytest.raises(InvalidStateTransition):
        step_handoff(case, handoff_agent=agent)


def test_unknown_vendor_id_in_cache_raises(tmp_path: Path) -> None:
    case = _approved_case()
    agent = VendorHandoffAgent(vendor_cache_dir=VENDORS_DIR, handoff_root=tmp_path)

    with pytest.raises(VendorCacheError):
        step_handoff(case, handoff_agent=agent, vendor_id="missing_vendor")
