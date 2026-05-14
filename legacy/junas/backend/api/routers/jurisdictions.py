"""Jurisdiction registry router."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from api.services.jurisdiction_registry import list_jurisdictions, get_jurisdiction

router = APIRouter(prefix="/jurisdictions")

def _jurisdiction_to_dict(j) -> dict[str, Any]:
    return {
        "id": j.id, "name": j.name, "short_name": j.short_name,
        "citation_patterns": [{"kind": p.kind, "regex": p.regex, "description": p.description} for p in j.citation_patterns],
        "legal_source_domains": j.legal_source_domains,
        "system_prompt_addition": j.system_prompt_addition,
        "template_ids": j.template_ids,
    }

@router.get("")
async def list_all() -> list[dict[str, Any]]:
    return [_jurisdiction_to_dict(j) for j in list_jurisdictions()]

@router.get("/{jurisdiction_id}")
async def get_by_id(jurisdiction_id: str) -> dict[str, Any]:
    j = get_jurisdiction(jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    return _jurisdiction_to_dict(j)
