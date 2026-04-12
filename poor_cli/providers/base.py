"""
Base provider interface for AI models
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from pydantic import BaseModel, Field, field_validator

from .capability import ProviderCapability


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
    supports_structured_output: bool = False  # grammar-constrained / json_schema output


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

    capabilities: frozenset[ProviderCapability] = frozenset()

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
        self.economy_max_output_tokens: int = 0 # set by economy mode; 0 = no cap
        self.economy_max_thinking_tokens: int = 0 # set by thinking budget optimizer; 0 = use provider default
        self.prompt_prefix: str = ""

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
    async def send_message(self, message: Any, **kwargs) -> ProviderResponse:
        """Send a message and get normalized response

        Args:
            message: Message to send (str or provider-specific content)
            **kwargs: Provider-specific options (e.g. structured_output=StructuredOutputConfig)

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

    def update_system_instruction(self, instruction: str) -> None:
        """Update system instruction mid-session for dynamic context refresh.
        Subclasses may override for provider-specific behavior."""
        self.system_instruction = instruction

    def update_prompt_prefix(self, prefix: str) -> None:
        """Update stable per-request prefix injected before conversation history."""
        self.prompt_prefix = prefix or ""

    def get_prompt_prefix(self) -> str:
        """Return stable per-request prefix text."""
        return self.prompt_prefix or ""

    def switch_model(self, model_name: str) -> None:
        """Switch to a different model (e.g. for economy downshift).
        Subclasses may override for provider-specific re-init."""
        self.model_name = model_name

    def get_provider_name(self) -> str:
        """Get the provider name

        Returns:
            Provider name (lowercase)
        """
        return self.__class__.__name__.replace("Provider", "").lower()

    def preferred_edit_format(self) -> str:
        """Return provider-tuned preferred edit format."""
        from ..edit_formats import suggest_format_for_model

        return suggest_format_for_model(
            self.model_name,
            provider_name=self.get_provider_name(),
        )

    def count_tokens(self, text: str, *, model: Optional[str] = None) -> int:
        """Count tokens for this provider via the shared TokenCounter.

        Subclasses with a native SDK counter should register a CountBackend
        with the global TokenCounter at construction time rather than
        overriding this method.
        """
        from ..token_counter import get_token_counter

        return get_token_counter().count(
            text,
            provider=self.get_provider_name(),
            model=model or self.model_name,
        ).count
