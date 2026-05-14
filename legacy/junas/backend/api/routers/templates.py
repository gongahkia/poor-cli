"""Legal template library router."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.services.template_service import list_templates, get_template, render_template

router = APIRouter(prefix="/templates")

def _template_to_dict(t) -> dict[str, Any]:
    return {"id": t.id, "title": t.title, "category": t.category, "jurisdiction": t.jurisdiction, "description": t.description,
            "variables": [{"name": v.name, "label": v.label, "placeholder": v.placeholder, "type": v.var_type} for v in t.variables],
            "content": t.content}

@router.get("")
async def list_all_templates(jurisdiction: str = "", category: str = "") -> list[dict[str, Any]]:
    return [_template_to_dict(t) for t in list_templates(jurisdiction, category)]

@router.get("/{template_id}")
async def get_template_by_id(template_id: str) -> dict[str, Any]:
    template = get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_dict(template)

class RenderRequest(BaseModel):
    values: dict[str, str]

@router.post("/{template_id}/render")
async def render(template_id: str, req: RenderRequest) -> dict[str, str]:
    template = get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    rendered = render_template(template, req.values)
    return {"template_id": template_id, "rendered": rendered}
