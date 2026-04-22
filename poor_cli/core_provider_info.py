"""Provider-info and routing helpers, split out of core.py.

Implemented as a mixin on PoorCLICore. All methods access PoorCLICore
internals (self.provider, self.config, self._config_manager, etc.) via
duck typing — valid only as part of the full core class.
"""

from __future__ import annotations

from typing import Any, Dict

from .provider_catalog import KEYLESS_LOCAL_PROVIDER_NAMES
from .providers.capability import ProviderCapability, capability_names
from .providers.provider_factory import ProviderFactory
from .provider_probe import (
    normalize_routing_mode,
    resolve_routing_mode,
)


class ProviderInfoMixin:
    """get_provider_info / readiness / routing-mode helpers."""

    def _seed_provider_readiness_cache(self) -> Dict[str, Dict[str, Any]]:
        if not self.config:
            return {}
        providers = getattr(getattr(self.config, "model", None), "providers", {}) or {}
        seeded: Dict[str, Dict[str, Any]] = {}
        for provider_name in sorted(providers.keys()):
            provider_cfg = providers[provider_name]
            provider_info = ProviderFactory.get_provider_info(provider_name) or {}
            dependency_available = bool(provider_info.get("available", True))
            raw_capabilities = provider_info.get("capabilities") or {}
            if isinstance(raw_capabilities, dict):
                capabilities = dict(raw_capabilities)
            else:
                capabilities = {
                    str(capability): True
                    for capability in raw_capabilities
                }
            env_var = str(getattr(provider_cfg, "api_key_env_var", "") or "")
            key_info = (
                self._config_manager.get_api_key_info(provider_name)
                if self._config_manager is not None
                else {}
            )
            key_value = str(key_info.get("key") or "")
            configured = provider_name in KEYLESS_LOCAL_PROVIDER_NAMES or bool(key_value)
            source = str(
                key_info.get("source")
                or ("local" if provider_name in KEYLESS_LOCAL_PROVIDER_NAMES else "none")
            )
            status_label = "probe pending"
            if not dependency_available:
                status_label = "provider dependency unavailable"
            elif provider_name in KEYLESS_LOCAL_PROVIDER_NAMES:
                status_label = "local provider (probe pending)"
            elif configured:
                status_label = f"configured ({source})"
            elif env_var:
                status_label = f"missing {env_var}"
            seeded[provider_name] = {
                "name": provider_name,
                "available": dependency_available,
                "ready": False,
                "configured": configured,
                "source": source,
                "statusLabel": status_label,
                "defaultModel": str(getattr(provider_cfg, "default_model", "") or ""),
                "models": [],
                "capabilities": capabilities,
                "envVar": env_var,
                "baseUrl": getattr(provider_cfg, "base_url", None),
            }
        self._provider_readiness_cache = {
            name: dict(payload)
            for name, payload in seeded.items()
        }
        return seeded

    def get_provider_info(self) -> Dict[str, Any]:
        """Return info about the current provider."""
        if not self._initialized or not self.config:
            # soft-init: minimal response so status polling does not spam errors
            return {"name": "unconfigured", "model": "", "initialized": False, "capabilities": {}}
        if not self.provider:
            return {
                "name": self.config.model.provider,
                "model": self.config.model.model_name,
                "routingMode": self.get_routing_mode(),
                "initialized": False,
                "capabilities": {},
                "supported_clients": list(self.SUPPORTED_CLIENTS),
            }

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
        if not self.config:
            return {}
        provider_status = dict(getattr(self, "_provider_readiness_cache", {}) or {})
        if not provider_status:
            provider_status = self._seed_provider_readiness_cache()
        schedule_probe = getattr(self, "_schedule_provider_readiness_probe", None)
        if callable(schedule_probe):
            schedule_probe()
        return {
            name: dict(payload)
            for name, payload in provider_status.items()
        }

    def get_routing_mode(self) -> str:
        if not self.config:
            return normalize_routing_mode(self._resolved_routing_mode)
        configured_mode = normalize_routing_mode(
            getattr(self.config.model, "routing_mode", "manual")
        )
        if configured_mode != "manual":
            self._resolved_routing_mode = configured_mode
            return self._resolved_routing_mode
        provider_status = dict(getattr(self, "_provider_readiness_cache", {}) or {})
        if provider_status:
            self._resolved_routing_mode = resolve_routing_mode(
                configured_mode,
                provider_status,
            )
            return self._resolved_routing_mode
        schedule_probe = getattr(self, "_schedule_provider_readiness_probe", None)
        if callable(schedule_probe):
            schedule_probe()
        self._resolved_routing_mode = configured_mode
        return self._resolved_routing_mode

    def set_routing_mode(self, routing_mode: str) -> str:
        normalized = normalize_routing_mode(routing_mode)
        if self.config is not None:
            self.config.model.routing_mode = normalized
        self._resolved_routing_mode = normalized
        return normalized
