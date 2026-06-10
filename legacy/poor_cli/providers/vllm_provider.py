"""vLLM OpenAI-compatible local text provider."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None
    AIOHTTP_AVAILABLE = False

from .base import BaseProvider, FunctionCall, ProviderCapabilities, ProviderResponse, UsageMetadata
from .capability import PROVIDER_CAPABILITIES
from ..exceptions import APIConnectionError, APIError, APITimeoutError, ConfigurationError, setup_logger
from ..provider_catalog import default_model_for_provider, get_model_context_window
from ..retry import RetryConfig, with_retry

logger = setup_logger(__name__)
_DEFAULT_VLLM_BASE_URL = "http://localhost:8000/v1"


class VLLMProvider(BaseProvider):
    """vLLM server provider.

    This is intentionally a text provider. vLLM's public server API does not
    expose a full hidden-state/KV hand-off endpoint for LatentMAS-style routing.
    """

    provider_key = "vllm"
    provider_label = "vLLM"
    default_base_url = _DEFAULT_VLLM_BASE_URL
    auth_env_var = "VLLM_API_KEY"
    capabilities = PROVIDER_CAPABILITIES["vllm"]
    available = AIOHTTP_AVAILABLE

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 120.0,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        if not AIOHTTP_AVAILABLE:
            raise ConfigurationError(f"{self.provider_label} provider requires aiohttp. Install with: pip install aiohttp")
        if not model_name:
            model_name = default_model_for_provider(self.provider_key)
        super().__init__(api_key or os.environ.get(self.auth_env_var, ""), model_name, **kwargs)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.base_url = (base_url or os.environ.get(f"{self.auth_env_var.removesuffix('_API_KEY')}_BASE_URL") or self.default_base_url).rstrip("/")
        self.messages: List[Dict[str, Any]] = []
        self.tools: Optional[List[Dict[str, Any]]] = None
        self.system_instruction: Optional[str] = None
        logger.info("%s provider initialized (server: %s, model=%s)", self.provider_label, self.base_url, self.model_name)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def initialize(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ):
        if tools:
            logger.warning("vLLM provider currently ignores tool declarations")
        self.system_instruction = system_instruction
        try:
            async with aiohttp.ClientSession(headers=self._headers()) as session:
                async with session.get(
                    f"{self.base_url}/models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status >= 400:
                        error_text = await resp.text()
                        raise ConfigurationError(f"{self.provider_label} server returned {resp.status}: {error_text}")
                    await resp.read()
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(
                f"{self.provider_label} server not available at {self.base_url}. "
                "Start the local OpenAI-compatible server and retry."
            ) from exc

    def _build_request_messages(self) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if self.system_instruction:
            messages.append({"role": "system", "content": self.system_instruction})
        if self.prompt_prefix:
            messages.append({"role": "user", "content": self.prompt_prefix})
        messages.extend(self.messages)
        return messages

    def _build_chat_request(self, stream: bool) -> Dict[str, Any]:
        request_data: Dict[str, Any] = {
            "model": self.model_name,
            "messages": self._build_request_messages(),
            "stream": stream,
        }
        if self.economy_max_output_tokens > 0:
            request_data["max_tokens"] = self.economy_max_output_tokens
        return request_data

    async def send_message(self, message: Any, **kwargs: Any) -> ProviderResponse:
        self._append_message(message)

        async def _do_send() -> ProviderResponse:
            try:
                async with aiohttp.ClientSession(headers=self._headers()) as session:
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        json=self._build_chat_request(stream=False),
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as resp:
                        if resp.status >= 400:
                            error_text = await resp.text()
                            raise APIError(f"{self.provider_label} error {resp.status}: {error_text}", error_text)
                        response_data = await resp.json()
                return self._parse_response(response_data)
            except asyncio.TimeoutError as exc:
                raise APITimeoutError(f"{self.provider_label} request timeout", str(exc))
            except aiohttp.ClientError as exc:
                raise APIConnectionError(f"{self.provider_label} connection error", str(exc))
            except (APIError, APITimeoutError, APIConnectionError):
                raise
            except Exception as exc:
                raise APIError(f"{self.provider_label} API error: {exc}", str(exc))

        return await with_retry(
            _do_send,
            config=RetryConfig(max_retries=self.max_retries, base_delay=self.retry_delay, jitter=True),
            retryable=lambda exc: isinstance(exc, (APITimeoutError, APIConnectionError)),
        )

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        self._append_message(message)
        accumulated_content = ""
        try:
            async with aiohttp.ClientSession(headers=self._headers()) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=self._build_chat_request(stream=True),
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status >= 400:
                        error_text = await resp.text()
                        raise APIError(f"{self.provider_label} error {resp.status}: {error_text}", error_text)
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        for item in line.splitlines():
                            item = item.strip()
                            if item.startswith("data:"):
                                item = item[5:].strip()
                            if not item or item == "[DONE]":
                                continue
                            try:
                                chunk_data = json.loads(item)
                            except json.JSONDecodeError:
                                logger.debug("failed to parse %s stream chunk: %s", self.provider_label, item)
                                continue
                            delta = (((chunk_data.get("choices") or [{}])[0]).get("delta") or {})
                            content = delta.get("content") or ""
                            if content:
                                accumulated_content += content
                                yield ProviderResponse(
                                    content=content,
                                    role="assistant",
                                    raw_response=chunk_data,
                                    metadata={"is_chunk": True},
                                )
            if accumulated_content:
                self.messages.append({"role": "assistant", "content": accumulated_content})
        except (APIError, APIConnectionError, APITimeoutError):
            raise
        except asyncio.TimeoutError as exc:
            raise APITimeoutError(f"{self.provider_label} streaming request timeout", str(exc))
        except aiohttp.ClientError as exc:
            raise APIConnectionError(f"{self.provider_label} streaming connection error", str(exc))
        except Exception as exc:
            raise APIError(f"{self.provider_label} streaming error: {exc}", str(exc))

    def _append_message(self, message: Any) -> None:
        if isinstance(message, str):
            self.messages.append({"role": "user", "content": message})
        elif isinstance(message, list) and all(isinstance(item, dict) for item in message):
            self.messages.extend(message)
        elif isinstance(message, dict):
            self.messages.append(message)
        else:
            self.messages.append({"role": "user", "content": str(message)})

    def _parse_response(self, response_data: Dict[str, Any]) -> ProviderResponse:
        try:
            choice = (response_data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            function_calls = None
            if message.get("tool_calls"):
                function_calls = []
                for tool_call in message.get("tool_calls") or []:
                    function = tool_call.get("function") or {}
                    raw_arguments = function.get("arguments") or {}
                    try:
                        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    except json.JSONDecodeError:
                        arguments = {}
                    function_calls.append(FunctionCall(
                        id=tool_call.get("id") or f"{self.provider_key}_{function.get('name', 'tool')}",
                        name=function.get("name") or "",
                        arguments=arguments,
                    ))
            self.messages.append({"role": "assistant", "content": content})
            usage_data = response_data.get("usage") or {}
            usage = None
            if usage_data:
                usage = UsageMetadata(
                    input_tokens=int(usage_data.get("prompt_tokens") or 0),
                    output_tokens=int(usage_data.get("completion_tokens") or 0),
                    total_tokens=int(usage_data.get("total_tokens") or 0),
                    prompt_tokens=int(usage_data.get("prompt_tokens") or 0),
                    completion_tokens=int(usage_data.get("completion_tokens") or 0),
                )
            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=choice.get("finish_reason"),
                function_calls=function_calls,
                raw_response=response_data,
                metadata={"model": response_data.get("model"), "usage": usage_data or None},
                usage=usage,
            )
        except Exception as exc:
            logger.error("Error parsing %s response: %s", self.provider_label, exc)
            return ProviderResponse(content="", role="assistant", raw_response=response_data, metadata={"parse_error": str(exc)})

    async def clear_history(self):
        self.messages = []

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.messages)

    def set_history(self, messages: List[Dict[str, Any]]) -> None:
        self.messages = [message for message in messages if message.get("role") != "system"]

    def get_capabilities(self) -> ProviderCapabilities:
        max_tokens = get_model_context_window(self.provider_key, self.model_name) or 32768
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=False,
            supports_system_instructions=True,
            max_context_tokens=max_tokens,
            supports_vision=False,
            supports_json_mode=False,
            supports_structured_output=False,
            supports_latent_communication=False,
        )

    def get_provider_name(self) -> str:
        return self.provider_key

    @classmethod
    async def discover_models(cls, base_url: str = "", api_key: str = "") -> List[str]:
        if not AIOHTTP_AVAILABLE:
            return []
        base_url = base_url or cls.default_base_url
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    f"{base_url.rstrip('/')}/models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status >= 400:
                        return []
                    payload = await resp.json()
        except Exception:
            return []
        return [
            str(model.get("id", "")).strip()
            for model in payload.get("data", [])
            if isinstance(model, dict) and str(model.get("id", "")).strip()
        ]
