from __future__ import annotations

import json
import urllib.request
from typing import Any

from .offline import require_online
from .providers import ProviderRequest, ProviderResponse


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any | None = None):
        if client is None:
            from anthropic import Anthropic

            client = Anthropic()
        self.client = client

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("anthropic provider")
        kwargs = dict(request.params)
        message = self.client.messages.create(
            model=request.model,
            system=request.system_prompt or None,
            messages=[{"role": "user", "content": request.prompt}],
            max_tokens=int(kwargs.pop("max_tokens", 4096)),
            **kwargs,
        )
        return ProviderResponse(provider=self.name, model=request.model, content=_anthropic_text(message), raw=_raw(message))


class OpenAIProvider:
    name = "openai"

    def __init__(self, client: Any | None = None):
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        self.client = client

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("openai provider")
        kwargs = dict(request.params)
        response = self.client.responses.create(
            model=request.model,
            input=request.prompt,
            instructions=request.system_prompt or None,
            **kwargs,
        )
        return ProviderResponse(provider=self.name, model=request.model, content=_openai_text(response), raw=_raw(response))


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: Any | None = None):
        if client is None:
            from google import genai

            client = genai.Client()
        self.client = client

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("gemini provider")
        kwargs = dict(request.params)
        config = kwargs.pop("config", None)
        if request.system_prompt:
            config = {**(config or {}), "system_instruction": request.system_prompt}
        response = self.client.models.generate_content(model=request.model, contents=request.prompt, config=config, **kwargs)
        return ProviderResponse(provider=self.name, model=request.model, content=_gemini_text(response), raw=_raw(response))


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", opener: Any | None = None):
        self.base_url = base_url.rstrip("/")
        self.opener = opener or urllib.request.urlopen

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("ollama provider")
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "system": request.system_prompt,
            "stream": False,
            "options": request.params,
        }
        http_request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(http_request) as response:
            raw = json.loads(response.read().decode())
        return ProviderResponse(provider=self.name, model=request.model, content=str(raw.get("response") or ""), raw=raw)


def _anthropic_text(message: Any) -> str:
    parts = []
    for block in getattr(message, "content", []) or []:
        if isinstance(block, dict):
            parts.append(str(block.get("text") or ""))
        else:
            parts.append(str(getattr(block, "text", "")))
    return "".join(parts)


def _openai_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            chunks.append(str(getattr(content, "text", "")))
    return "".join(chunks)


def _gemini_text(response: Any) -> str:
    text = getattr(response, "text", None)
    return str(text or "")


def _raw(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    if isinstance(value, dict):
        return value
    return {"repr": repr(value)}
