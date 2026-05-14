from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.services.glossary_lookup import GlossaryService, parse_csv_list

router = APIRouter(prefix="/glossary")


def get_glossary_service(request: Request) -> GlossaryService:
    es = getattr(request.app.state, "elasticsearch", None)
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch client unavailable")
    return GlossaryService(es)


@router.get("/search")
async def search_glossary(
    q: str = Query(..., min_length=1),
    jurisdiction: str | None = Query(None),
    domain: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    service: GlossaryService = Depends(get_glossary_service),
) -> dict[str, Any]:
    return await service.search(
        q=q,
        jurisdiction=parse_csv_list(jurisdiction),
        domain=parse_csv_list(domain),
        page=page,
        per_page=per_page,
    )


@router.get("/term/{phrase}")
async def get_glossary_term(
    phrase: str,
    service: GlossaryService = Depends(get_glossary_service),
) -> dict[str, Any]:
    return await service.get_term(phrase)


@router.get("/compare")
async def compare_glossary_term(
    term: str = Query(..., min_length=1),
    jurisdictions: str | None = Query(None),
    service: GlossaryService = Depends(get_glossary_service),
) -> dict[str, Any]:
    return await service.compare(term, parse_csv_list(jurisdictions))


@router.get("/suggest")
async def suggest_terms(
    prefix: str = Query(..., min_length=1),
    size: int = Query(10, ge=1, le=30),
    service: GlossaryService = Depends(get_glossary_service),
) -> dict[str, list[str]]:
    suggestions = await service.suggest(prefix, size)
    return {"suggestions": suggestions}


@router.get("/jurisdictions")
async def list_jurisdictions(
    service: GlossaryService = Depends(get_glossary_service),
) -> dict[str, list[dict[str, Any]]]:
    jurisdictions = await service.get_jurisdictions()
    return {"jurisdictions": jurisdictions}
