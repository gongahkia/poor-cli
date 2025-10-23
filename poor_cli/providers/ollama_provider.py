"""
Ollama Provider Implementation

Supports local model execution with Ollama (Llama 3, CodeLlama, Mistral, etc.)
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncIterator

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

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


class OllamaProvider(BaseProvider):
    """Ollama local model provider implementation"""

    def __init__(self, api_key: str = "", model_name: str = "llama3",
                 max_retries: int = 3, retry_delay: float = 1.0, timeout: float = 120.0,
                 base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama provider

        Args:
            api_key: Not used for Ollama (local), kept for compatibility
            model_name: Model to use (llama3, codellama, mistral, etc.)
            max_retries: Max retries for failed requests
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds (longer for local models)
            base_url: Ollama server URL (default: http://localhost:11434)
        """
        if not AIOHTTP_AVAILABLE:
            raise ConfigurationError(
                "Ollama provider requires 'aiohttp' package. "
                "Install with: pip install aiohttp"
            )

        super().__init__(api_key, model_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.base_url = base_url.rstrip('/')

        self.messages = []  # Conversation history
        self.tools = None
        self.system_instruction = None

        logger.info(f"Ollama provider initialized (server: {self.base_url})")

    async def initialize(self, tools: Optional[List[Dict[str, Any]]] = None,
                        system_instruction: Optional[str] = None):
        """Initialize with tools and system instructions"""
        try:
            # Translate tools to Ollama format (OpenAI-compatible)
            if tools:
                self.tools = ToolTranslator.translate(tools, ProviderType.OLLAMA)
                logger.info(f"Translated {len(self.tools)} tools to Ollama format")

            # Store system instruction
            if system_instruction:
                self.system_instruction = system_instruction
                self.messages.append({
                    "role": "system",
                    "content": system_instruction
                })

            # Check if Ollama is running
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = [m['name'] for m in data.get('models', [])]
                            logger.info(f"Ollama server available. Models: {models}")

                            # Check if requested model is available
                            if self.model_name not in models:
                                logger.warning(f"Model {self.model_name} not found. Available: {models}")
            except Exception as e:
                logger.warning(f"Could not connect to Ollama server: {e}")
                raise ConfigurationError(
                    f"Ollama server not available at {self.base_url}. "
                    f"Make sure Ollama is running (ollama serve)"
                )

            logger.info(f"Ollama model {self.model_name} initialized")

        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            raise ConfigurationError(f"Failed to initialize Ollama: {e}")

    async def send_message(self, message: Any) -> ProviderResponse:
        """Send message to Ollama"""
        # Handle string message vs pre-formatted content
        if isinstance(message, str):
            self.messages.append({
                "role": "user",
                "content": message
            })
        else:
            self.messages.append(message)

        for attempt in range(self.max_retries):
            try:
                # Prepare request
                request_data = {
                    "model": self.model_name,
                    "messages": self.messages,
                    "stream": False
                }

                # Add tools if available (note: tool support varies by model)
                if self.tools:
                    request_data["tools"] = self.tools

                # Send request
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/api/chat",
                        json=request_data,
                        timeout=aiohttp.ClientTimeout(total=self.timeout)
                    ) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            raise APIError(f"Ollama error {resp.status}: {error_text}", error_text)

                        response_data = await resp.json()

                # Parse response
                return self._parse_response(response_data)

            except asyncio.TimeoutError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Timeout, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APITimeoutError("Ollama request timeout", str(e))

            except aiohttp.ClientError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Connection error, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                raise APIConnectionError("Ollama connection error", str(e))

            except Exception as e:
                logger.error(f"Ollama error: {e}")
                raise APIError(f"Ollama API error: {e}", str(e))

    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        """Stream response from Ollama"""
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
            request_data = {
                "model": self.model_name,
                "messages": self.messages,
                "stream": True
            }

            if self.tools:
                request_data["tools"] = self.tools

            # Stream response
            accumulated_content = ""

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=request_data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise APIError(f"Ollama error {resp.status}: {error_text}", error_text)

                    # Read streaming response line by line
                    async for line in resp.content:
                        if line:
                            try:
                                chunk_data = json.loads(line.decode('utf-8'))

                                # Extract message content
                                if 'message' in chunk_data:
                                    msg = chunk_data['message']
                                    if 'content' in msg and msg['content']:
                                        accumulated_content += msg['content']

                                        yield ProviderResponse(
                                            content=msg['content'],
                                            role="assistant",
                                            raw_response=chunk_data,
                                            metadata={"is_chunk": True}
                                        )

                                # Check if done
                                if chunk_data.get('done', False):
                                    break

                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse Ollama chunk: {line}")
                                continue

            # Add final message to history
            if accumulated_content:
                self.messages.append({
                    "role": "assistant",
                    "content": accumulated_content
                })

        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise APIError(f"Ollama streaming error: {e}", str(e))

    def _parse_response(self, response_data: Dict[str, Any]) -> ProviderResponse:
        """
        Parse Ollama response into normalized ProviderResponse

        Args:
            response_data: Ollama response dictionary

        Returns:
            Normalized ProviderResponse
        """
        try:
            # Extract message
            message = response_data.get('message', {})
            content = message.get('content', '')

            # Extract tool calls if present
            function_calls = None
            if 'tool_calls' in message and message['tool_calls']:
                function_calls = []
                for tc in message['tool_calls']:
                    function_calls.append(FunctionCall(
                        id=tc.get('id', f"ollama_{tc['function']['name']}"),
                        name=tc['function']['name'],
                        arguments=json.loads(tc['function']['arguments']) if isinstance(tc['function']['arguments'], str) else tc['function']['arguments']
                    ))

            # Add to history
            self.messages.append({
                "role": "assistant",
                "content": content
            })

            return ProviderResponse(
                content=content,
                role="assistant",
                finish_reason=response_data.get('done_reason'),
                function_calls=function_calls,
                raw_response=response_data,
                metadata={
                    "model": response_data.get('model'),
                    "total_duration": response_data.get('total_duration'),
                    "load_duration": response_data.get('load_duration'),
                    "prompt_eval_count": response_data.get('prompt_eval_count'),
                    "eval_count": response_data.get('eval_count')
                }
            )

        except Exception as e:
            logger.error(f"Error parsing Ollama response: {e}")
            return ProviderResponse(
                content="",
                role="assistant",
                raw_response=response_data,
                metadata={"parse_error": str(e)}
            )

    async def clear_history(self):
        """Clear Ollama conversation history"""
        # Keep system message if exists
        if self.system_instruction:
            self.messages = [{
                "role": "system",
                "content": self.system_instruction
            }]
        else:
            self.messages = []

        logger.info("Ollama history cleared")

    def get_history(self) -> List[Dict[str, Any]]:
        """Get Ollama conversation history"""
        return self.messages.copy()

    def get_capabilities(self) -> ProviderCapabilities:
        """Get Ollama capabilities"""
        # Capabilities vary by model
        # Most Ollama models support long context (32K-128K)
        supports_tools = "llama3" in self.model_name.lower() or "mistral" in self.model_name.lower()

        return ProviderCapabilities(
            supports_streaming=True,
            supports_function_calling=supports_tools,  # Only some models
            supports_system_instructions=True,
            max_context_tokens=32000,  # Varies by model
            supports_vision=False,  # Most models don't support vision yet
            supports_json_mode=True,
            supports_code_interpreter=False
        )
