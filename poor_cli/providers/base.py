"""
Base provider interface for AI models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncIterator


@dataclass
class ProviderCapabilities:
    """Capabilities supported by a provider"""
    supports_streaming: bool = False
    supports_function_calling: bool = False
    supports_system_instructions: bool = False
    max_context_tokens: int = 4096
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_code_interpreter: bool = False


@dataclass
class FunctionCall:
    """Represents a function call from the AI"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ProviderResponse:
    """Normalized response format across all providers"""
    content: str
    role: str = "assistant"
    finish_reason: Optional[str] = None
    function_calls: Optional[List[FunctionCall]] = None
    raw_response: Optional[Any] = None  # Original provider response
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """Base class for all AI model providers"""

    def __init__(self, api_key: str, model_name: str, **kwargs):
        """Initialize provider

        Args:
            api_key: API key for the provider
            model_name: Model name to use
            **kwargs: Additional provider-specific configuration
        """
        self.api_key = api_key
        self.model_name = model_name
        self.config = kwargs

    @abstractmethod
    async def initialize(self, tools: Optional[List[Dict[str, Any]]] = None,
                        system_instruction: Optional[str] = None):
        """Initialize the provider with tools and system instructions

        Args:
            tools: List of tool definitions in canonical format
            system_instruction: System instruction for the model
        """
        pass

    @abstractmethod
    async def send_message(self, message: Any) -> ProviderResponse:
        """Send a message and get normalized response

        Args:
            message: Message to send (str or provider-specific content)

        Returns:
            Normalized ProviderResponse object
        """
        pass

    @abstractmethod
    async def send_message_stream(self, message: Any) -> AsyncIterator[ProviderResponse]:
        """Send a message and stream response

        Args:
            message: Message to send

        Yields:
            ProviderResponse chunks
        """
        pass

    @abstractmethod
    async def clear_history(self):
        """Clear conversation history"""
        pass

    @abstractmethod
    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history

        Returns:
            List of message dictionaries
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Get provider capabilities

        Returns:
            Provider capabilities
        """
        pass

    def translate_tools(self, tools: List[Dict[str, Any]]) -> Any:
        """Convert canonical tool format to provider-specific format

        Override this method in subclasses if tool format conversion is needed.
        Default implementation returns tools as-is.

        Args:
            tools: Tools in canonical format

        Returns:
            Tools in provider-specific format
        """
        return tools

    def get_provider_name(self) -> str:
        """Get the provider name

        Returns:
            Provider name (lowercase)
        """
        return self.__class__.__name__.replace("Provider", "").lower()
