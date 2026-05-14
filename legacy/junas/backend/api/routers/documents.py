"""Document parsing router."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from api.services.document_parser import parse_document

router = APIRouter(prefix="/documents")

@router.post("/parse")
async def parse(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        result = parse_document(data, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"filename": result.filename, "text": result.text, "page_count": result.page_count, "char_count": result.char_count}
