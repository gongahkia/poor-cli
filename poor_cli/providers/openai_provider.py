"""
OpenAI Provider Implementation

Supports current OpenAI GPT families and other compatible OpenAI models.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncIterator

try:
    from openai import AsyncOpenAI
    from openai import APIError as OpenAIAPIError, RateLimitError, APITimeoutError as OpenAITimeoutError, APIConnectionError as OpenAIConnectionError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None
    OPENAI_MISSING_HINT = "Install with: pip install 'poor-cli[openai]'"

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, FunctionCall, UsageMetadata
from .tool_translator import ToolTranslator, ProviderType
from ..provider_catalog import default_model_for_provider
from ..retry import RetryConfig, with_retry
from ..structured_output import (
    StructuredOutputConfig, build_openai_response_format,
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


class OpenAIProvider(BaseProvider):
    """OpenAI API provider implementation"""

    def preferred_edit_format(self) -> str:
        return "unified_diff"

    def __init__(self, api_key: str, model_name: str = default_model_for_provider("openai"),
                 max_retries: int = 3, retry_delay: float = 1.0, timeout: float = 60.0,
                 prompt_caching: bool = True, **kwargs):
        """
        Initialize OpenAI provider

        Args:
            api_key: OpenAI API key
            model_name: Model to use (for example gpt-5.1, gpt-5, gpt-5-mini)
            max_retries: Max retries for failed requests
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds
        """
        if not OPENAI_AVAILABLE:
            raise ConfigurationError(
                "OpenAI provider requires the 'openai' package. "
                "Install with: pip install 'poor-cli[openai]'"
            )

        super().__init__(api_key, model_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout

        # Initialize OpenAI client
        try:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                max_retries=0,  # We handle retries ourselves
                timeout=timeout
            )
            logger.info("OpenAI provider initialized")
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize OpenAI: {e}")

        self.prompt_caching = prompt_caching
        self.messages = []  # Conversation history
        self.tools = None
        self.system_instruction = None

    async def initialize(self, tools: Optional[List[Dict[str, Any]]] = None,
                        system_instruction: Optional[str] = None):
        """Initialize with tools and system instructions"""
        try:
            # Translate tools to OpenAI format
            if tools:
                self.tools = ToolTranslator.translate(tools, ProviderType.OPENAI)
                logger.info(f"Translated {len(self.tools)} tools to OpenAI format")

            # Store system instruction
            if system_instruction:
                self.system_instruction = system_instruction

            logger.info(f"OpenAI model {self.model_name} initialized")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize OpenAI: {e}")

    def _build_request_messages(self) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if self.system_instruction:
            messages.append({
                "role": "system",
                "content": self.system_instruction,
            })
        if self.prompt_prefix:
            messages.append({
                "role": "user",
                "content": self.prompt_prefix,
            })
        messages.extend(self.messages)
        return messages

    async def send_message(self, message: Any, *,
                           structured_output: Optional[StructuredOutputConfig] = None) -> ProviderResponse:
        """Send message to OpenAI"""
        self._append_message(message)

        async def _do_send() -> ProviderResponse:
            try:
                request_params = {
                    "model": self.model_name,
                    "messages": self._build_request_messages(),
                }
                if self.tools:
                    request_params["tools"] = self.tools
                    request_params["tool_choice"] = "auto"
                if structured_output:
                    request_params["response_format"] = build_openai_response_format(structured_output)
                response = await self.client.chat.completions.create(**request_params)
                if structured_output:
                    get_so_metrics().record_structured_attempt(success=True)
                else:
                    get_so_metrics().record_unstructured()
                return self._parse_response(response)
            except RateLimitError as e:
                raise APIRateLimitError("OpenAI rate limit exceeded", str(e))
            except OpenAITimeoutError as e:
                raise APITimeoutError("OpenAI request timeout", str(e))
            except OpenAIConnectionError as e:
                raise APIConnectionError("OpenAI connection error", str(e))
            except (APIError, ConfigurationError):
                raise
            except Exception as e:
                raise APIError(f"OpenAI API error: {e}", str(e))

        try:
            return await with_retry(
                _do_send,
                config=RetryConfig(max_retries=self.max_retries, base_delay=self.retry_delay, jitter=True),
                retryable=lambda e: isinstance(e, (APITimeoutError, APIRateLimitError, APIConnectionError)),
            )
        except Exception:
            if structured_output:  # fallback: retry without structured constraint
                get_so_metrics().record_structured_attempt(success=False)
                logger.warning("structured output failed for OpenAI; retrying unconstrained")
                self.messages.pop()  # remove the duplicate user message
                return await self.send_message(message, structured_output=None)
            raise

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        """Stream response from OpenAI"""
        self._append_message(message)

        try:
            # Prepare request
            request_params = {
                "model": self.model_name,
                "messages": self._build_request_messages(),
                "stream": True,
                "stream_options": {"include_usage": True},
            }

            if self.tools:
                request_params["tools"] = self.tools
                request_params["tool_choice"] = "auto"

            # economy mode output cap
            if self.economy_max_output_tokens > 0:
                request_params["max_tokens"] = self.economy_max_output_tokens

            # Stream response
            accumulated_content = ""
            accumulated_tool_calls = {}
            stream_usage = None

            async for chunk in await self.client.chat.completions.create(**request_params):
                # capture usage from final chunk (stream_options include_usage)
                if hasattr(chunk, 'usage') and chunk.usage:
                    prompt_details = getattr(chunk.usage, "prompt_tokens_details", None)
                    cached_tokens = getattr(prompt_details, "cached_tokens", 0) or 0
                    stream_usage = UsageMetadata(
                        input_tokens=chunk.usage.prompt_tokens or 0,
                        output_tokens=chunk.usage.completion_tokens or 0,
                        total_tokens=chunk.usage.total_tokens or 0,
                        cache_read_input_tokens=cached_tokens,
                        prompt_tokens=chunk.usage.prompt_tokens or 0,
                        completion_tokens=chunk.usage.completion_tokens or 0,
                    )
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    # Handle text content
                    if hasattr(delta, 'content') and delta.content:
                        accumulated_content += delta.content

                        yield ProviderResponse(
                            content=delta.content,
                            role="assistant",
                            raw_response=chunk,
                            metadata={"is_chunk": True}
                        )

                    # Handle tool calls (streaming)
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {
                                    "id": tc_chunk.id or "",
                                    "name": "",
                                    "arguments": ""
                                }

                            if hasattr(tc_chunk, 'id') and tc_chunk.id:
                                accumulated_tool_calls[idx]["id"] = tc_chunk.id

                            if hasattr(tc_chunk, 'function'):
                                if hasattr(tc_chunk.function, 'name') and tc_chunk.function.name:
                                    accumulated_tool_calls[idx]["name"] = tc_chunk.function.name
                                if hasattr(tc_chunk.function, 'arguments') and tc_chunk.function.arguments:
                                    accumulated_tool_calls[idx]["arguments"] += tc_chunk.function.arguments

            # Add final message to history
            assistant_message = {"role": "assistant"}

            if accumulated_content:
                assistant_message["content"] = accumulated_content

            if accumulated_tool_calls:
                # Convert accumulated tool calls to proper format
                tool_calls_list = []
                function_calls = []
                for idx in sorted(accumulated_tool_calls.keys()):
                    tc = accumulated_tool_calls[idx]
                    tool_calls_list.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                        }
                    })
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    function_calls.append(FunctionCall(
                        id=tc["id"],
                        name=tc["name"],
                        arguments=args,
                    ))
                assistant_message["tool_calls"] = tool_calls_list

                # Yield final response with tool calls so the agentic loop can execute them
                usage_meta = None
                if stream_usage:
                    usage_meta = {
                        "input_tokens": stream_usage.input_tokens,
                        "output_tokens": stream_usage.output_tokens,
                        "cache_read_input_tokens": stream_usage.cache_read_input_tokens,
                    }
                yield ProviderResponse(
                    content=accumulated_content,
                    role="assistant",
                    function_calls=function_calls,
                    metadata={"is_chunk": False, "usage": usage_meta} if usage_meta else {"is_chunk": False},
                    usage=stream_usage,
                )

            elif stream_usage:
                # no tool calls but we have usage — yield final with usage
                yield ProviderResponse(
                    content="",
                    role="assistant",
                    metadata={"usage": {
                        "input_tokens": stream_usage.input_tokens,
                        "output_tokens": stream_usage.output_tokens,
                        "cache_read_input_tokens": stream_usage.cache_read_input_tokens,
                    }},
                    usage=stream_usage,
                )

            self.messages.append(assistant_message)

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise APIError(f"OpenAI streaming error: {e}", str(e))

    def _append_message(self, message: Any) -> None:
        """Append or extend chat history with user/tool messages."""
        if isinstance(message, str):
            self.messages.append({
                "role": "user",
                "content": message
            })
            return

        if (
            isinstance(message, list)
            and len(message) > 0
            and isinstance(message[0], dict)
            and "type" in message[0]
        ):
            self.messages.append({
                "role": "user",
                "content": message,
            })
            return

        if isinstance(message, list) and all(isinstance(item, dict) for item in message):
            self.messages.extend(message)
            return

        self.messages.append(message)

    def format_tool_results(self, tool_results: List[Dict[str, Any]]) -> Any:
        """Format tool results for OpenAI function-calling follow-up turns."""
        return [
            {
                "role": "tool",
                "tool_call_id": tool_result["id"],
                "content": tool_result["result"],
            }
            for tool_result in tool_results
        ]

    def _parse_response(self, response: Any) -> ProviderResponse:
        """
        Parse OpenAI response into normalized ProviderResponse

        Args:
            response: OpenAI response object

        Returns:
            Normalized ProviderResponse
        """
        try:
            choice = response.choices[0]
            message = choice.message

            # Extract content
            content = message.content or ""

            # Extract reasoning/thinking content (o-series models)
            thinking_content = getattr(message, 'reasoning_content', None) or ""

            # Extract function calls
            function_calls = None
            if hasattr(message, 'tool_calls') and message.tool_calls:
                function_calls = []
                for tc in message.tool_calls:
                    try:
                        # Parse arguments JSON
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse tool arguments: {tc.function.arguments}")
                        args = {}

                    function_calls.append(FunctionCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args
                    ))

            # Build assistant message for history
            assistant_message = {"role": "assistant"}

            if content:
                assistant_message["content"] = content

            if hasattr(message, 'tool_calls') and message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]

            # Add to history
            self.messages.append(assistant_message)

            usage_obj = None
            usage_meta = None
            if hasattr(response, 'usage') and response.usage:
                prompt_details = getattr(response.usage, "prompt_tokens_details", None)
                cached_tokens = getattr(prompt_details, "cached_tokens", 0) or 0
                usage_obj = UsageMetadata(
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    cache_read_input_tokens=cached_tokens,
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                )
                usage_meta = {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "cache_read_input_tokens": cached_tokens,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }
            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=choice.finish_reason,
                function_calls=function_calls,
                raw_response=response,
                metadata={
                    "model": response.model,
                    "usage": usage_meta,
                },
                thinking_content=thinking_content or None,
                usage=usage_obj,
            )

        except Exception as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return ProviderResponse(
                content="",
                role="assistant",
                raw_response=response,
                metadata={"parse_error": str(e)}
            )

    async def clear_history(self):
        """Clear OpenAI conversation history"""
        self.messages = []
        logger.info("OpenAI history cleared")

    def get_history(self) -> List[Dict[str, Any]]:
        """Get OpenAI conversation history"""
        return self.messages.copy()

    def set_history(self, messages: List[Dict[str, Any]]) -> None:
        filtered = [m for m in messages if m.get("role") != "system"]
        # Sanitize tool_calls / tool message pairs after context compaction.
        # OpenAI rejects orphaned tool results (role=tool without a preceding
        # assistant message that has a matching tool_calls entry).
        # First pass: collect tool_call IDs that have matching results.
        provided_tool_call_ids: set = set()
        result_tool_call_ids: set = set()
        for msg in filtered:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_id = tc.get("id", "")
                    if tc_id:
                        provided_tool_call_ids.add(tc_id)
            elif msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id", "")
                if tc_id:
                    result_tool_call_ids.add(tc_id)
        # IDs that have both a call and a result are valid pairs.
        valid_ids = provided_tool_call_ids & result_tool_call_ids
        orphan_calls = provided_tool_call_ids - valid_ids
        orphan_results = result_tool_call_ids - valid_ids
        # Second pass: strip orphans.
        cleaned: list = []
        for msg in filtered:
            if msg.get("role") == "tool" and msg.get("tool_call_id", "") in orphan_results:
                continue  # drop orphaned tool result
            if msg.get("role") == "assistant" and msg.get("tool_calls") and orphan_calls:
                # Remove orphaned tool_calls entries; keep valid ones.
                kept = [tc for tc in msg["tool_calls"] if tc.get("id", "") not in orphan_calls]
                sanitized = dict(msg)
                if kept:
                    sanitized["tool_calls"] = kept
                else:
                    del sanitized["tool_calls"]
                    if not sanitized.get("content"):
                        sanitized["content"] = ""
                cleaned.append(sanitized)
            else:
                cleaned.append(msg)
        self.messages = cleaned

    def update_system_instruction(self, instruction: str) -> None:
        self.system_instruction = instruction

    def get_capabilities(self) -> ProviderCapabilities:
        """Get OpenAI capabilities"""
        supports_vision = "vision" in self.model_name.lower() or "gpt-4" in self.model_name
        # prefer catalog context window, fall back to heuristic
        from ..provider_catalog import get_model_context_window
        max_tokens = get_model_context_window("openai", self.model_name)
        if not max_tokens:
            max_tokens = 128000 if "turbo" in self.model_name or "gpt-4" in self.model_name else 8192

        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_system_instructions=True,
            max_context_tokens=max_tokens,
            supports_vision=supports_vision,
            supports_json_mode=True,
            supports_code_interpreter=False,
            supports_structured_output=True,
        )
