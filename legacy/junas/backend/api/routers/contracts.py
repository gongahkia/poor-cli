from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from api.services.contract_classifier import ContractClassifier
from api.services.tos_scanner import ToSScanner

router = APIRouter(prefix="/contracts")


class ContractClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1)
    top_k_types: int = Field(3, ge=1, le=5)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text must not be blank")
        return text


class ToSScanRequest(BaseModel):
    text: str = Field(..., min_length=1)
    threshold: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text must not be blank")
        return text


def get_contract_classifier(request: Request) -> ContractClassifier:
    classifier = getattr(request.app.state, "contract_classifier", None)
    if classifier is None:
        raise HTTPException(status_code=503, detail="Contract classifier model is not loaded")
    return classifier


def get_tos_scanner(request: Request) -> ToSScanner:
    scanner = getattr(request.app.state, "tos_scanner", None)
    if scanner is None:
        raise HTTPException(status_code=503, detail="ToS scanner model is not loaded")
    return scanner


@router.post("/classify")
async def classify_contract(
    body: ContractClassifyRequest,
    classifier: ContractClassifier = Depends(get_contract_classifier),
) -> dict[str, Any]:
    clauses = classifier.classify_contract(body.text, top_k_types=body.top_k_types)
    distribution = dict(Counter(clause["clause_type"] for clause in clauses))
    return {
        "total_clauses": len(clauses),
        "clauses": clauses,
        "clause_distribution": distribution,
    }


@router.post("/scan-tos")
async def scan_tos(
    body: ToSScanRequest,
    scanner: ToSScanner = Depends(get_tos_scanner),
) -> dict[str, Any]:
    return scanner.scan_tos(body.text, threshold=body.threshold)
