"""LiteLLM provider — catch-all routing to 100+ backends.

Useful when the user wants poor-cli to talk to a provider that does not have
a native adapter (Cohere, Mistral, Vertex AI, Bedrock, Groq, Together,
Perplexity, Replicate, etc.). Native adapters (Gemini, OpenAI, Anthropic,
OpenRouter, Ollama) stay preferred because they carry provider-specific
features like explicit prompt caching.

Model names follow the ``<vendor>/<model>`` convention litellm uses, e.g.:
- ``groq/llama-3.1-70b-versatile``
- ``cohere/command-r-plus``
- ``mistral/mistral-large-latest``
- ``bedrock/anthropic.claude-3-sonnet-20240229-v1:0``

Credentials come from the shared keyring / env / plaintext chain — litellm
respects standard env vars (``OPENAI_API_KEY``, ``COHERE_API_KEY``,
``ANTHROPIC_API_KEY`` etc.) so most setups Just Work.

Portability: litellm itself is stateless at the call layer; we do not
activate its caching/memory sidekicks. The portability gate (MH9) still
rejects any stateful-API passthrough (``store=True``, ``previous_response_id``)
that would bind a session to the backend.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    from litellm import acompletion  # type: ignore
    LITELLM_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dep
    LITELLM_AVAILABLE = False
    acompletion = None

from .base import (
    BaseProvider,
    FunctionCall,
    ProviderCapabilities,
    ProviderResponse,
    UsageMetadata,
)
from .capability import PROVIDER_CAPABILITIES
from ..exceptions import APIError, ConfigurationError, setup_logger

logger = setup_logger(__name__)


class LiteLLMProvider(BaseProvider):
    """Catch-all provider that routes via litellm to any supported backend."""

    capabilities = PROVIDER_CAPABILITIES["litellm"]

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 60.0,
        base_url: Optional[str] = None,
        **_: Any,
    ):
        if not LITELLM_AVAILABLE:
            raise ConfigurationError(
                "LiteLLM provider requires the 'litellm' package. "
                "Install with: pip install litellm"
            )
        if not model_name:
            raise ConfigurationError(
                "LiteLLM provider requires an explicit model_name "
                "(e.g. 'groq/llama-3.1-70b-versatile')."
            )
        super().__init__(api_key, model_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.base_url = base_url
        self.messages: List[Dict[str, Any]] = []
        self.tools: Optional[List[Dict[str, Any]]] = None
        self.system_instruction: Optional[str] = None
        self._structured_output = None

    # ── initialization ─────────────────────────────────────────────────

    async def initialize(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> None:
        if tools:
            self.tools = [
                {"type": "function", "function": tool}
                for tool in tools
            ]
        if system_instruction:
            self.system_instruction = system_instruction
        logger.info("LiteLLM provider initialized (model=%s)", self.model_name)

    # ── send ────────────────────────────────────────────────────────────

    def _build_messages(self, message: Any) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        if self.system_instruction:
            msgs.append({"role": "system", "content": self.system_instruction})
        msgs.extend(self.messages)
        if isinstance(message, str):
            msgs.append({"role": "user", "content": message})
        elif isinstance(message, dict):
            msgs.append(message)
        elif isinstance(message, list):
            msgs.extend(message)
        return msgs

    def _extract_function_calls(self, msg: Any) -> Optional[List[FunctionCall]]:
        tool_calls = getattr(msg, "tool_calls", None) or (msg.get("tool_calls") if isinstance(msg, dict) else None)
        if not tool_calls:
            return None
        out: List[FunctionCall] = []
        for call in tool_calls:
            if hasattr(call, "function"):
                fn = call.function
                name = getattr(fn, "name", "")
                args_raw = getattr(fn, "arguments", "{}")
                call_id = getattr(call, "id", "") or name
            else:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args_raw = fn.get("arguments", "{}")
                call_id = call.get("id", "") or name
            try:
                arguments = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except (json.JSONDecodeError, ValueError):
                arguments = {}
            if name:
                out.append(FunctionCall(id=str(call_id or name), name=str(name), arguments=arguments))
        return out or None

    async def send_message(
        self,
        message: Any,
        *,
        structured_output: Any = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        if not LITELLM_AVAILABLE or acompletion is None:
            raise ConfigurationError("litellm not installed")
        messages = self._build_messages(message)
        call_kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "timeout": self.timeout,
        }
        if self.api_key:
            call_kwargs["api_key"] = self.api_key
        if self.base_url:
            call_kwargs["api_base"] = self.base_url
        if self.tools:
            call_kwargs["tools"] = self.tools
        if structured_output is not None:
            from ..structured_output import build_openai_response_format
            call_kwargs["response_format"] = build_openai_response_format(structured_output)
        try:
            response = await acompletion(**call_kwargs)
        except Exception as exc:
            raise APIError(f"litellm call failed: {exc}") from exc

        # response is a ModelResponse (or dict-compatible) with OpenAI-like shape
        choice = response.choices[0] if hasattr(response, "choices") else response["choices"][0]
        msg = getattr(choice, "message", None) or choice.get("message", {})
        content = getattr(msg, "content", None) or msg.get("content", "") or ""
        finish_reason = getattr(choice, "finish_reason", None) or choice.get("finish_reason", None)

        usage_raw = getattr(response, "usage", None) or response.get("usage", {}) if isinstance(response, dict) else getattr(response, "usage", None)
        usage_md = UsageMetadata()
        if usage_raw:
            def _get(obj, k, default=0):
                return getattr(obj, k, None) if hasattr(obj, k) else obj.get(k, default) if isinstance(obj, dict) else default
            usage_md.input_tokens = int(_get(usage_raw, "prompt_tokens", 0) or 0)
            usage_md.output_tokens = int(_get(usage_raw, "completion_tokens", 0) or 0)
            usage_md.total_tokens = int(_get(usage_raw, "total_tokens", 0) or 0)
            usage_md.prompt_tokens = usage_md.input_tokens
            usage_md.completion_tokens = usage_md.output_tokens

        function_calls = self._extract_function_calls(msg)

        result = ProviderResponse(
            content=str(content or ""),
            role="assistant",
            finish_reason=str(finish_reason) if finish_reason else None,
            function_calls=function_calls,
            raw_response=response,
            metadata={"backend": "litellm", "model": self.model_name},
            usage=usage_md,
        )

        # record to local history so swap-provider preserves context
        self.messages.append({"role": "user", "content": message if isinstance(message, str) else json.dumps(message)})
        if result.content:
            self.messages.append({"role": "assistant", "content": result.content})
        return result

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        # Simplified streaming: issue a non-streaming call and yield once.
        # litellm supports stream=True; native streaming can be added later.
        response = await self.send_message(message)
        yield response

    async def clear_history(self) -> None:
        self.messages = []

    def get_history(self) -> List[Dict[str, Any]]:
        return [dict(m) for m in self.messages]

    def set_history(self, messages: List[Dict[str, Any]]) -> None:
        self.messages = [dict(m) for m in messages]

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_system_instructions=True,
            supports_json_mode=True,
            supports_vision=True,
            max_context_tokens=128_000,
            supports_structured_output=True,
        )

    def format_tool_results(self, tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OpenAI-compatible tool result formatting."""
        formatted = []
        for entry in tool_results:
            formatted.append({
                "role": "tool",
                "tool_call_id": entry.get("id", entry.get("name", "")),
                "content": json.dumps(entry.get("result")) if not isinstance(entry.get("result"), str) else entry["result"],
            })
        self.messages.extend(formatted)
        return formatted
