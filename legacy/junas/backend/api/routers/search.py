from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from api.config import get_settings
from api.services.case_retrieval import CaseRetrievalService, create_case_retrieval_service

router = APIRouter(prefix="/search")
StageLiteral = Literal["bm25", "dense", "rerank"]
DEFAULT_STAGES: list[StageLiteral] = ["bm25", "dense", "rerank"]


class CaseSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=50)
    stages: list[StageLiteral] = Field(default_factory=lambda: list(DEFAULT_STAGES))
    include_scores: bool = True

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be blank")
        return query

    @field_validator("stages")
    @classmethod
    def validate_stages(cls, values: list[StageLiteral]) -> list[StageLiteral]:
        if not values:
            return list(DEFAULT_STAGES)
        ordered: list[StageLiteral] = []
        seen: set[StageLiteral] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered


def get_case_retrieval_service(request: Request) -> CaseRetrievalService:
    service = getattr(request.app.state, "case_retrieval_service", None)
    if service is not None:
        return service

    settings = get_settings()
    service = create_case_retrieval_service(
        data_root=settings.lecard_data_root,
        qdrant_url=settings.qdrant_url,
        biencoder_model_path=settings.case_biencoder_model_path,
        cross_encoder_model_path=settings.case_cross_encoder_model_path,
        metrics_path=settings.case_retrieval_metrics_path,
    )
    if service is None:
        raise HTTPException(status_code=503, detail="Case retrieval service is unavailable")

    request.app.state.case_retrieval_service = service
    return service


@router.post("/cases")
async def search_cases(
    body: CaseSearchRequest,
    service: CaseRetrievalService = Depends(get_case_retrieval_service),
) -> dict[str, Any]:
    return service.search_cases(
        query=body.query,
        top_k=body.top_k,
        stages=[str(stage) for stage in body.stages],
        include_scores=body.include_scores,
    )


@router.get("/cases/{case_id}")
async def get_case_details(
    case_id: str,
    service: CaseRetrievalService = Depends(get_case_retrieval_service),
) -> dict[str, Any]:
    row = service.get_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return row


@router.get("/charges")
async def list_charges(
    service: CaseRetrievalService = Depends(get_case_retrieval_service),
) -> dict[str, list[str]]:
    return {"charges": service.list_charges()}


@router.get("/metrics")
async def get_retrieval_metrics(
    service: CaseRetrievalService = Depends(get_case_retrieval_service),
) -> dict[str, Any]:
    return service.get_metrics()
