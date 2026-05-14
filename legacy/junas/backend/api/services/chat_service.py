"""BYOK streaming chat service ported from Junas Rust providers.rs."""
from __future__ import annotations
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
import httpx
from api.services.llm_client import LLMClient

logger = logging.getLogger(__name__)
CONNECT_TIMEOUT = 10
REQUEST_TIMEOUT = 120
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.3

PROVIDER_TOKEN_BUDGETS: dict[str, int] = {
    "claude": 180_000,
    "openai": 120_000,
    "gemini": 100_000,
    "ollama": 16_000,
    "lmstudio": 16_000,
}


async def _retry(fn, retries: int = MAX_RETRIES) -> httpx.Response:
    for attempt in range(retries + 1):
        try:
            resp = await fn()
            if resp.status_code in (408, 429, 500, 502, 503, 504) and attempt < retries:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            if attempt >= retries:
                raise
            await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
    raise RuntimeError("unreachable")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT))


class ChatMessage:
    __slots__ = ("role", "content")
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class ChatSettings:
    def __init__(self, **kwargs: Any):
        self.temperature: float | None = kwargs.get("temperature")
        self.max_tokens: int = kwargs.get("max_tokens", 4096)
        self.top_p: float | None = kwargs.get("top_p")
        self.system_prompt: str | None = kwargs.get("system_prompt")


async def stream_claude(messages: list[dict], model: str, settings: ChatSettings, api_key: str) -> AsyncIterator[str]:
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": settings.max_tokens,
        "messages": [m for m in messages if m["role"] != "system"],
        "stream": True,
    }
    if settings.temperature is not None:
        body["temperature"] = settings.temperature
    if settings.top_p is not None:
        body["top_p"] = settings.top_p
    sys_parts = [m["content"] for m in messages if m["role"] == "system"]
    if sys_parts:
        body["system"] = "\n\n".join(sys_parts)
    if settings.system_prompt:
        body["system"] = settings.system_prompt + ("\n\n" + body.get("system", "") if body.get("system") else "")
    async with _client() as client:
        async with client.stream("POST", "https://api.anthropic.com/v1/messages", json=body, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json",
        }) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "content_block_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        yield text


async def stream_openai(messages: list[dict], model: str, settings: ChatSettings, api_key: str, base_url: str = "https://api.openai.com") -> AsyncIterator[str]:
    msgs: list[dict] = []
    if settings.system_prompt:
        msgs.append({"role": "system", "content": settings.system_prompt})
    msgs.extend(messages)
    body: dict[str, Any] = {"model": model, "messages": msgs, "stream": True}
    if settings.temperature is not None:
        body["temperature"] = settings.temperature
    if settings.max_tokens:
        body["max_tokens"] = settings.max_tokens
    if settings.top_p is not None:
        body["top_p"] = settings.top_p
    async with _client() as client:
        async with client.stream("POST", f"{base_url}/v1/chat/completions", json=body, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
        }) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        yield text


async def stream_gemini(messages: list[dict], model: str, settings: ChatSettings, api_key: str) -> AsyncIterator[str]:
    contents: list[dict] = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    body: dict[str, Any] = {"contents": contents}
    if settings.system_prompt:
        body["systemInstruction"] = {"parts": [{"text": settings.system_prompt}]}
    gen_config: dict[str, Any] = {}
    if settings.temperature is not None:
        gen_config["temperature"] = settings.temperature
    if settings.max_tokens:
        gen_config["maxOutputTokens"] = settings.max_tokens
    if settings.top_p is not None:
        gen_config["topP"] = settings.top_p
    body["generationConfig"] = gen_config
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
    async with _client() as client:
        async with client.stream("POST", url, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                candidates = event.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text = part.get("text", "")
                        if text:
                            yield text


async def stream_ollama(messages: list[dict], model: str, settings: ChatSettings, endpoint: str = "http://localhost:11434") -> AsyncIterator[str]:
    msgs: list[dict] = []
    if settings.system_prompt:
        msgs.append({"role": "system", "content": settings.system_prompt})
    msgs.extend(messages)
    body: dict[str, Any] = {"model": model, "messages": msgs, "stream": True}
    if settings.temperature is not None:
        body["options"] = {"temperature": settings.temperature}
    url = f"{endpoint.rstrip('/')}/api/chat"
    async with _client() as client:
        async with client.stream("POST", url, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = event.get("message", {}).get("content", "")
                if text:
                    yield text
                if event.get("done"):
                    break


async def stream_lmstudio(messages: list[dict], model: str, settings: ChatSettings, endpoint: str = "http://localhost:1234") -> AsyncIterator[str]:
    async for chunk in stream_openai(messages, model, settings, api_key="lm-studio", base_url=endpoint.rstrip("/")):
        yield chunk


STREAM_PROVIDERS = {
    "claude": stream_claude,
    "openai": stream_openai,
    "gemini": stream_gemini,
    "ollama": stream_ollama,
    "lmstudio": stream_lmstudio,
}


async def chat_generate(provider: str, messages: list[dict], model: str, settings: ChatSettings, api_key: str = "", endpoint: str = "") -> str:
    """Non-streaming generation: collect full response."""
    chunks: list[str] = []
    async for chunk in chat_stream(provider, messages, model, settings, api_key, endpoint):
        chunks.append(chunk)
    return "".join(chunks)


async def chat_stream(provider: str, messages: list[dict], model: str, settings: ChatSettings, api_key: str = "", endpoint: str = "") -> AsyncIterator[str]:
    """Dispatch to the appropriate streaming provider."""
    fn = STREAM_PROVIDERS.get(provider)
    if fn is None:
        raise ValueError(f"Unknown provider: {provider}")
    if provider in ("claude", "openai", "gemini"):
        async for chunk in fn(messages, model, settings, api_key):
            yield chunk
    elif provider == "ollama":
        async for chunk in fn(messages, model, settings, endpoint or "http://localhost:11434"):
            yield chunk
    elif provider == "lmstudio":
        async for chunk in fn(messages, model, settings, endpoint or "http://localhost:1234"):
            yield chunk


class GeminiClient(LLMClient):
    """Non-streaming Gemini client for RAG/research use."""
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model

    async def generate(self, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        settings = ChatSettings(max_tokens=max_tokens, temperature=0.1)
        return await chat_generate("gemini", messages, self.model, settings, api_key=self.api_key)


class LMStudioClient(LLMClient):
    """Non-streaming LM Studio client for RAG/research use."""
    def __init__(self, base_url: str = "http://localhost:1234", model: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        settings = ChatSettings(max_tokens=max_tokens, temperature=0.1)
        return await chat_generate("lmstudio", messages, self.model, settings, endpoint=self.base_url)
