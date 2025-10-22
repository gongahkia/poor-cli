"""
Base provider interface for AI models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, AsyncIterator


@dataclass
class ProviderCapabilities:
    """Capabilities supported by a provider"""
    supports_streaming: bool = False
    supports_function_calling: bool = False
    supports_system_instructions: bool = False
    max_context_tokens: int = 4096
    supports_vision: bool = False


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
            tools: List of tool definitions
            system_instruction: System instruction for the model
        """
        pass

    @abstractmethod
    async def send_message(self, message: str) -> Any:
        """Send a message and get response

        Args:
            message: Message to send

        Returns:
            Provider-specific response object
        """
        pass

    @abstractmethod
    async def send_message_stream(self, message: str) -> AsyncIterator[Any]:
        """Send a message and stream response

        Args:
            message: Message to send

        Yields:
            Response chunks
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
