"""
OpenAI Provider Implementation

Supports GPT-4, GPT-4-Turbo, GPT-3.5-Turbo and other OpenAI models.
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncIterator

try:
    from openai import AsyncOpenAI
    from openai import APIError as OpenAIAPIError, RateLimitError, Timeout, APIConnectionError as OpenAIConnectionError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None

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


class OpenAIProvider(BaseProvider):
    """OpenAI API provider implementation"""

    def __init__(self, api_key: str, model_name: str = "gpt-4-turbo",
                 max_retries: int = 3, retry_delay: float = 1.0, timeout: float = 60.0):
        """
        Initialize OpenAI provider

        Args:
            api_key: OpenAI API key
            model_name: Model to use (gpt-4-turbo, gpt-4, gpt-3.5-turbo, etc.)
            max_retries: Max retries for failed requests
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds
        """
        if not OPENAI_AVAILABLE:
            raise ConfigurationError(
                "OpenAI provider requires 'openai' package. "
                "Install with: pip install openai"
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
                self.messages.append({
                    "role": "system",
                    "content": system_instruction
                })

            logger.info(f"OpenAI model {self.model_name} initialized")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize OpenAI: {e}")

    async def send_message(self, message: Any) -> ProviderResponse:
        """Send message to OpenAI"""
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
                }

                if self.tools:
                    request_params["tools"] = self.tools
                    request_params["tool_choice"] = "auto"

                # Send request
                response = await self.client.chat.completions.create(**request_params)

                # Parse response
                return self._parse_response(response)

            except RateLimitError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Rate limit, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APIRateLimitError("OpenAI rate limit exceeded", str(e))

            except Timeout as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Timeout, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APITimeoutError("OpenAI request timeout", str(e))

            except OpenAIConnectionError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Connection error, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APIConnectionError("OpenAI connection error", str(e))

            except Exception as e:
                logger.error(f"OpenAI error: {e}")
                raise APIError(f"OpenAI API error: {e}", str(e))

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        """Stream response from OpenAI"""
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
                "stream": True
            }

            if self.tools:
                request_params["tools"] = self.tools
                request_params["tool_choice"] = "auto"

            # Stream response
            accumulated_content = ""
            accumulated_tool_calls = {}

            async for chunk in await self.client.chat.completions.create(**request_params):
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
                assistant_message["tool_calls"] = tool_calls_list

            self.messages.append(assistant_message)

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise APIError(f"OpenAI streaming error: {e}", str(e))

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

            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=choice.finish_reason,
                function_calls=function_calls,
                raw_response=response,
                metadata={
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    } if hasattr(response, 'usage') else None
                }
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
        # Keep system message if exists
        if self.system_instruction:
            self.messages = [{
                "role": "system",
                "content": self.system_instruction
            }]
        else:
            self.messages = []

        logger.info("OpenAI history cleared")

    def get_history(self) -> List[Dict[str, Any]]:
        """Get OpenAI conversation history"""
        return self.messages.copy()

    def get_capabilities(self) -> ProviderCapabilities:
        """Get OpenAI capabilities"""
        # Determine capabilities based on model
        supports_vision = "vision" in self.model_name.lower() or "gpt-4" in self.model_name
        max_tokens = 128000 if "turbo" in self.model_name or "gpt-4" in self.model_name else 8192

        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_system_instructions=True,
            max_context_tokens=max_tokens,
            supports_vision=supports_vision,
            supports_json_mode=True,
            supports_code_interpreter=False
        )
