"""
Anthropic (Claude) Provider Implementation

Supports Claude 3.5 Sonnet, Claude 3 Opus, and other Anthropic models.
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

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, FunctionCall
from .tool_translator import ToolTranslator, ProviderType
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

    def __init__(self, api_key: str, model_name: str = "claude-3-5-sonnet-20241022",
                 max_retries: int = 3, retry_delay: float = 1.0, timeout: float = 60.0):
        """
        Initialize Anthropic provider

        Args:
            api_key: Anthropic API key
            model_name: Model to use (claude-3-5-sonnet-20241022, claude-3-opus-20240229, etc.)
            max_retries: Max retries for failed requests
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds
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

    async def send_message(self, message: Any) -> ProviderResponse:
        """Send message to Anthropic"""
        # Handle string message vs pre-formatted content
        if isinstance(message, str):
            self.messages.append({
                "role": "user",
                "content": message
            })
        else:
            # Assume it's already formatted (for tool results)
            self.messages.append(message)

        for attempt in range(self.max_retries):
            try:
                # Prepare request
                request_params = {
                    "model": self.model_name,
                    "messages": self.messages,
                    "max_tokens": 4096,  # Anthropic requires max_tokens
                }

                if self.system_instruction:
                    request_params["system"] = self.system_instruction

                if self.tools:
                    request_params["tools"] = self.tools

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
        # Handle string message
        if isinstance(message, str):
            self.messages.append({
                "role": "user",
                "content": message
            })
        else:
            self.messages.append(message)

        try:
            # Prepare request
            request_params = {
                "model": self.model_name,
                "messages": self.messages,
                "max_tokens": 4096,
                "stream": True
            }

            if self.system_instruction:
                request_params["system"] = self.system_instruction

            if self.tools:
                request_params["tools"] = self.tools

            # Stream response
            accumulated_content = ""
            accumulated_tool_uses = []

            async with self.client.messages.stream(**request_params) as stream:
                async for event in stream:
                    # Handle different event types
                    if hasattr(event, 'type'):
                        if event.type == "content_block_delta":
                            if hasattr(event, 'delta'):
                                delta = event.delta

                                # Text content
                                if hasattr(delta, 'type') and delta.type == "text_delta":
                                    if hasattr(delta, 'text'):
                                        accumulated_content += delta.text
                                        yield ProviderResponse(
                                            content=delta.text,
                                            role="assistant",
                                            raw_response=event,
                                            metadata={"is_chunk": True}
                                        )

                                # Tool use (Anthropic calls it tool_use)
                                elif hasattr(delta, 'type') and delta.type == "input_json_delta":
                                    # Tool input is being streamed
                                    pass

                        elif event.type == "content_block_start":
                            # Track tool use starts
                            if hasattr(event, 'content_block'):
                                block = event.content_block
                                if hasattr(block, 'type') and block.type == "tool_use":
                                    accumulated_tool_uses.append({
                                        "id": block.id,
                                        "name": block.name,
                                        "input": {}
                                    })

                        elif event.type == "content_block_stop":
                            # Content block finished
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

            # Add tool uses from final message
            if hasattr(final_message, 'content'):
                for block in final_message.content:
                    if hasattr(block, 'type') and block.type == "tool_use":
                        assistant_message["content"].append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })

            self.messages.append(assistant_message)

        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise APIError(f"Anthropic streaming error: {e}", str(e))

    def _parse_response(self, response: Any) -> ProviderResponse:
        """
        Parse Anthropic response into normalized ProviderResponse

        Args:
            response: Anthropic response object

        Returns:
            Normalized ProviderResponse
        """
        try:
            # Extract content and tool uses
            content = ""
            function_calls = None

            if hasattr(response, 'content'):
                for block in response.content:
                    # Text content
                    if hasattr(block, 'type') and block.type == "text":
                        if hasattr(block, 'text'):
                            content += block.text

                    # Tool use (Anthropic's function calling)
                    elif hasattr(block, 'type') and block.type == "tool_use":
                        if function_calls is None:
                            function_calls = []

                        function_calls.append(FunctionCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if hasattr(block, 'input') else {}
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

            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=response.stop_reason if hasattr(response, 'stop_reason') else None,
                function_calls=function_calls,
                raw_response=response,
                metadata={
                    "model": response.model if hasattr(response, 'model') else None,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    } if hasattr(response, 'usage') else None
                }
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

    def get_capabilities(self) -> ProviderCapabilities:
        """Get Anthropic capabilities"""
        # Claude 3.5 Sonnet has 200K context, Claude 3 Opus has 200K
        max_tokens = 200000

        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_system_instructions=True,
            max_context_tokens=max_tokens,
            supports_vision=True,  # Claude 3 supports vision
            supports_json_mode=False,
            supports_code_interpreter=False
        )
