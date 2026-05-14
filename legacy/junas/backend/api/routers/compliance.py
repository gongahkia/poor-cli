"""Compliance checking router."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel
from api.services.compliance_service import (
    check_compliance,
    get_default_rules,
    normalize_jurisdiction,
    ComplianceRule as CRule,
)

router = APIRouter(prefix="/compliance")

class ComplianceCheckRequest(BaseModel):
    text: str
    jurisdiction: str = "sg"
    custom_rules: list[dict[str, Any]] | None = None

@router.get("/rules")
async def list_rules(jurisdiction: str = "sg") -> list[dict[str, Any]]:
    resolved = normalize_jurisdiction(jurisdiction)
    rules = get_default_rules(resolved)
    return [{"id": r.id, "name": r.name, "category": r.category, "description": r.description, "keywords": r.keywords, "severity": r.severity, "jurisdiction": resolved} for r in rules]

@router.post("/check")
async def check(req: ComplianceCheckRequest) -> dict[str, Any]:
    resolved = normalize_jurisdiction(req.jurisdiction)
    rules = get_default_rules(resolved)
    if req.custom_rules:
        rules = rules + [CRule(id=r["id"], name=r["name"], category=r.get("category", "Custom"), description=r.get("description", ""), keywords=r.get("keywords", []), severity=r.get("severity", "medium")) for r in req.custom_rules]
    results = check_compliance(req.text, rules)
    passed = sum(1 for r in results if r.status == "pass")
    warnings = sum(1 for r in results if r.status == "warning")
    failed = sum(1 for r in results if r.status == "fail")
    return {
        "results": [{"rule_id": r.rule_id, "rule_name": r.rule_name, "status": r.status, "details": r.details, "severity": r.severity} for r in results],
        "summary": {"total": len(results), "passed": passed, "warnings": warnings, "failed": failed},
        "jurisdiction": resolved,
    }
