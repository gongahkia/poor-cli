from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.config import get_settings
from api.services.case_retrieval import create_case_retrieval_service
from api.services.citation_verifier import CitationVerifier
from api.services.legal_qa import ConversationStore, LegalQAService
from api.services.llm_client import get_llm_client, get_llm_model_name
from api.services.retrieval_orchestrator import RetrievalOrchestrator, SourceType

router = APIRouter(prefix="/research")


class ResearchAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    sources: list[str] | None = None
    top_k: int = Field(8, ge=1, le=12)
    conversation_id: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "question": "What is genocide under the Rome Statute?",
                    "sources": ["treaty", "statute", "glossary"],
                    "top_k": 8,
                }
            ]
        }
    )

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("question must not be blank")
        return question

    @field_validator("sources")
    @classmethod
    def _normalize_sources(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [str(item).strip().lower() for item in value if str(item).strip()]
        return cleaned or None


class ResearchAskResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]
    citations: dict[str, Any]
    conversation_id: str


def _parse_source_types(raw_sources: list[str] | None) -> list[SourceType] | None:
    if raw_sources is None:
        return None

    normalized: list[SourceType] = []
    seen: set[SourceType] = set()
    aliases = {
        "statute": SourceType.STATUTE,
        "statutes": SourceType.STATUTE,
        "glossary": SourceType.GLOSSARY,
        "case": SourceType.CASE_LAW,
        "case_law": SourceType.CASE_LAW,
        "case-law": SourceType.CASE_LAW,
        "treaty": SourceType.TREATY,
        "treaties": SourceType.TREATY,
        "rome-statute": SourceType.TREATY,
        "rome_statute": SourceType.TREATY,
    }

    for raw in raw_sources:
        if raw not in aliases:
            raise ValueError(f"unsupported source: {raw}")
        source_type = aliases[raw]
        if source_type in seen:
            continue
        seen.add(source_type)
        normalized.append(source_type)

    return normalized or None


def get_legal_qa_service(request: Request) -> LegalQAService:
    service = getattr(request.app.state, "legal_qa_service", None)
    if isinstance(service, LegalQAService):
        return service

    settings = get_settings()
    es = getattr(request.app.state, "elasticsearch", None)
    if es is None:
        raise HTTPException(status_code=503, detail="Elasticsearch client unavailable")

    qdrant = getattr(request.app.state, "qdrant", None)
    case_service = getattr(request.app.state, "case_retrieval_service", None)
    if case_service is None:
        case_service = create_case_retrieval_service(
            data_root=settings.lecard_data_root,
            qdrant_url=settings.qdrant_url,
            biencoder_model_path=settings.case_biencoder_model_path,
            cross_encoder_model_path=settings.case_cross_encoder_model_path,
            metrics_path=settings.case_retrieval_metrics_path,
        )
        request.app.state.case_retrieval_service = case_service

    try:
        llm_client = get_llm_client(settings)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"LLM provider unavailable: {exc}") from exc

    service = LegalQAService(
        orchestrator=RetrievalOrchestrator(es_client=es, qdrant_client=qdrant, case_service=case_service),
        llm_client=llm_client,
        citation_verifier=CitationVerifier(es_client=es),
        conversation_store=ConversationStore(getattr(request.app.state, "pg_pool", None)),
    )
    request.app.state.legal_qa_service = service
    return service


@router.post("/ask", response_model=ResearchAskResponse)
async def ask_research_question(
    body: ResearchAskRequest,
    service: LegalQAService = Depends(get_legal_qa_service),
) -> dict[str, Any]:
    try:
        source_types = _parse_source_types(body.sources)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return await service.answer(
            question=body.question,
            sources=source_types,
            conversation_id=body.conversation_id,
            top_k=body.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Research answer unavailable: {exc}") from exc


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    service: LegalQAService = Depends(get_legal_qa_service),
) -> dict[str, Any]:
    payload = await service.get_conversation(conversation_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return payload


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    service: LegalQAService = Depends(get_legal_qa_service),
) -> dict[str, Any]:
    deleted = await service.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "deleted": True}


def _rome_statute_available(request: Request) -> bool:
    if getattr(request.app.state, "rome_statute_service", None) is not None:
        return True
    settings = get_settings()
    return Path(settings.rome_statute_data_path).exists()


@router.get("/config")
async def get_research_config(request: Request) -> dict[str, Any]:
    settings = get_settings()
    available_sources = [SourceType.STATUTE.value, SourceType.GLOSSARY.value]
    if getattr(request.app.state, "case_retrieval_service", None) is not None:
        available_sources.append(SourceType.CASE_LAW.value)
    if _rome_statute_available(request):
        available_sources.append(SourceType.TREATY.value)

    return {
        "provider": settings.llm_provider,
        "model": get_llm_model_name(settings),
        "available_sources": available_sources,
        "max_context_chunks": 12,
    }
