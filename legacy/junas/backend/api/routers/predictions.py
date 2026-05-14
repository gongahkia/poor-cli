from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from api.config import get_settings
from api.services.court_predictor import CourtPredictor, create_court_predictor

router = APIRouter(prefix="/predict")


class ScotusPredictRequest(BaseModel):
    text: str = Field(..., min_length=1)
    top_k: int = Field(3, ge=1, le=14)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text must not be blank")
        return text


class EcthrPredictRequest(BaseModel):
    text: str = Field(..., min_length=1)
    task: str = Field("violation")
    threshold: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text must not be blank")
        return text

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        task = value.strip().lower()
        if task not in {"violation", "alleged"}:
            raise ValueError("task must be either 'violation' or 'alleged'")
        return task


class CaseHoldPredictRequest(BaseModel):
    context: str = Field(..., min_length=1)
    options: list[str] = Field(..., min_length=5, max_length=5)

    @field_validator("context")
    @classmethod
    def validate_context(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("context must not be blank")
        return text

    @field_validator("options")
    @classmethod
    def validate_options(cls, values: list[str]) -> list[str]:
        if len(values) != 5:
            raise ValueError("options must contain exactly 5 values")
        cleaned = [str(item).strip() for item in values]
        if any(not value for value in cleaned):
            raise ValueError("all options must be non-empty")
        return cleaned


class EurlexPredictRequest(BaseModel):
    text: str = Field(..., min_length=1)
    threshold: float = Field(0.3, ge=0.0, le=1.0)
    max_labels: int = Field(10, ge=1, le=100)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text must not be blank")
        return text


def get_court_predictor(request: Request) -> CourtPredictor:
    predictor = getattr(request.app.state, "court_predictor", None)
    if isinstance(predictor, CourtPredictor):
        return predictor

    settings = get_settings()
    predictor = create_court_predictor(
        scotus_model_path=settings.scotus_model_path,
        ecthr_violation_model_path=settings.ecthr_violation_model_path,
        ecthr_alleged_model_path=settings.ecthr_alleged_model_path,
        casehold_model_path=settings.casehold_model_path,
        eurlex_model_path=settings.eurlex_model_path,
    )
    request.app.state.court_predictor = predictor
    return predictor


@router.post("/scotus")
async def predict_scotus(
    body: ScotusPredictRequest,
    predictor: CourtPredictor = Depends(get_court_predictor),
) -> dict[str, Any]:
    try:
        return predictor.predict_scotus(text=body.text, top_k=body.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SCOTUS prediction failed: {exc}") from exc


@router.post("/ecthr")
async def predict_ecthr(
    body: EcthrPredictRequest,
    predictor: CourtPredictor = Depends(get_court_predictor),
) -> dict[str, Any]:
    try:
        return predictor.predict_ecthr(text=body.text, task=body.task, threshold=body.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ECtHR prediction failed: {exc}") from exc


@router.post("/casehold")
async def predict_casehold(
    body: CaseHoldPredictRequest,
    predictor: CourtPredictor = Depends(get_court_predictor),
) -> dict[str, Any]:
    try:
        return predictor.predict_casehold(context=body.context, options=body.options)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"CaseHOLD prediction failed: {exc}") from exc


@router.post("/eurlex")
async def predict_eurlex(
    body: EurlexPredictRequest,
    predictor: CourtPredictor = Depends(get_court_predictor),
) -> dict[str, Any]:
    try:
        return predictor.predict_eurlex(
            text=body.text,
            threshold=body.threshold,
            max_labels=body.max_labels,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"EUR-LEX prediction failed: {exc}") from exc
