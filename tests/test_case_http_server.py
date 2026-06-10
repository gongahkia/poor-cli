"""HTTP boundary tests for SPEC-HTTP-CASE.md section 4."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from starlette.testclient import TestClient

from haus.case.http_server import create_app
from haus.case.ingest import load_case_from_library
from haus.case.store import CaseStore, SQLiteCaseStore


LIBRARY_3 = "corpus/library/3.json"
PROPOSALS_DIR = "tests/fixtures/proposals"
VENDORS_DIR = "tests/fixtures/vendors"
BRIEF = {
    "flat_type": "3-room BTO",
    "household_size": 2,
    "style_prompt": "minimalist",
    "constraints": [],
    "must_keep_rooms": [],
}


def _client(
    max_revise: int = 1,
    handoff_root: Path | None = None,
    vendor_cache_dir: str | Path | None = VENDORS_DIR,
    api_token: str | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            proposals_dir=PROPOSALS_DIR,
            vendor_cache_dir=vendor_cache_dir,
            handoff_root=handoff_root,
            max_revise=max_revise,
            store=CaseStore(),
            api_token=api_token,
        )
    )


def _create_case(client: TestClient, pinned: str = "demo_3room_remove_wall_28") -> dict:
    res = client.post(
        "/case",
        json={
            "floor_plan_ref": LIBRARY_3,
            "brief": BRIEF,
            "pinned_proposal_id": pinned,
        },
    )
    assert res.status_code == 201
    return res.json()


def test_http_round_trip_escalates_then_approves():
    with _client(max_revise=1) as client:
        case = _create_case(client)
        case_id = case["case_id"]
        assert case["design_status"] == "designing"

        res = client.post(f"/case/{case_id}/design", json={})
        assert res.status_code == 200
        case = res.json()
        assert case["design_status"] == "compliance_pending"
        assert all(it.get("name") != "wall_28" for it in case["items"])

        res = client.post(f"/case/{case_id}/compliance", json={})
        assert res.status_code == 200
        case = res.json()
        assert case["design_status"] == "revising"
        assert case["compliance_findings"][0]["element_name"] == "wall_28"

        res = client.post(
            f"/case/{case_id}/revise",
            json={"findings": case["compliance_findings"]},
        )
        assert res.status_code == 200
        case = res.json()
        assert case["design_status"] == "compliance_pending"
        assert case["revise_count"] == 1

        res = client.post(f"/case/{case_id}/compliance", json={})
        assert res.status_code == 200
        case = res.json()
        assert case["design_status"] == "awaiting_human_approval"
        assert "Auto-revise exhausted" in case["approval_state"]["escalation_reason"]

        res = client.patch(
            f"/case/{case_id}/approval",
            json={"decision": "approved", "reviewer": "coordinator_alice", "notes": "ok"},
        )
        assert res.status_code == 200
        case = res.json()
        assert case["design_status"] == "approved"
        assert case["approval_state"]["reviewer"] == "coordinator_alice"

        res = client.get(f"/case/{case_id}")
        assert res.status_code == 200
        assert res.json()["design_status"] == "approved"


def test_handoff_route_completes_approved_case_and_writes_packet(tmp_path: Path):
    with _client(max_revise=3, handoff_root=tmp_path) as client:
        case = _create_case(client, pinned="demo_3room_keep_walls")
        case_id = case["case_id"]

        assert client.post(f"/case/{case_id}/design", json={}).status_code == 200
        assert client.post(f"/case/{case_id}/compliance", json={}).status_code == 200
        assert client.patch(
            f"/case/{case_id}/approval",
            json={"decision": "approved", "reviewer": "coordinator_alice"},
        ).status_code == 200

        res = client.post(
            f"/case/{case_id}/handoff",
            json={"vendor_cache_key": "demo_hdb_renovation"},
        )
        assert res.status_code == 200
        case = res.json()
        assert case["design_status"] == "handoff_complete"
        assert case["vendor_handoff"]["cached"] is True
        assert case["vendor_handoff"]["vendor_id"] == "vendor_haus_001"

        packet_path = Path(urlparse(case["vendor_handoff"]["packet_uri"]).path)
        assert packet_path.exists()
        with zipfile.ZipFile(packet_path) as zf:
            handoff = json.loads(zf.read("handoff.json"))
        assert handoff["case_id"] == case_id
        assert handoff["vendor"]["vendor_name"] == "Keystone HDB Renovation Pte Ltd"


def test_clean_design_goes_to_human_approval_over_http():
    with _client(max_revise=3) as client:
        case = _create_case(client, pinned="demo_3room_keep_walls")
        case_id = case["case_id"]

        assert client.post(f"/case/{case_id}/design", json={}).status_code == 200
        res = client.post(f"/case/{case_id}/compliance", json={})
        assert res.status_code == 200
        case = res.json()
        assert case["design_status"] == "awaiting_human_approval"
        assert case["compliance_findings"] == []
        assert case["approval_state"]["escalation_reason"] is None


def test_create_case_validates_required_fields():
    with _client() as client:
        res = client.post("/case", json={"floor_plan_ref": LIBRARY_3})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "validation_failed"


def test_create_case_rejects_malformed_library_payload(tmp_path: Path):
    bad = tmp_path / "bad-case.json"
    bad.write_text(json.dumps({"version": 1, "metadata": {}, "items": {"bad": "shape"}}), encoding="utf-8")

    with _client() as client:
        res = client.post("/case", json={"floor_plan_ref": str(bad), "brief": BRIEF})

    assert res.status_code == 400
    body = res.json()
    assert body["error"]["code"] == "validation_failed"
    assert "items" in body["error"]["hint"]


def test_create_case_missing_library_is_validation_error():
    with _client() as client:
        res = client.post("/case", json={"floor_plan_ref": "missing-case.json", "brief": BRIEF})

    assert res.status_code == 400
    assert res.json()["error"]["code"] == "validation_failed"


def test_unknown_case_returns_uniform_error_envelope():
    with _client() as client:
        res = client.get("/case/does-not-exist")
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "case_not_found"


def test_invalid_state_transition_returns_uniform_error_envelope():
    with _client() as client:
        case = _create_case(client)
        res = client.post(f"/case/{case['case_id']}/compliance", json={})
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "invalid_state_transition"


def test_revise_requires_findings_array():
    with _client() as client:
        case = _create_case(client)
        case_id = case["case_id"]
        assert client.post(f"/case/{case_id}/design", json={}).status_code == 200
        assert client.post(f"/case/{case_id}/compliance", json={}).status_code == 200

        res = client.post(f"/case/{case_id}/revise", json={})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "validation_failed"


def test_handoff_requires_approved_state_over_http(tmp_path: Path):
    with _client(handoff_root=tmp_path) as client:
        case = _create_case(client)
        res = client.post(f"/case/{case['case_id']}/handoff", json={})
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "invalid_state_transition"


def test_handoff_cache_miss_returns_fallback_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    with _client(max_revise=3, handoff_root=tmp_path / "handoffs", vendor_cache_dir=tmp_path / "vendors") as client:
        case = _create_case(client, pinned="demo_3room_keep_walls")
        case_id = case["case_id"]
        assert client.post(f"/case/{case_id}/design", json={}).status_code == 200
        assert client.post(f"/case/{case_id}/compliance", json={}).status_code == 200
        assert client.patch(
            f"/case/{case_id}/approval",
            json={"decision": "approved", "reviewer": "coordinator_alice"},
        ).status_code == 200

        res = client.post(f"/case/{case_id}/handoff", json={"vendor_cache_key": "not_cached"})

    assert res.status_code == 200
    handoff = res.json()["vendor_handoff"]
    assert handoff["cached"] is False
    assert handoff["source"] == "live_search_stub"
    assert handoff["fallback_reason"] == "vendor_cache_miss"


def test_sqlite_store_persists_case_across_app_instances(tmp_path: Path):
    db_path = tmp_path / "cases.sqlite3"
    app = create_app(
        proposals_dir=PROPOSALS_DIR,
        vendor_cache_dir=VENDORS_DIR,
        case_db_path=db_path,
    )
    with TestClient(app) as client:
        case = _create_case(client, pinned="demo_3room_keep_walls")
        case_id = case["case_id"]
        assert case["revision"] == 1

    app = create_app(
        proposals_dir=PROPOSALS_DIR,
        vendor_cache_dir=VENDORS_DIR,
        case_db_path=db_path,
    )
    with TestClient(app) as client:
        res = client.get(f"/case/{case_id}")

    assert res.status_code == 200
    assert res.json()["case_id"] == case_id


def test_case_http_auth_requires_bearer_token():
    app = create_app(
        proposals_dir=PROPOSALS_DIR,
        vendor_cache_dir=VENDORS_DIR,
        store=CaseStore(),
        api_token="secret-token",
    )
    with TestClient(app) as client:
        res = client.get("/case/does-not-exist")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "unauthorized"

        res = client.post(
            "/case",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "floor_plan_ref": LIBRARY_3,
                "brief": BRIEF,
                "pinned_proposal_id": "demo_3room_keep_walls",
            },
        )
        assert res.status_code == 201


def test_sqlite_store_updates_are_atomic(tmp_path: Path):
    store = SQLiteCaseStore(tmp_path / "cases.sqlite3")
    case = load_case_from_library(LIBRARY_3, brief=BRIEF)
    case = store.create(case)
    case_id = case["case_id"]

    def bump() -> None:
        store.update(case_id, lambda c: {**c, "revise_count": c.get("revise_count", 0) + 1})

    threads = [Thread(target=bump) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    saved = store.get(case_id)
    assert saved["revise_count"] == 8
    assert saved["revision"] == 9
