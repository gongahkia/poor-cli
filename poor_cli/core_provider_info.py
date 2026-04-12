"""Provider-info and routing helpers, split out of core.py.

Implemented as a mixin on PoorCLICore. All methods access PoorCLICore
internals (self.provider, self.config, self._config_manager, etc.) via
duck typing — valid only as part of the full core class.
"""

from __future__ import annotations

from typing import Any, Dict

from .providers.capability import ProviderCapability, capability_names
from .provider_probe import (
    normalize_routing_mode,
    probe_providers,
    resolve_routing_mode,
)


class ProviderInfoMixin:
    """get_provider_info / readiness / routing-mode helpers."""

    def get_provider_info(self) -> Dict[str, Any]:
        """Return info about the current provider."""
        if not self._initialized or not self.provider or not self.config:
            # soft-init: minimal stub so lualine/status polling doesn't spam errors
            return {"name": "unconfigured", "model": "", "initialized": False, "capabilities": {}}

        capabilities: Dict[str, Any] = {}
        declared = getattr(self.provider, "capabilities", frozenset())
        if declared:
            runtime_caps = self.provider.get_capabilities()
            capabilities = {
                "flags": capability_names(declared),
                "streaming": ProviderCapability.STREAMING in declared,
                "function_calling": ProviderCapability.TOOL_CALLING in declared,
                "vision": ProviderCapability.VISION in declared,
                "json_mode": ProviderCapability.JSON_MODE in declared,
                "extended_thinking": ProviderCapability.EXTENDED_THINKING in declared,
                "prompt_caching_prefix": ProviderCapability.PROMPT_CACHING_PREFIX in declared,
                "prompt_caching_block": ProviderCapability.PROMPT_CACHING_BLOCK in declared,
                "grounding": ProviderCapability.GROUNDING in declared,
                "latent_communication": ProviderCapability.LATENT_COMMUNICATION in declared,
                "max_context_tokens": runtime_caps.max_context_tokens,
            }

        return {
            "name": self.config.model.provider,
            "model": self.config.model.model_name,
            "routingMode": self.get_routing_mode(),
            "capabilities": capabilities,
            "supported_clients": list(self.SUPPORTED_CLIENTS),
        }

    def get_provider_readiness(self) -> Dict[str, Dict[str, Any]]:
        if not self._config_manager or not self.config:
            return {}
        return probe_providers(self._config_manager, self.config)

    def get_routing_mode(self) -> str:
        if not self.config:
            return normalize_routing_mode(self._resolved_routing_mode)
        provider_status = self.get_provider_readiness()
        self._resolved_routing_mode = resolve_routing_mode(
            getattr(self.config.model, "routing_mode", "manual"),
            provider_status,
        )
        return self._resolved_routing_mode

    def set_routing_mode(self, routing_mode: str) -> str:
        normalized = normalize_routing_mode(routing_mode)
        if self.config is not None:
            self.config.model.routing_mode = normalized
        self._resolved_routing_mode = normalized
        return normalized
