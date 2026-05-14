from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.config import get_settings
from api.services.rome_statute import RomeStatuteService, create_rome_statute_service

router = APIRouter(prefix="/rome-statute")


def get_rome_statute_service(request: Request) -> RomeStatuteService:
    service = getattr(request.app.state, "rome_statute_service", None)
    if isinstance(service, RomeStatuteService):
        return service

    settings = get_settings()
    service = create_rome_statute_service(settings.rome_statute_data_path)
    if service is None:
        raise HTTPException(status_code=503, detail="Rome Statute dataset is unavailable")

    request.app.state.rome_statute_service = service
    return service


@router.get("/search")
async def search_rome_statute(
    q: str = Query(..., min_length=1),
    top_k: int = Query(20, ge=1, le=100),
    service: RomeStatuteService = Depends(get_rome_statute_service),
) -> dict[str, Any]:
    results = service.search(query=q, top_k=top_k)
    return {"query": q, "total": len(results), "results": results}


@router.get("/article/{number}")
async def get_rome_article(
    number: str,
    service: RomeStatuteService = Depends(get_rome_statute_service),
) -> dict[str, Any]:
    article = service.get_article(number)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.get("/parts")
async def list_rome_parts(
    service: RomeStatuteService = Depends(get_rome_statute_service),
) -> dict[str, Any]:
    return {"parts": service.list_parts()}


@router.get("/part/{number}")
async def get_rome_part(
    number: str,
    service: RomeStatuteService = Depends(get_rome_statute_service),
) -> dict[str, Any]:
    part = service.get_part(number)
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")
    return part
