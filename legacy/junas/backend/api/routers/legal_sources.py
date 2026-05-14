"""Legal source scraping router."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from api.services.legal_scraper import search_sso_statutes, search_commonlii_cases

router = APIRouter(prefix="/legal-sources")

def _result_to_dict(r) -> dict[str, str]:
    return {"title": r.title, "url": r.url, "snippet": r.snippet, "source": r.source}

@router.get("/sso")
async def sso_search(query: str = Query(..., min_length=1)) -> list[dict[str, str]]:
    try:
        results = await search_sso_statutes(query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SSO search failed: {exc}")
    return [_result_to_dict(r) for r in results]

@router.get("/commonlii")
async def commonlii_search(query: str = Query(..., min_length=1)) -> list[dict[str, str]]:
    try:
        results = await search_commonlii_cases(query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"CommonLII search failed: {exc}")
    return [_result_to_dict(r) for r in results]
