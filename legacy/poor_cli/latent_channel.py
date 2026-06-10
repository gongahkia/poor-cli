"""Latent communication channel for providers that expose model internals."""

from __future__ import annotations

from typing import Any

from .providers.capability import ProviderCapability, provider_has_capability


class LatentChannel:
    """Small adapter over provider-native latent pipeline support."""

    def __init__(self, provider: Any, config: Any = None):
        self.provider = provider
        self.config = config

    @staticmethod
    def enabled(config: Any) -> bool:
        research = getattr(config, "research", None)
        latent = getattr(research, "latent_communication", None)
        return bool(getattr(latent, "enabled", False))

    def available(self) -> bool:
        return (
            self.enabled(self.config)
            and provider_has_capability(self.provider, ProviderCapability.LATENT_COMMUNICATION)
            and callable(getattr(self.provider, "run_latent_pipeline", None))
        )

    async def run(self, prompt: str, max_new_tokens: int = 512) -> tuple[str, Any]:
        if not self.available():
            raise RuntimeError("latent channel unavailable")
        return await self.provider.run_latent_pipeline(prompt, max_new_tokens=max_new_tokens)
