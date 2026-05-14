"""Tests for compliance router."""
import pytest
from fastapi.testclient import TestClient
from api.main import create_app

app = create_app()
client = TestClient(app)

def test_list_rules():
    resp = client.get("/api/v1/compliance/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 10
    assert all(row["jurisdiction"] == "sg" for row in data)


def test_list_rules_uses_requested_jurisdiction():
    resp = client.get("/api/v1/compliance/rules?jurisdiction=us")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    assert all(row["jurisdiction"] == "us" for row in data)
    ids = {row["id"] for row in data}
    assert "governing-law-us" in ids

def test_check_compliance_pass():
    text = "This agreement is governed by the laws of Singapore. The consent of the individual is obtained for personal data collection under the PDPA. Data protection measures are in place."
    resp = client.post("/api/v1/compliance/check", json={"text": text})
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "summary" in data
    assert data["summary"]["total"] >= 10
    # governing law rule should pass
    gov_law = [r for r in data["results"] if r["rule_id"] == "governing-law"]
    assert gov_law[0]["status"] == "pass"

def test_check_compliance_fail():
    resp = client.post("/api/v1/compliance/check", json={"text": "Hello world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["failed"] > 0


def test_check_compliance_uses_jurisdiction_rules():
    text = "This contract is governed by the laws of California and includes arbitration venue."
    resp = client.post("/api/v1/compliance/check", json={"text": text, "jurisdiction": "us"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["jurisdiction"] == "us"
    assert data["summary"]["total"] >= 5
    rule_ids = {row["rule_id"] for row in data["results"]}
    assert "governing-law-us" in rule_ids
