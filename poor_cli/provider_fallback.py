"""
Provider fallback chain logic for poor-cli.

Automatically retries operations against alternate providers when the
active provider returns a rate-limit or 5xx server error.  Integrates
with per-provider circuit breakers to skip providers known to be down.
"""

from typing import Any, Callable, Dict, List, Optional
from .exceptions import (
    setup_logger,
    APIRateLimitError,
    APIError,
    APIConnectionError,
    CircuitOpenError,
    ConfigurationError,
)
from .config import FallbackConfig, ConfigManager
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .providers.base import BaseProvider
from .providers.provider_factory import ProviderFactory

logger = setup_logger(__name__)


class ProviderFallbackManager:
    """Manages provider fallback chains for resilient API execution."""

    def __init__(self, config: FallbackConfig, config_manager: ConfigManager,
                 cb_config: Optional[CircuitBreakerConfig] = None):
        self.config = config
        self.config_manager = config_manager
        self._attempt_index = 0
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._cb_config = cb_config or CircuitBreakerConfig()

    def get_circuit_breaker(self, provider_name: str) -> CircuitBreaker:
        """return (or create) a circuit breaker for *provider_name*."""
        key = provider_name.lower()
        if key not in self._circuit_breakers:
            self._circuit_breakers[key] = CircuitBreaker(key, self._cb_config)
        return self._circuit_breakers[key]

    def record_success(self, provider_name: str) -> None:
        self.get_circuit_breaker(provider_name).record_success()

    def record_failure(self, provider_name: str) -> None:
        self.get_circuit_breaker(provider_name).record_failure()

    async def try_fallback(
        self,
        primary_provider_name: str,
        error: Exception,
        tools: Any = None,
        system_instruction: Any = None,
    ) -> Optional[BaseProvider]:
        """Given a failed primary provider, return an initialized fallback or None."""
        if not self.config.enabled or not self._should_fallback(error):
            return None
        chain = self._get_fallback_chain(primary_provider_name)
        if not chain:
            return None
        for provider_name in chain:
            if self._attempt_index >= self.config.max_fallback_attempts:
                break
            cb = self.get_circuit_breaker(provider_name)
            if not cb.allow_request():
                logger.info("skipping fallback %s (circuit open)", provider_name)
                continue
            self._attempt_index += 1
            try:
                provider = await self.create_fallback_provider(provider_name)
                await provider.initialize(tools=tools or [], system_instruction=system_instruction)
                logger.info("fallback provider ready: %s", provider_name)
                return provider
            except Exception as init_err:
                cb.record_failure()
                logger.warning("fallback provider %s init failed: %s", provider_name, init_err)
        return None

    def reset(self, provider_name: Optional[str] = None) -> None:
        """Reset circuit breaker state for one or all providers."""
        if provider_name:
            key = provider_name.lower()
            if key in self._circuit_breakers:
                self._circuit_breakers[key].reset()
        else:
            for cb in self._circuit_breakers.values():
                cb.reset()
        self._attempt_index = 0

    def _should_fallback(self, error: Exception) -> bool:
        """Return True if the error type warrants trying the next provider."""
        if isinstance(error, CircuitOpenError):
            return True
        if isinstance(error, APIRateLimitError) and self.config.retry_on_rate_limit:
            return True
        if isinstance(error, (APIError, APIConnectionError)) and self.config.retry_on_server_error:
            error_msg = str(error).lower()
            if any(code in error_msg for code in ("500", "502", "503", "504", "server error")):
                return True
            if isinstance(error, APIConnectionError):
                return True
        return False

    def _get_fallback_chain(self, primary: str) -> List[str]:
        """Return ordered list of providers to try after the primary.

        When prefer_cheaper is enabled, sorts by cheapest default model first.
        """
        if not self.config.chain:
            return []
        chain = [p for p in self.config.chain if p.lower() != primary.lower()]
        if getattr(self.config, "prefer_cheaper", False) and chain:
            try:
                from .provider_catalog import get_cheapest_model
                def _cost_key(provider_name: str) -> float:
                    tier = get_cheapest_model(provider_name)
                    if tier:
                        return tier.cost_1k_in + tier.cost_1k_out
                    return 999.0 # unknown providers go last
                chain.sort(key=_cost_key)
            except Exception:
                pass # fallback to original order
        return chain

    async def create_fallback_provider(self, provider_name: str) -> BaseProvider:
        """Create a provider instance for fallback use."""
        api_key = self.config_manager.get_api_key(provider_name)
        if not api_key and provider_name.lower() != "ollama":
            raise ConfigurationError(f"no API key available for fallback provider: {provider_name}")
        provider_config = self.config_manager.get_provider_config(provider_name)
        if not provider_config:
            raise ConfigurationError(f"no configuration found for fallback provider: {provider_name}")
        extra_kwargs: Dict[str, Any] = {}
        if provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url
        provider = ProviderFactory.create(
            provider_name=provider_name,
            api_key=api_key or "",
            model_name=provider_config.default_model,
            **extra_kwargs,
        )
        logger.info("created fallback provider: %s (%s)", provider_name, provider_config.default_model)
        return provider
