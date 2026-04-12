"""
Gemini AI Provider Implementation.

Uses the `google-genai` unified SDK with a compatibility bridge for
legacy protobuf Content tool-result payloads.
"""

import asyncio
import base64
import json
from typing import List, Dict, Any, Optional, AsyncIterator

try:
    from google import genai
    from google.genai import types as genai_types
    from google.genai import errors as genai_errors

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None
    genai_types = None
    genai_errors = None

try:
    from google.protobuf.json_format import MessageToDict
except ImportError:  # pragma: no cover - protobuf is an indirect dependency.
    MessageToDict = None

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, FunctionCall, UsageMetadata
from .capability import PROVIDER_CAPABILITIES
from .tool_translator import ToolTranslator, ProviderType
from ..provider_catalog import default_model_for_provider
from ..retry import RetryConfig, with_retry
from ..structured_output import (
    StructuredOutputConfig, build_gemini_response_schema,
    get_metrics as get_so_metrics,
)
from ..exceptions import (
    APIError,
    APIRateLimitError,
    APITimeoutError,
    APIConnectionError,
    ConfigurationError,
    setup_logger,
)

logger = setup_logger(__name__)


class GeminiProvider(BaseProvider):
    """Gemini provider implementation backed by `google-genai`."""

    capabilities = PROVIDER_CAPABILITIES["gemini"]

    def preferred_edit_format(self) -> str:
        return "search_replace"

    def __init__(
        self,
        api_key: str,
        model_name: str = default_model_for_provider("gemini"),
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 60.0,
    ):
        """Initialize Gemini provider.

        Args:
            api_key: Gemini API key.
            model_name: Model to use.
            max_retries: Maximum retries for retryable request failures.
            retry_delay: Initial retry delay in seconds.
            timeout: Per-request timeout in seconds.
        """
        if not GENAI_AVAILABLE:
            raise ConfigurationError(
                "Gemini provider requires 'google-genai'. " "Install with: pip install google-genai"
            )

        super().__init__(api_key, model_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout

        try:
            self.client = genai.Client(api_key=self.api_key).aio
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize Gemini client: {e}")

        self.chat = None
        self._chat_config = None
        self._cached_content_name: Optional[str] = None
        self._cached_content_hash: Optional[str] = None

    async def initialize(
        self,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ):
        """Initialize Gemini chat session with tool declarations and system instruction."""
        try:
            config_kwargs: Dict[str, Any] = {
                "automatic_function_calling": (
                    genai_types.AutomaticFunctionCallingConfig(disable=True)
                )
            }

            if tools:
                translated_tools = ToolTranslator.translate(tools, ProviderType.GEMINI)
                config_kwargs["tools"] = [
                    genai_types.Tool(function_declarations=translated_tools)
                ]

            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction

            # attempt server-side context caching for large system+tools payload
            # Gemini context caching minimum is ~32K tokens (~128K chars)
            import hashlib as _hl
            cacheable_chars = len(system_instruction or "")
            _tool_json = json.dumps(translated_tools) if tools else ""
            if tools:
                cacheable_chars += len(_tool_json)
            _content_hash = _hl.sha256(((system_instruction or "") + _tool_json).encode("utf-8", errors="replace")).hexdigest()
            if cacheable_chars > 32000:
                # reuse existing cache if content hasn't changed
                if self._cached_content_name and self._cached_content_hash == _content_hash:
                    config_kwargs.pop("system_instruction", None)
                    config_kwargs.pop("tools", None)
                    config_kwargs["cached_content"] = self._cached_content_name
                    logger.info("Gemini context cache reused (hash match): %s", self._cached_content_name)
                else:
                    # invalidate stale cache
                    if self._cached_content_name and self._cached_content_hash != _content_hash:
                        try:
                            await self.client.caches.delete(name=self._cached_content_name)
                            logger.info("Deleted stale Gemini cache: %s", self._cached_content_name)
                        except Exception:
                            pass
                        self._cached_content_name = None
                        self._cached_content_hash = None
                    try:
                        cache_config = genai_types.CreateCachedContentConfig(
                            display_name="poor-cli-context-cache",
                        )
                        if system_instruction:
                            cache_config.system_instruction = system_instruction
                        if tools and translated_tools:
                            cache_config.tools = [genai_types.Tool(function_declarations=translated_tools)]
                        cached = await self.client.caches.create(
                            model=self.model_name,
                            config=cache_config,
                        )
                        if cached and getattr(cached, "name", None):
                            self._cached_content_name = cached.name
                            self._cached_content_hash = _content_hash
                            config_kwargs.pop("system_instruction", None)
                            config_kwargs.pop("tools", None)
                            config_kwargs["cached_content"] = cached.name
                            logger.info("Gemini context cache created (system+tools): %s", cached.name)
                    except Exception as exc:
                        logger.debug("Gemini context caching unavailable: %s", exc)

            self._chat_config = genai_types.GenerateContentConfig(**config_kwargs)
            self.chat = self.client.chats.create(
                model=self.model_name,
                config=self._chat_config,
            )
            logger.info(f"Gemini model {self.model_name} initialized")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize Gemini model: {e}")

    async def send_message(self, message: Any, *,
                           structured_output: Optional[StructuredOutputConfig] = None) -> ProviderResponse:
        """Send message to Gemini and return normalized response."""
        if self.chat is None:
            raise ConfigurationError("Gemini provider not initialized")

        normalized_message = self._normalize_message(message)
        # temporarily inject response_schema if structured output requested
        _prev_schema = None
        if structured_output and self._chat_config is not None:
            _prev_schema = getattr(self._chat_config, "response_schema", None)
            try:
                self._chat_config.response_schema = build_gemini_response_schema(structured_output)
                self._chat_config.response_mime_type = "application/json"
            except Exception:
                pass  # graceful: schema injection unsupported

        async def _do_send() -> ProviderResponse:
            try:
                response = await asyncio.wait_for(
                    self.chat.send_message(normalized_message),
                    timeout=self.timeout,
                )
                if structured_output:
                    get_so_metrics().record_structured_attempt(success=True)
                else:
                    get_so_metrics().record_unstructured()
                return self._parse_response(response)
            except asyncio.TimeoutError as e:
                raise APITimeoutError("Gemini request timeout", str(e))
            except genai_errors.APIError as e:
                raise self._map_api_error(e)
            except (APIError, ConfigurationError):
                raise
            except Exception as e:
                raise APIError(f"Failed to send message: {e}", str(e))

        try:
            return await with_retry(
                _do_send,
                config=RetryConfig(max_retries=self.max_retries, base_delay=self.retry_delay, jitter=True),
                retryable=lambda e: isinstance(e, (APITimeoutError, APIRateLimitError, APIConnectionError)),
            )
        except Exception:
            if structured_output:
                get_so_metrics().record_structured_attempt(success=False)
                logger.warning("structured output failed for Gemini; retrying unconstrained")
                if self._chat_config is not None:
                    self._chat_config.response_schema = _prev_schema
                    try:
                        del self._chat_config.response_mime_type
                    except Exception:
                        pass
                return await self.send_message(message, structured_output=None)
            raise
        finally:
            if structured_output and self._chat_config is not None:
                self._chat_config.response_schema = _prev_schema
                try:
                    del self._chat_config.response_mime_type
                except Exception:
                    pass

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        """Stream response chunks from Gemini."""
        if self.chat is None:
            raise ConfigurationError("Gemini provider not initialized")

        if self.economy_max_output_tokens > 0 and self._chat_config is not None:
            try:
                self._chat_config.max_output_tokens = self.economy_max_output_tokens
            except Exception:
                pass

        normalized_message = self._normalize_message(message)
        retry_cfg = RetryConfig(max_retries=self.max_retries, base_delay=self.retry_delay, jitter=True)

        for attempt in range(retry_cfg.max_retries):
            received_chunk = False
            try:
                stream = await asyncio.wait_for(
                    self.chat.send_message_stream(normalized_message),
                    timeout=self.timeout,
                )
                while True:
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=self.timeout)
                    received_chunk = True
                    yield self._parse_response(chunk, is_chunk=True)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError as e:
                if not received_chunk and attempt < retry_cfg.max_retries - 1:
                    delay = retry_cfg.base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                raise APITimeoutError("Gemini streaming request timeout", str(e))
            except genai_errors.APIError as e:
                mapped = self._map_api_error(e)
                if not received_chunk and self._is_retryable_error(e) and attempt < retry_cfg.max_retries - 1:
                    delay = retry_cfg.base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                raise mapped
            except Exception as e:
                raise APIError(f"Streaming failed: {e}", str(e))

    def format_tool_results(self, tool_results: List[Dict[str, Any]]) -> Any:
        """Format tool results as Gemini function-response parts."""
        return [
            genai_types.Part.from_function_response(
                name=tool_result["name"],
                response={"result": tool_result["result"]},
            )
            for tool_result in tool_results
        ]

    def _normalize_message(self, message: Any) -> Any:
        """Normalize caller payloads into `google-genai` chat message shapes."""
        if isinstance(message, str):
            if self.prompt_prefix:
                return f"{self.prompt_prefix}\n\n{message}"
            return message

        if (
            isinstance(message, list)
            and message
            and all(isinstance(item, dict) for item in message)
        ):
            parts: List[Any] = []
            if self.prompt_prefix and all(item.get("type") in ("image", "text") for item in message):
                parts.append(genai_types.Part.from_text(text=self.prompt_prefix))
            for item in message:
                inline_data = item.get("inline_data")
                if isinstance(inline_data, dict):
                    try:
                        parts.append(
                            genai_types.Part(
                                inline_data=genai_types.Blob(
                                    mime_type=inline_data["mime_type"],
                                    data=base64.b64decode(inline_data["data"]),
                                )
                            )
                        )
                        continue
                    except Exception:
                        logger.debug("Failed to parse inline_data part for Gemini", exc_info=True)

                if "text" in item:
                    parts.append(genai_types.Part.from_text(text=str(item["text"])))
            if parts:
                return parts

        legacy_parts = self._legacy_content_to_parts(message)
        if legacy_parts is not None:
            return legacy_parts

        return message

    def _legacy_content_to_parts(self, message: Any) -> Optional[List[Any]]:
        """Convert legacy `protos.Content` tool responses to `types.Part` list."""
        parts = getattr(message, "parts", None)
        if parts is None:
            return None

        converted_parts = []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                converted_parts.append(genai_types.Part.from_text(text=text))
                continue

            function_response = getattr(part, "function_response", None)
            if function_response is None:
                continue

            name = getattr(function_response, "name", "")
            if not name:
                continue

            converted_parts.append(
                genai_types.Part.from_function_response(
                    name=name,
                    response=self._coerce_response_payload(
                        getattr(function_response, "response", {})
                    ),
                )
            )

        return converted_parts if converted_parts else None

    def _coerce_response_payload(self, payload: Any) -> Dict[str, Any]:
        """Convert protobuf structs and other payload objects into dictionaries."""
        if isinstance(payload, dict):
            return payload

        if MessageToDict is not None:
            try:
                converted = MessageToDict(payload, preserving_proto_field_name=True)
                if isinstance(converted, dict):
                    return converted
            except Exception:
                pass

        try:
            items = dict(payload.items())
            if isinstance(items, dict):
                return items
        except Exception:
            pass

        return {"result": str(payload)}

    def _is_retryable_error(self, error: Exception) -> bool:
        """Return True if a Gemini SDK error should be retried."""
        code = getattr(error, "code", None)
        return code in {408, 429, 500, 502, 503, 504}

    def _map_api_error(self, error: Exception) -> APIError:
        """Map Gemini SDK exceptions to poor-cli API exception types."""
        code = getattr(error, "code", None)

        if code == 429:
            return APIRateLimitError("Gemini rate limit exceeded", str(error))

        if code in {408, 504}:
            return APITimeoutError("Gemini request timeout", str(error))

        if code in {502, 503}:
            return APIConnectionError("Gemini API temporarily unavailable", str(error))

        return APIError(f"Gemini API error: {error}", str(error))

    def _parse_response(self, response: Any, is_chunk: bool = False) -> ProviderResponse:
        """Parse Gemini SDK responses into normalized `ProviderResponse`."""
        try:
            content = response.text or ""
            function_calls: List[FunctionCall] = []

            for fc in response.function_calls or []:
                if not fc.name:
                    continue

                function_calls.append(
                    FunctionCall(
                        id=fc.id or f"gemini_{fc.name}",
                        name=fc.name,
                        arguments=fc.args or {},
                    )
                )

            finish_reason = None
            if getattr(response, "candidates", None):
                candidate = response.candidates[0]
                if getattr(candidate, "finish_reason", None) is not None:
                    finish_reason = str(candidate.finish_reason)

            usage_obj = None
            raw_usage = getattr(response, "usage_metadata", None)
            if raw_usage:
                in_tok = getattr(raw_usage, "prompt_token_count", 0) or 0
                out_tok = getattr(raw_usage, "candidates_token_count", 0) or 0
                cached_tok = getattr(raw_usage, "cached_content_token_count", 0) or 0
                usage_obj = UsageMetadata(input_tokens=in_tok, output_tokens=out_tok,
                                          cache_read_input_tokens=cached_tok)
            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=finish_reason,
                function_calls=function_calls if function_calls else None,
                raw_response=response,
                metadata={"is_chunk": is_chunk},
                usage=usage_obj,
            )

        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            return ProviderResponse(
                content="",
                role="assistant",
                raw_response=response,
                metadata={"parse_error": str(e), "is_chunk": is_chunk},
            )

    async def clear_history(self):
        """Clear Gemini conversation history by starting a new chat session."""
        if self._chat_config is None:
            raise ConfigurationError("Gemini provider not initialized")

        try:
            self.chat = self.client.chats.create(
                model=self.model_name,
                config=self._chat_config,
            )
            logger.info("Gemini history cleared")
        except Exception as e:
            raise APIError(f"Failed to clear history: {e}", str(e))

    def get_history(self) -> List[Dict[str, Any]]:
        """Get Gemini conversation history."""
        if self.chat is None:
            return []

        try:
            history = []
            for message in self.chat.get_history():
                parts = []
                for part in getattr(message, "parts", []) or []:
                    if getattr(part, "text", None):
                        parts.append(part.text)
                    elif getattr(part, "function_call", None):
                        parts.append(
                            {
                                "function_call": {
                                    "name": part.function_call.name,
                                    "args": part.function_call.args,
                                }
                            }
                        )
                    elif getattr(part, "function_response", None):
                        parts.append(
                            {
                                "function_response": {
                                    "name": part.function_response.name,
                                    "response": part.function_response.response,
                                }
                            }
                        )

                history.append(
                    {
                        "role": message.role,
                        "parts": parts,
                    }
                )

            return history
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []

    def set_history(self, messages: List[Dict[str, Any]]) -> None:
        """Restore history by recreating the chat with prior turns as context.

        Gemini's chat object manages history internally so we cannot inject
        raw messages.  Instead we create a fresh chat seeded with the prior
        history converted to ``Content`` objects.
        """
        if self._chat_config is None:
            return
        history_parts: List[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            parts = msg.get("parts", [])
            text_parts = []
            for p in parts:
                if isinstance(p, str):
                    text_parts.append(genai_types.Part.from_text(text=p))
                elif isinstance(p, dict) and "text" in p:
                    text_parts.append(genai_types.Part.from_text(text=p["text"]))
            if text_parts:
                history_parts.append(genai_types.Content(role=role, parts=text_parts))
        self.chat = self.client.chats.create(
            model=self.model_name,
            config=self._chat_config,
            history=history_parts if history_parts else None,
        )

    def update_system_instruction(self, instruction: str) -> None:
        self.system_instruction = instruction
        if self._chat_config is not None:
            self._chat_config = genai_types.GenerateContentConfig(
                system_instruction=instruction,
                tools=self._chat_config.tools if hasattr(self._chat_config, "tools") else None,
            )
            history = self.get_history()
            self.set_history(history)

    def get_capabilities(self) -> ProviderCapabilities:
        """Get Gemini capabilities."""
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_system_instructions=True,
            max_context_tokens=1000000,
            supports_vision=True,
            supports_json_mode=True,
            supports_code_interpreter=False,
            supports_structured_output=True,
        )
