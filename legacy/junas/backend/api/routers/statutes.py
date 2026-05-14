from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.services.statute_lookup import StatuteService

router = APIRouter(prefix="/statutes")


def get_statute_service(request: Request) -> StatuteService:
    es = getattr(request.app.state, "elasticsearch", None)
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch client unavailable")
    qdrant = getattr(request.app.state, "qdrant", None)
    return StatuteService(es=es, qdrant=qdrant)


@router.get("/search")
async def search_statutes(
    q: str = Query(..., min_length=1),
    chapter: str | None = Query(None),
    mode: Literal["hybrid", "keyword", "semantic"] = Query("hybrid"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    service: StatuteService = Depends(get_statute_service),
) -> dict[str, Any]:
    try:
        return await service.search(q=q, chapter=chapter, mode=mode, page=page, per_page=per_page)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/section/{number}")
async def get_statute_section(
    number: str,
    service: StatuteService = Depends(get_statute_service),
) -> dict[str, Any]:
    section = await service.get_section(number)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@router.get("/chapters")
async def list_statute_chapters(
    service: StatuteService = Depends(get_statute_service),
) -> dict[str, list[dict[str, Any]]]:
    chapters = await service.list_chapters()
    return {"chapters": chapters}


@router.get("/chapter/{chapter_number}")
async def list_chapter_sections(
    chapter_number: str,
    service: StatuteService = Depends(get_statute_service),
) -> dict[str, Any]:
    sections = await service.get_chapter_sections(chapter_number)
    return {"chapter_number": chapter_number, "sections": sections}
