from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.services.entity_extractor import COARSE_ENTITY_TYPES, FINE_ENTITY_TYPES, EntityExtractor

router = APIRouter(prefix="/ner")


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: Literal["de", "en"] = "de"
    granularity: Literal["fine", "coarse"] = "fine"
    use_gazetteer: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "Der BGH hat entschieden, dass § 433 BGB anwendbar ist.",
                    "language": "de",
                    "granularity": "fine",
                    "use_gazetteer": True,
                },
                {
                    "text": "The Court held in Brown v. Board of Education that segregation was unconstitutional.",
                    "language": "en",
                    "granularity": "fine",
                    "use_gazetteer": False,
                },
            ]
        }
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("text must not be blank")
        return text


class BatchExtractRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=100)
    language: Literal["de", "en"] = "de"
    granularity: Literal["fine", "coarse"] = "fine"
    use_gazetteer: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "texts": [
                        "Der BGH entschied im Verfahren III ZR 100/22.",
                        "The Supreme Court reviewed the judgment.",
                    ],
                    "language": "de",
                    "granularity": "coarse",
                    "use_gazetteer": True,
                }
            ]
        }
    )

    @field_validator("texts")
    @classmethod
    def validate_texts(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned:
            raise ValueError("texts must contain at least one non-empty string")
        return cleaned


def get_entity_extractor(request: Request) -> EntityExtractor:
    extractor = getattr(request.app.state, "entity_extractor", None)
    if extractor is None:
        raise HTTPException(status_code=503, detail="NER model is not loaded")
    return extractor


def _resolve_model_name(extractor: EntityExtractor, language: str) -> str:
    model_name_for_language = getattr(extractor, "model_name_for_language", None)
    if callable(model_name_for_language):
        return str(model_name_for_language(language))
    return str(getattr(extractor, "model_name", "ner-model"))


def _build_response(
    text: str,
    entities: list[dict[str, Any]],
    language: str,
    granularity: str,
    use_gazetteer: bool,
    model_name: str,
) -> dict[str, Any]:
    entity_counts = dict(Counter(entity["type"] for entity in entities))
    return {
        "text": text,
        "entities": entities,
        "entity_counts": entity_counts,
        "model_info": {
            "model": model_name,
            "language": language,
            "granularity": granularity,
            "gazetteer_applied": use_gazetteer,
        },
    }


@router.post("/extract")
async def extract_entities(
    body: ExtractRequest,
    extractor: EntityExtractor = Depends(get_entity_extractor),
) -> dict[str, Any]:
    entities = extractor.extract(
        text=body.text,
        language=body.language,
        granularity=body.granularity,
        use_gazetteer=body.use_gazetteer,
    )
    return _build_response(
        text=body.text,
        entities=entities,
        language=body.language,
        granularity=body.granularity,
        use_gazetteer=body.use_gazetteer,
        model_name=_resolve_model_name(extractor, body.language),
    )


@router.get("/entity-types")
async def list_entity_types() -> dict[str, list[dict[str, Any]]]:
    return {
        "fine_grained": list(FINE_ENTITY_TYPES),
        "coarse_grained": list(COARSE_ENTITY_TYPES),
    }


@router.post("/batch")
async def extract_entities_batch(
    body: BatchExtractRequest,
    extractor: EntityExtractor = Depends(get_entity_extractor),
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for text in body.texts:
        entities = extractor.extract(
            text=text,
            language=body.language,
            granularity=body.granularity,
            use_gazetteer=body.use_gazetteer,
        )
        results.append(
            _build_response(
                text=text,
                entities=entities,
                language=body.language,
                granularity=body.granularity,
                use_gazetteer=body.use_gazetteer,
                model_name=_resolve_model_name(extractor, body.language),
            )
        )
    return results
