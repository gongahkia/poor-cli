"""BYOK streaming chat router."""
from __future__ import annotations
import json
from typing import Any
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from api.services.chat_service import ChatSettings, chat_stream, chat_generate, PROVIDER_TOKEN_BUDGETS

router = APIRouter(prefix="/chat")

class ChatRequest(BaseModel):
    provider: str = "claude"
    model: str = ""
    messages: list[dict[str, str]]
    temperature: float | None = None
    max_tokens: int = 4096
    top_p: float | None = None
    system_prompt: str | None = None
    api_key: str = ""  # BYOK: sent per-request
    endpoint: str = ""  # for ollama/lmstudio

PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "claude": "claude-sonnet-4-20250514",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3",
    "lmstudio": "default",
}

def _resolve_api_key(req: ChatRequest, http_request: Request) -> str:
    if req.api_key:
        return req.api_key
    header_key = http_request.headers.get(f"x-api-key-{req.provider}", "")
    return header_key

@router.post("/stream")
async def stream_chat(req: ChatRequest, http_request: Request) -> StreamingResponse:
    api_key = _resolve_api_key(req, http_request)
    model = req.model or PROVIDER_DEFAULT_MODELS.get(req.provider, "")
    settings = ChatSettings(temperature=req.temperature, max_tokens=req.max_tokens, top_p=req.top_p, system_prompt=req.system_prompt)
    async def event_generator():
        try:
            async for chunk in chat_stream(req.provider, req.messages, model, settings, api_key=api_key, endpoint=req.endpoint):
                yield f"data: {json.dumps({'delta': chunk, 'done': False})}\n\n"
            yield f"data: {json.dumps({'delta': '', 'done': True})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/send")
async def send_chat(req: ChatRequest, http_request: Request) -> dict[str, Any]:
    api_key = _resolve_api_key(req, http_request)
    model = req.model or PROVIDER_DEFAULT_MODELS.get(req.provider, "")
    settings = ChatSettings(temperature=req.temperature, max_tokens=req.max_tokens, top_p=req.top_p, system_prompt=req.system_prompt)
    try:
        content = await chat_generate(req.provider, req.messages, model, settings, api_key=api_key, endpoint=req.endpoint)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=str(exc))
    return {"content": content, "model": model, "provider": req.provider}

@router.get("/providers")
async def list_providers() -> list[dict[str, Any]]:
    return [
        {"id": "claude", "label": "Anthropic Claude", "default_model": "claude-sonnet-4-20250514", "is_local": False, "token_budget": PROVIDER_TOKEN_BUDGETS["claude"]},
        {"id": "openai", "label": "OpenAI", "default_model": "gpt-4o-mini", "is_local": False, "token_budget": PROVIDER_TOKEN_BUDGETS["openai"]},
        {"id": "gemini", "label": "Google Gemini", "default_model": "gemini-2.0-flash", "is_local": False, "token_budget": PROVIDER_TOKEN_BUDGETS["gemini"]},
        {"id": "ollama", "label": "Ollama (Local)", "default_model": "llama3", "is_local": True, "token_budget": PROVIDER_TOKEN_BUDGETS["ollama"]},
        {"id": "lmstudio", "label": "LM Studio (Local)", "default_model": "default", "is_local": True, "token_budget": PROVIDER_TOKEN_BUDGETS["lmstudio"]},
    ]
