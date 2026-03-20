"""
Anthropic (Claude) Provider Implementation

Supports current Claude and Anthropic model families.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncIterator

try:
    from anthropic import AsyncAnthropic
    from anthropic import APIError as AnthropicAPIError, RateLimitError as AnthropicRateLimitError
    from anthropic import APIConnectionError as AnthropicConnectionError, APITimeoutError as AnthropicTimeoutError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    AsyncAnthropic = None

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, FunctionCall, UsageMetadata
from .tool_translator import ToolTranslator, ProviderType
from ..provider_catalog import default_model_for_provider
from ..exceptions import (
    APIError,
    APIRateLimitError,
    APITimeoutError,
    APIConnectionError,
    ConfigurationError,
    setup_logger,
)

logger = setup_logger(__name__)


class AnthropicProvider(BaseProvider):
    """Anthropic (Claude) API provider implementation"""

    def __init__(self, api_key: str, model_name: str = default_model_for_provider("anthropic"),
                 max_retries: int = 3, retry_delay: float = 1.0, timeout: float = 60.0,
                 prompt_caching: bool = True):
        """
        Initialize Anthropic provider

        Args:
            api_key: Anthropic API key
            model_name: Model to use (for example claude-sonnet-4-20250514 or claude-3-7-sonnet-20250219)
            max_retries: Max retries for failed requests
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds
            prompt_caching: Enable cache_control injection on system/tools
        """
        if not ANTHROPIC_AVAILABLE:
            raise ConfigurationError(
                "Anthropic provider requires 'anthropic' package. "
                "Install with: pip install anthropic"
            )

        super().__init__(api_key, model_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.prompt_caching = prompt_caching

        # Initialize Anthropic client
        try:
            self.client = AsyncAnthropic(
                api_key=self.api_key,
                max_retries=0,  # We handle retries ourselves
                timeout=timeout
            )
            logger.info("Anthropic provider initialized")
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize Anthropic: {e}")

        self.messages = []  # Conversation history
        self.tools = None
        self.system_instruction = None

    async def initialize(self, tools: Optional[List[Dict[str, Any]]] = None,
                        system_instruction: Optional[str] = None):
        """Initialize with tools and system instructions"""
        try:
            # Translate tools to Anthropic format
            if tools:
                self.tools = ToolTranslator.translate(tools, ProviderType.ANTHROPIC)
                logger.info(f"Translated {len(self.tools)} tools to Anthropic format")

            # Store system instruction
            if system_instruction:
                self.system_instruction = system_instruction

            logger.info(f"Anthropic model {self.model_name} initialized")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize Anthropic: {e}")

    def _supports_extended_thinking(self) -> bool:
        """Check if current model supports extended thinking."""
        m = self.model_name.lower()
        return any(tag in m for tag in ("claude-3-7", "claude-4", "claude-opus", "claude-sonnet-4"))

    def _build_request_params(self) -> Dict[str, Any]:
        """Build common request params with optional thinking support."""
        params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": self.messages,
            "max_tokens": 16384,
        }
        if self._supports_extended_thinking():
            params["thinking"] = {"type": "enabled", "budget_tokens": 10000}
            params["max_tokens"] = 16384
        else:
            params["max_tokens"] = 4096
        if self.system_instruction:
            if self.prompt_caching:
                params["system"] = [{"type": "text", "text": self.system_instruction, "cache_control": {"type": "ephemeral"}}]
            else:
                params["system"] = self.system_instruction
        if self.tools:
            if self.prompt_caching and self.tools:
                tools_copy = [dict(t) for t in self.tools]
                tools_copy[-1] = {**tools_copy[-1], "cache_control": {"type": "ephemeral"}}
                params["tools"] = tools_copy
            else:
                params["tools"] = self.tools
        return params

    async def send_message(self, message: Any) -> ProviderResponse:
        """Send message to Anthropic"""
        self._append_message(message)

        for attempt in range(self.max_retries):
            try:
                request_params = self._build_request_params()

                # Send request
                response = await self.client.messages.create(**request_params)

                # Parse response
                return self._parse_response(response)

            except AnthropicRateLimitError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Rate limit, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APIRateLimitError("Anthropic rate limit exceeded", str(e))

            except AnthropicTimeoutError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Timeout, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APITimeoutError("Anthropic request timeout", str(e))

            except AnthropicConnectionError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Connection error, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APIConnectionError("Anthropic connection error", str(e))

            except Exception as e:
                logger.error(f"Anthropic error: {e}")
                raise APIError(f"Anthropic API error: {e}", str(e))

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        """Stream response from Anthropic"""
        self._append_message(message)

        try:
            request_params = self._build_request_params()
            request_params["stream"] = True

            # Stream response
            accumulated_content = ""
            accumulated_thinking = ""
            accumulated_tool_uses = []

            async with self.client.messages.stream(**request_params) as stream:
                async for event in stream:
                    if hasattr(event, 'type'):
                        if event.type == "content_block_delta":
                            if hasattr(event, 'delta'):
                                delta = event.delta
                                delta_type = getattr(delta, 'type', '')

                                if delta_type == "text_delta":
                                    text = getattr(delta, 'text', '')
                                    if text:
                                        accumulated_content += text
                                        yield ProviderResponse(
                                            content=text, role="assistant",
                                            raw_response=event,
                                            metadata={"is_chunk": True},
                                        )

                                elif delta_type == "thinking_delta":
                                    thinking = getattr(delta, 'thinking', '')
                                    if thinking:
                                        accumulated_thinking += thinking
                                        yield ProviderResponse(
                                            content="", role="assistant",
                                            thinking_content=thinking,
                                            metadata={"is_chunk": True, "is_thinking": True},
                                        )

                                elif delta_type == "input_json_delta":
                                    pass  # tool input streaming

                        elif event.type == "content_block_start":
                            if hasattr(event, 'content_block'):
                                block = event.content_block
                                block_type = getattr(block, 'type', '')
                                if block_type == "tool_use":
                                    accumulated_tool_uses.append({
                                        "id": block.id, "name": block.name, "input": {},
                                    })
                                elif block_type == "thinking":
                                    yield ProviderResponse(
                                        content="", role="assistant",
                                        metadata={"is_chunk": True, "thinking_started": True},
                                    )

                        elif event.type == "content_block_stop":
                            pass

            # Get final message (Anthropic stream provides it)
            final_message = await stream.get_final_message()

            # Add final message to history
            assistant_message = {"role": "assistant", "content": []}

            if accumulated_content:
                assistant_message["content"].append({
                    "type": "text",
                    "text": accumulated_content
                })

            # Build function calls and tool uses from final message
            final_function_calls = []
            if hasattr(final_message, 'content'):
                for block in final_message.content:
                    if hasattr(block, 'type') and block.type == "tool_use":
                        assistant_message["content"].append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                        final_function_calls.append(FunctionCall(
                            id=block.id, name=block.name,
                            arguments=block.input if hasattr(block, 'input') else {},
                        ))

            self.messages.append(assistant_message)

            # yield final response with actual usage and tool calls
            final_usage = None
            final_usage_meta = None
            if hasattr(final_message, 'usage') and final_message.usage:
                cache_creation = getattr(final_message.usage, "cache_creation_input_tokens", 0) or 0
                cache_read = getattr(final_message.usage, "cache_read_input_tokens", 0) or 0
                final_usage = UsageMetadata(
                    input_tokens=final_message.usage.input_tokens,
                    output_tokens=final_message.usage.output_tokens,
                    cache_creation_input_tokens=cache_creation,
                    cache_read_input_tokens=cache_read,
                )
                final_usage_meta = {
                    "input_tokens": final_message.usage.input_tokens,
                    "output_tokens": final_message.usage.output_tokens,
                    "cache_creation_input_tokens": cache_creation,
                    "cache_read_input_tokens": cache_read,
                }
            yield ProviderResponse(
                content=accumulated_content,
                role="assistant",
                function_calls=final_function_calls if final_function_calls else None,
                metadata={"usage": final_usage_meta} if final_usage_meta else {},
                usage=final_usage,
            )

        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise APIError(f"Anthropic streaming error: {e}", str(e))

    def _append_message(self, message: Any) -> None:
        """Append user/tool messages in Anthropic-compatible format."""
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
            and message[0].get("type") in ("image", "text")
        ):
            self.messages.append({
                "role": "user",
                "content": message,
            })
            return

        if isinstance(message, list) and all(
            isinstance(item, dict) and item.get("type") == "tool_result"
            for item in message
        ):
            self.messages.append({
                "role": "user",
                "content": message
            })
            return

        if isinstance(message, list) and all(
            isinstance(item, dict) and "role" in item
            for item in message
        ):
            self.messages.extend(message)
            return

        self.messages.append(message)

    def format_tool_results(self, tool_results: List[Dict[str, Any]]) -> Any:
        """Format tool results for Anthropic tool-use follow-up turns."""
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_result["id"],
                    "content": tool_result["result"],
                }
                for tool_result in tool_results
            ],
        }

    def _parse_response(self, response: Any) -> ProviderResponse:
        """
        Parse Anthropic response into normalized ProviderResponse

        Args:
            response: Anthropic response object

        Returns:
            Normalized ProviderResponse
        """
        try:
            content = ""
            thinking_content = ""
            function_calls = None

            if hasattr(response, 'content'):
                for block in response.content:
                    block_type = getattr(block, 'type', '')
                    if block_type == "text":
                        content += getattr(block, 'text', '')
                    elif block_type == "thinking":
                        thinking_content += getattr(block, 'thinking', '')
                    elif block_type == "tool_use":
                        if function_calls is None:
                            function_calls = []
                        function_calls.append(FunctionCall(
                            id=block.id, name=block.name,
                            arguments=block.input if hasattr(block, 'input') else {},
                        ))

            # Build assistant message for history
            assistant_message = {"role": "assistant", "content": []}

            if content:
                assistant_message["content"].append({
                    "type": "text",
                    "text": content
                })

            if hasattr(response, 'content'):
                for block in response.content:
                    if hasattr(block, 'type') and block.type == "tool_use":
                        assistant_message["content"].append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input if hasattr(block, 'input') else {}
                        })

            # Add to history
            self.messages.append(assistant_message)

            usage_obj = None
            usage_meta = None
            if hasattr(response, 'usage'):
                cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
                cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
                usage_obj = UsageMetadata(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cache_creation_input_tokens=cache_creation,
                    cache_read_input_tokens=cache_read,
                )
                usage_meta = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "cache_creation_input_tokens": cache_creation,
                    "cache_read_input_tokens": cache_read,
                }
            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=response.stop_reason if hasattr(response, 'stop_reason') else None,
                function_calls=function_calls,
                raw_response=response,
                metadata={
                    "model": response.model if hasattr(response, 'model') else None,
                    "usage": usage_meta,
                },
                thinking_content=thinking_content or None,
                usage=usage_obj,
            )

        except Exception as e:
            logger.error(f"Error parsing Anthropic response: {e}")
            return ProviderResponse(
                content="",
                role="assistant",
                raw_response=response,
                metadata={"parse_error": str(e)}
            )

    async def clear_history(self):
        """Clear Anthropic conversation history"""
        self.messages = []
        logger.info("Anthropic history cleared")

    def get_history(self) -> List[Dict[str, Any]]:
        """Get Anthropic conversation history"""
        return self.messages.copy()

    def set_history(self, messages: List[Dict[str, Any]]) -> None:
        self.messages = list(messages)

    def get_capabilities(self) -> ProviderCapabilities:
        """Get Anthropic capabilities"""
        # Claude 3.5 Sonnet has 200K context, Claude 3 Opus has 200K
        max_tokens = 200000

        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_system_instructions=True,
            max_context_tokens=max_tokens,
            supports_vision=True,
            supports_json_mode=False,
            supports_code_interpreter=False,
            supports_thinking=self._supports_extended_thinking(),
        )
