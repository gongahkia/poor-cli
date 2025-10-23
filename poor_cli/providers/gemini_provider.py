"""
Gemini AI Provider Implementation
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncIterator
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from .base import BaseProvider, ProviderCapabilities, ProviderResponse, FunctionCall
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
    """Gemini AI provider implementation"""

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp",
                 max_retries: int = 3, retry_delay: float = 1.0, timeout: float = 60.0):
        """Initialize Gemini provider

        Args:
            api_key: Gemini API key
            model_name: Model to use
            max_retries: Maximum retries for failed requests
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds (not used by Gemini SDK directly)
        """
        super().__init__(api_key, model_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.model = None
        self.chat = None

        # Configure Gemini
        try:
            genai.configure(api_key=self.api_key)
            logger.info("Gemini provider initialized")
        except Exception as e:
            raise ConfigurationError(f"Failed to configure Gemini: {e}")

    async def initialize(self, tools: Optional[List[Dict[str, Any]]] = None,
                        system_instruction: Optional[str] = None):
        """Initialize Gemini model with tools and instructions"""
        try:
            def _init():
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    tools=tools if tools else None,
                    system_instruction=system_instruction,
                )
                chat = model.start_chat(enable_automatic_function_calling=False)
                return model, chat

            self.model, self.chat = await asyncio.to_thread(_init)
            logger.info(f"Gemini model {self.model_name} initialized")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize Gemini model: {e}")

    async def send_message(self, message: Any) -> ProviderResponse:
        """Send message to Gemini

        Args:
            message: Message to send (str or Content object)

        Returns:
            Normalized ProviderResponse object
        """
        for attempt in range(self.max_retries):
            try:
                response = await asyncio.to_thread(self.chat.send_message, message)

                # Parse Gemini response into ProviderResponse
                return self._parse_response(response)

            except google_exceptions.ResourceExhausted as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise APIRateLimitError("Rate limit exceeded", str(e))

            except google_exceptions.DeadlineExceeded as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise APITimeoutError("Request timed out", str(e))

            except Exception as e:
                raise APIError(f"Failed to send message: {e}", str(e))

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        """Stream response from Gemini

        Args:
            message: Message to send

        Yields:
            ProviderResponse chunks
        """
        try:
            def _stream():
                return self.chat.send_message(message, stream=True)

            stream_gen = await asyncio.to_thread(_stream)

            for chunk in stream_gen:
                yield self._parse_response(chunk, is_chunk=True)
                await asyncio.sleep(0)

        except google_exceptions.ResourceExhausted as e:
            raise APIRateLimitError("Rate limit exceeded", str(e))
        except Exception as e:
            raise APIError(f"Streaming failed: {e}", str(e))

    def _parse_response(self, response: Any, is_chunk: bool = False) -> ProviderResponse:
        """
        Parse Gemini response into normalized ProviderResponse

        Args:
            response: Gemini response object
            is_chunk: Whether this is a streaming chunk

        Returns:
            Normalized ProviderResponse
        """
        try:
            # Extract content and function calls
            content = ""
            function_calls = []
            finish_reason = None

            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]

                # Get finish reason
                if hasattr(candidate, 'finish_reason'):
                    finish_reason = str(candidate.finish_reason)

                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        # Extract text
                        if hasattr(part, 'text') and part.text:
                            content += part.text

                        # Extract function calls
                        if hasattr(part, 'function_call') and part.function_call:
                            fc = part.function_call
                            function_calls.append(FunctionCall(
                                id=f"gemini_{fc.name}",  # Gemini doesn't provide IDs
                                name=fc.name,
                                arguments=dict(fc.args) if fc.args else {}
                            ))

            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=finish_reason,
                function_calls=function_calls if function_calls else None,
                raw_response=response,
                metadata={"is_chunk": is_chunk}
            )

        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            # Return minimal response on error
            return ProviderResponse(
                content="",
                role="assistant",
                raw_response=response,
                metadata={"parse_error": str(e)}
            )

    async def clear_history(self):
        """Clear Gemini conversation history"""
        try:
            def _start_new():
                return self.model.start_chat(enable_automatic_function_calling=False)

            self.chat = await asyncio.to_thread(_start_new)
            logger.info("Gemini history cleared")
        except Exception as e:
            raise APIError(f"Failed to clear history: {e}", str(e))

    def get_history(self) -> List[Dict[str, Any]]:
        """Get Gemini conversation history

        Returns:
            List of message dictionaries
        """
        if not self.chat:
            return []

        try:
            history = []
            for message in self.chat.history:
                history.append({
                    "role": message.role,
                    "parts": [part.text if hasattr(part, 'text') else str(part)
                             for part in message.parts]
                })
            return history
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []

    def get_capabilities(self) -> ProviderCapabilities:
        """Get Gemini capabilities

        Returns:
            Gemini capabilities
        """
        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=True,
            supports_system_instructions=True,
            max_context_tokens=1000000,  # Gemini 2.0 has 1M context
            supports_vision=True,
            supports_json_mode=True,
            supports_code_interpreter=False
        )
