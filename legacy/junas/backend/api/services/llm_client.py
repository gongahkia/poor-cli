from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        raise NotImplementedError


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        openai_module = importlib.import_module("openai")
        async_openai_cls = getattr(openai_module, "AsyncOpenAI", None)
        if async_openai_cls is None:
            raise RuntimeError("openai package does not provide AsyncOpenAI")
        self.client = async_openai_cls(api_key=api_key)
        self.model = model

    async def generate(self, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        choice = response.choices[0].message.content
        return choice if isinstance(choice, str) else ""


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        anthropic_module = importlib.import_module("anthropic")
        async_anthropic_cls = getattr(anthropic_module, "AsyncAnthropic", None)
        if async_anthropic_cls is None:
            raise RuntimeError("anthropic package does not provide AsyncAnthropic")
        self.client = async_anthropic_cls(api_key=api_key)
        self.model = model

    async def generate(self, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        system_prompt = "\n\n".join(message["content"] for message in messages if message.get("role") == "system")
        user_messages = [
            {"role": message.get("role", "user"), "content": message.get("content", "")}
            for message in messages
            if message.get("role") != "system"
        ]
        response = await self.client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=user_messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        chunks = getattr(response, "content", [])
        if not chunks:
            return ""
        first = chunks[0]
        return str(getattr(first, "text", ""))


class OllamaClient(LLMClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload.get("message", {}).get("content", ""))


class EchoContextClient(LLMClient):
    """Fallback client used when no external provider is configured."""

    async def generate(self, messages: list[dict[str, str]], max_tokens: int = 1024) -> str:
        del max_tokens
        user_messages = [message.get("content", "") for message in messages if message.get("role") == "user"]
        prompt = user_messages[-1] if user_messages else ""
        return (
            "Junas could not reach an external LLM provider. "
            "Please configure OLLAMA_URL/OLLAMA_MODEL or API keys for OpenAI/Anthropic. "
            f"Your latest prompt was: {prompt[:240]}"
        )


def get_llm_client(settings: Any) -> LLMClient:
    provider = str(getattr(settings, "llm_provider", "ollama")).strip().lower()

    if provider == "openai":
        api_key = str(getattr(settings, "openai_api_key", "")).strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for llm_provider=openai")
        model = str(getattr(settings, "openai_model", "gpt-4o-mini")).strip() or "gpt-4o-mini"
        return OpenAIClient(api_key=api_key, model=model)

    if provider == "anthropic":
        api_key = str(getattr(settings, "anthropic_api_key", "")).strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for llm_provider=anthropic")
        model = str(getattr(settings, "anthropic_model", "claude-sonnet-4-20250514")).strip()
        model = model or "claude-sonnet-4-20250514"
        return AnthropicClient(api_key=api_key, model=model)

    if provider == "ollama":
        base_url = str(getattr(settings, "ollama_url", "http://localhost:11434")).strip()
        model = str(getattr(settings, "ollama_model", "llama3")).strip() or "llama3"
        return OllamaClient(base_url=base_url or "http://localhost:11434", model=model)

    if provider == "gemini":
        api_key = str(getattr(settings, "gemini_api_key", "")).strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for llm_provider=gemini")
        model = str(getattr(settings, "gemini_model", "gemini-2.0-flash")).strip() or "gemini-2.0-flash"
        from api.services.chat_service import GeminiClient
        return GeminiClient(api_key=api_key, model=model)

    if provider == "lmstudio":
        base_url = str(getattr(settings, "lmstudio_url", "http://localhost:1234")).strip()
        model = str(getattr(settings, "lmstudio_model", "default")).strip() or "default"
        from api.services.chat_service import LMStudioClient
        return LMStudioClient(base_url=base_url or "http://localhost:1234", model=model)

    if provider == "echo":
        return EchoContextClient()

    raise ValueError(f"Unknown llm provider: {provider}")


def get_llm_model_name(settings: Any) -> str:
    provider = str(getattr(settings, "llm_provider", "ollama")).strip().lower()
    if provider == "openai":
        return str(getattr(settings, "openai_model", "gpt-4o-mini"))
    if provider == "anthropic":
        return str(getattr(settings, "anthropic_model", "claude-sonnet-4-20250514"))
    if provider == "ollama":
        return str(getattr(settings, "ollama_model", "llama3"))
    if provider == "gemini":
        return str(getattr(settings, "gemini_model", "gemini-2.0-flash"))
    if provider == "lmstudio":
        return str(getattr(settings, "lmstudio_model", "default"))
    if provider == "echo":
        return "echo-context"
    return "unknown"
