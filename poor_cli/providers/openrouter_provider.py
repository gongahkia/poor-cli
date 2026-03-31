"""OpenRouter provider — OpenAI-compatible gateway to 200+ models."""

from typing import Optional
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None

from .openai_provider import OpenAIProvider
from ..provider_catalog import default_model_for_provider
from ..exceptions import ConfigurationError, setup_logger

logger = setup_logger(__name__)
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter gateway — routes to any model via OpenAI-compatible API."""

    def __init__(self, api_key: str, model_name: str = "",
                 max_retries: int = 3, retry_delay: float = 1.0, timeout: float = 60.0,
                 base_url: Optional[str] = None):
        if not OPENAI_AVAILABLE:
            raise ConfigurationError(
                "OpenRouter provider requires 'openai' package. "
                "Install with: pip install openai"
            )
        if not model_name:
            try:
                model_name = default_model_for_provider("openrouter")
            except KeyError:
                model_name = "anthropic/claude-sonnet-4-20250514"
        from .base import BaseProvider
        BaseProvider.__init__(self, api_key, model_name)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        try:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=base_url or _OPENROUTER_BASE_URL,
                max_retries=0,
                timeout=timeout,
                default_headers={"HTTP-Referer": "https://github.com/gongahkia/poor-cli", "X-Title": "poor-cli"},
            )
            logger.info("OpenRouter provider initialized (model=%s)", model_name)
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize OpenRouter: {e}")
        self.messages = []
        self.tools = None
        self.system_instruction = None
