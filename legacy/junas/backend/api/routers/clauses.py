"""Legal clause library router."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from api.services.clause_service import search_clauses, get_clause, get_tone

router = APIRouter(prefix="/clauses")

def _clause_to_dict(c) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "category": c.category, "jurisdiction": c.jurisdiction, "description": c.description, "standard": c.standard, "aggressive": c.aggressive, "balanced": c.balanced, "protective": c.protective, "notes": c.notes}

@router.get("")
async def list_clauses(query: str = "", jurisdiction: str = "", category: str = "") -> list[dict[str, Any]]:
    return [_clause_to_dict(c) for c in search_clauses(query, jurisdiction, category)]

@router.get("/{clause_id}")
async def get_clause_by_id(clause_id: str) -> dict[str, Any]:
    clause = get_clause(clause_id)
    if clause is None:
        raise HTTPException(status_code=404, detail="Clause not found")
    return _clause_to_dict(clause)

@router.get("/{clause_id}/tone/{tone}")
async def get_clause_tone(clause_id: str, tone: str) -> dict[str, str]:
    clause = get_clause(clause_id)
    if clause is None:
        raise HTTPException(status_code=404, detail="Clause not found")
    if tone not in ("standard", "aggressive", "balanced", "protective"):
        raise HTTPException(status_code=400, detail="Invalid tone. Must be: standard, aggressive, balanced, protective")
    return {"clause_id": clause_id, "tone": tone, "wording": get_tone(clause, tone)}
