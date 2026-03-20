"""
Base provider interface for AI models
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from pydantic import BaseModel, Field, field_validator


class ProviderCapabilities(BaseModel):
    """Capabilities supported by a provider"""
    model_config = {"frozen": False}
    supports_streaming: bool = False
    supports_function_calling: bool = False
    supports_system_instructions: bool = False
    max_context_tokens: int = Field(default=4096, ge=1)
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_code_interpreter: bool = False
    supports_thinking: bool = False  # extended thinking / reasoning


class FunctionCall(BaseModel):
    """Represents a function call from the AI"""
    model_config = {"frozen": False}
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)


class UsageMetadata(BaseModel):
    """Token usage metadata from provider responses"""
    model_config = {"frozen": False}
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)  # openai compat alias
    completion_tokens: int = Field(default=0, ge=0)  # openai compat alias
    prompt_eval_count: int = Field(default=0, ge=0)  # ollama
    eval_count: int = Field(default=0, ge=0)  # ollama


class ProviderResponse(BaseModel):
    """Normalized response format across all providers"""
    model_config = {"frozen": False, "arbitrary_types_allowed": True}
    content: str = ""
    role: str = "assistant"
    finish_reason: Optional[str] = None
    function_calls: Optional[List[FunctionCall]] = None
    raw_response: Optional[Any] = None  # original provider response
    metadata: Dict[str, Any] = Field(default_factory=dict)
    thinking_content: Optional[str] = None  # model reasoning/thinking text
    usage: Optional[UsageMetadata] = None  # structured token usage

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("assistant", "user", "system", "tool", "model"):
            raise ValueError(f"invalid role: {v}")
        return v


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

    def set_history(self, messages: List[Dict[str, Any]]) -> None:
        """Replace conversation history with the given messages.
        Override in subclasses for provider-specific behavior."""
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

    def format_tool_results(self, tool_results: List[Dict[str, Any]]) -> Any:
        """Format executed tool results into provider-native follow-up input.

        Args:
            tool_results: Executed tool result dictionaries with id/name/result.

        Returns:
            Provider-specific payload accepted by `send_message`.
        """
        return "\n".join(
            f"{tool_result['name']}: {tool_result['result']}"
            for tool_result in tool_results
        )

    def get_provider_name(self) -> str:
        """Get the provider name

        Returns:
            Provider name (lowercase)
        """
        return self.__class__.__name__.replace("Provider", "").lower()
