# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.server.registry import register


class ProvidersHandlersMixin:
    async def handle_switch_provider(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Switch AI provider.

        Params:
            provider: Provider name
            model: Optional model name

        Returns:
            success: Whether the switch succeeded
            provider: New provider info
        """
        self._ensure_initialized()

        provider = params.get("provider", "")
        model = params.get("model")

        # validate API key availability before switch (from provider_lifecycle)
        if provider and provider not in KEYLESS_LOCAL_PROVIDER_NAMES:
            config_manager, config = self._ensure_config_loaded()
            api_key = config_manager.get_api_key(provider)
            if not api_key:
                pls = type("_Stub", (), {"_providers_with_keys": lambda self: [p for p in config.model.providers if p in KEYLESS_LOCAL_PROVIDER_NAMES or config_manager.get_api_key(p)]})()
                available = pls._providers_with_keys()
                provider_cfg = config.model.providers.get(provider)
                env_var = provider_cfg.api_key_env_var if provider_cfg else "API key"
                return {"success": False, "error": f"No API key for {provider} (set {env_var})", "availableProviders": available}

        await self.core.switch_provider(provider, model)
        provider_info = self.core.get_provider_info()

        # push providerChanged so lualine / status UIs update without polling
        async def _emit_provider_changed() -> None:
            try:
                await self.write_message_stdio(JsonRpcMessage(
                    method="poor-cli/providerChanged",
                    params={"providerInfo": provider_info},
                ))
            except Exception as exc:
                logger.debug("emit providerChanged notification failed: %s", exc)
        asyncio.create_task(_emit_provider_changed())

        return {"success": True, "provider": provider_info}

    async def handle_get_provider_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get current provider info.

        Returns:
            Provider info dict
        """
        self._ensure_initialized()
        return self.core.get_provider_info()

    async def handle_list_providers(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List all available providers with their models.

        Returns:
            Dictionary of provider name -> {available, models, ...}
        """
        from ...providers.provider_factory import ProviderFactory

        config_manager, config = self._ensure_config_loaded()
        result: Dict[str, Any] = {}
        seen_provider_keys: set[str] = set()
        ollama_models: List[str] = []
        ollama_base_url = self._ollama_base_url()
        ollama_ready = self._is_ollama_reachable(ollama_base_url)
        if ollama_ready:
            ollama_models = self._list_ollama_models(ollama_base_url)
        local_openai_ready: Dict[str, bool] = {}
        for local_name in ("vllm", "llama_server", "sglang", "hf_tgi", "lmstudio"):
            provider_cfg = config.model.providers.get(local_name)
            if provider_cfg and provider_cfg.base_url:
                local_openai_ready[local_name] = self._is_openai_compatible_local_reachable(provider_cfg.base_url)

        for name, cls in ProviderFactory.list_providers().items():
            info = ProviderFactory.get_provider_info(name) or {}
            provider_key = self._normalize_provider_name(name)
            if provider_key in seen_provider_keys:
                continue
            seen_provider_keys.add(provider_key)
            provider_cfg = config.model.providers.get(provider_key)
            dependency_available = bool(info.get("available", True))
            # Provide default model suggestions per provider
            model_suggestions: Dict[str, list] = {
                "gemini": common_models_for_provider("gemini"),
                "openai": common_models_for_provider("openai"),
                "anthropic": common_models_for_provider("anthropic"),
                "claude": common_models_for_provider("anthropic"),
                "ollama": ollama_models if ollama_models else common_models_for_provider("ollama"),
                "hf_local": common_models_for_provider("hf_local"),
                "vllm": common_models_for_provider("vllm"),
                "llama_server": common_models_for_provider("llama_server"),
                "sglang": common_models_for_provider("sglang"),
                "hf_tgi": common_models_for_provider("hf_tgi"),
                "lmstudio": common_models_for_provider("lmstudio"),
            }
            if provider_key == "ollama":
                ready = ollama_ready
                status_label = (
                    "service up"
                    if ready
                    else f"service unavailable at {ollama_base_url}"
                )
            elif provider_key == "hf_local":
                ready = dependency_available
                status_label = "local dependencies available" if ready else "provider dependency unavailable"
            elif provider_key in local_openai_ready:
                ready = bool(local_openai_ready.get(provider_key))
                base_url = provider_cfg.base_url if provider_cfg else ""
                status_label = "service up" if ready else f"service unavailable at {base_url}"
            else:
                api_key = config_manager.get_api_key(provider_key) if provider_cfg else None
                ready = bool(api_key)
                env_var = provider_cfg.api_key_env_var if provider_cfg else "API key"
                status_label = (
                    "API key configured" if ready else f"missing {env_var}"
                )
            if not dependency_available:
                ready = False
                status_label = "provider dependency unavailable"
            models = model_suggestions.get(name, [])
            tier_info: Dict[str, Any] = {}
            for model_name in models:
                mt = get_model_tier(provider_key, model_name)
                if mt:
                    tier_info[model_name] = {"tier": mt.tier, "cost1kIn": mt.cost_1k_in, "cost1kOut": mt.cost_1k_out, "speedRank": mt.speed_rank, "contextWindow": mt.context_window}
            result[name] = {
                "available": dependency_available,
                "ready": ready,
                "statusLabel": status_label,
                "models": models,
                "modelTiers": tier_info,
                "capabilities": info.get("capabilities", []),
            }
        return result

    def _normalize_provider_name(self, provider_name: str) -> str:
        provider = provider_name.strip().lower()
        if provider == "claude":
            return "anthropic"
        return provider

    def _mask_api_key(self, raw_key: Optional[str]) -> str:
        if not raw_key:
            return "(not set)"
        if len(raw_key) <= 8:
            return "*" * len(raw_key)
        return f"{raw_key[:4]}…{raw_key[-4:]}"

    def _ensure_config_loaded(self) -> Tuple[ConfigManager, Config]:
        """Load config metadata needed for API key/status operations before full init."""
        if self.core._config_manager is None:
            self.core._config_manager = ConfigManager(self.core._config_path)
        if self.core.config is None:
            self.core.config = self.core._config_manager.load()
        return self.core._config_manager, self.core.config

    async def handle_set_api_key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store/update a provider API key for this session and secure local storage.

        Params:
            provider: Provider name (gemini, openai, anthropic, claude)
            apiKey: Raw API key value
            persist: Optional bool (default true) to persist in secure key store
            reloadActiveProvider: Optional bool (default true) to reinitialize current provider
        """
        config_manager, config = self._ensure_config_loaded()

        provider = self._normalize_provider_name(str(params.get("provider", "")))
        if not provider:
            raise InvalidParamsError("Missing provider")

        api_key = str(params.get("apiKey", "")).strip()
        if not api_key:
            raise InvalidParamsError("Missing apiKey")

        if provider == "ollama":
            raise InvalidParamsError("Ollama does not require an API key")
        if provider in KEYLESS_LOCAL_PROVIDER_NAMES:
            raise InvalidParamsError(f"{provider} does not require an API key")

        provider_config = config.model.providers.get(provider)
        if provider_config is None:
            raise InvalidParamsError(f"Unknown provider: {provider}")

        persist = bool(params.get("persist", True))
        reload_active_provider = bool(params.get("reloadActiveProvider", True))

        env_var = provider_config.api_key_env_var
        os.environ[env_var] = api_key
        config.api_keys[provider] = api_key
        config_manager.config.api_keys[provider] = api_key

        stored_securely = False
        if persist:
            from ..credentials import get_credential_store

            stored_securely = get_credential_store().set(provider, api_key, store="keyring") == "keyring"

        active_provider_reloaded = False
        if (
            self.initialized
            and reload_active_provider
            and config.model.provider == provider
        ):
            # if server came up in soft-init (no key at boot), now complete full init
            if getattr(self, "_needs_provider_init", False):
                pending = getattr(self, "_pending_init_params", {}) or {}
                await self.core.initialize(
                    provider_name=pending.get("provider") or provider,
                    model_name=pending.get("model") or config.model.model_name,
                    api_key=api_key,
                )
                self._needs_provider_init = False
                self._pending_init_params = {}
                active_provider_reloaded = True
            else:
                await self.core.switch_provider(
                    provider,
                    config.model.model_name,
                )
                active_provider_reloaded = True

        return {
            "success": True,
            "provider": provider,
            "envVar": env_var,
            "persisted": stored_securely,
            "activeProviderReloaded": active_provider_reloaded,
            "maskedKey": self._mask_api_key(api_key),
        }

    async def handle_get_api_key_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return non-secret API key configuration status per provider.

        Params:
            provider: Optional provider filter.
        """
        _, config = self._ensure_config_loaded()

        requested_provider = str(params.get("provider", "")).strip()
        normalized_provider = self._normalize_provider_name(requested_provider)

        providers: List[str]
        if normalized_provider:
            if normalized_provider not in config.model.providers:
                raise InvalidParamsError(f"Unknown provider: {requested_provider}")
            providers = [normalized_provider]
        else:
            providers = sorted(config.model.providers.keys())

        from ..credentials import get_credential_store

        credential_store = get_credential_store()

        active_provider = self._normalize_provider_name(config.model.provider)
        status: Dict[str, Dict[str, Any]] = {}
        for provider in providers:
            provider_cfg = config.model.providers[provider]
            env_var = provider_cfg.api_key_env_var
            info = config_manager.get_api_key_info(provider)

            key_value = info.get("key")
            source = str(info.get("source") or "none")
            keyring_key = credential_store.get(provider, env_var="", config_keys={})
            configured = key_value is not None
            if provider in KEYLESS_LOCAL_PROVIDER_NAMES:
                configured = True
                source = "local"

            status[provider] = {
                "configured": configured,
                "source": source,
                "envVar": env_var,
                "active": provider == active_provider,
                "persisted": bool(keyring_key),
                "masked": self._mask_api_key(key_value),
            }

        return {"providers": status, "keyring": credential_store.status()}

    async def handle_test_api_key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an API key by making a minimal API call (zero tokens)."""
        provider = self._normalize_provider_name(str(params.get("provider", "")))
        if not provider:
            raise InvalidParamsError("Missing provider")
        api_key = str(params.get("apiKey", "")).strip()
        if provider == "ollama":
            base_url = self._ollama_base_url()
            reachable = self._is_ollama_reachable(base_url)
            return {"valid": reachable, "error": None if reachable else f"Ollama not reachable at {base_url}"}
        if provider == "hf_local":
            from ...providers.provider_factory import ProviderFactory
            return {
                "valid": ProviderFactory.is_provider_available("hf_local"),
                "error": None,
            }
        if provider in {"vllm", "llama_server", "sglang", "hf_tgi", "lmstudio"}:
            _, config = self._ensure_config_loaded()
            provider_cfg = config.model.providers.get(provider)
            base_url = provider_cfg.base_url if provider_cfg else ""
            reachable = self._is_openai_compatible_local_reachable(base_url)
            return {"valid": reachable, "error": None if reachable else f"{provider} not reachable at {base_url}"}
        if not api_key:
            raise InvalidParamsError("Missing apiKey")
        try:
            valid, error_msg = await self._probe_api_key(provider, api_key)
            return {"valid": valid, "error": error_msg}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def _probe_api_key(self, provider: str, api_key: str) -> Tuple[bool, Optional[str]]:
        """Hit a lightweight model-list endpoint to verify an API key."""
        import urllib.error
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            req = Request(url, method="GET")
        elif provider == "openai":
            req = Request("https://api.openai.com/v1/models", method="GET")
            req.add_header("Authorization", f"Bearer {api_key}")
        elif provider == "anthropic":
            req = Request("https://api.anthropic.com/v1/models", method="GET")
            req.add_header("x-api-key", api_key)
            req.add_header("anthropic-version", "2023-06-01")
        elif provider == "openrouter":
            req = Request("https://openrouter.ai/api/v1/models", method="GET")
            req.add_header("Authorization", f"Bearer {api_key}")
        else:
            return False, f"No validation endpoint for provider: {provider}"
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: urlopen(req, timeout=30))
            return (True, None) if response.status == 200 else (False, f"HTTP {response.status}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Invalid API key (401 Unauthorized)"
            if e.code == 403:
                return False, "API key forbidden (403)"
            return False, f"HTTP error {e.code}: {e.reason}"
        except Exception as e:
            return False, str(e)

    async def handle_list_ollama_models(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Discover models available on the local Ollama server."""
        self._ensure_initialized()
        try:
            from ...providers.ollama_provider import OllamaProvider
            base_url = str(params.get("baseUrl", "http://localhost:11434")).strip()
            models = await OllamaProvider.discover_models(base_url)
            return {"models": models, "count": len(models)}
        except Exception as e:
            return {"models": [], "count": 0, "error": str(e)}

    def _is_openai_compatible_local_reachable(self, base_url: str) -> bool:
        parsed = urlparse(str(base_url or "").strip())
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return self._is_tcp_endpoint_reachable(host, port)

@register('listProviders')
async def _rpc_3(ctx, params):
    return await ctx.handle_list_providers(params)

@register('switchProvider')
async def _rpc_5(ctx, params):
    return await ctx.handle_switch_provider(params)

@register('setApiKey')
async def _rpc_10(ctx, params):
    return await ctx.handle_set_api_key(params)

@register('getApiKeyStatus')
async def _rpc_11(ctx, params):
    return await ctx.handle_get_api_key_status(params)

@register('poor-cli/switchProvider')
async def _rpc_22(ctx, params):
    return await ctx.handle_switch_provider(params)

@register('poor-cli/getProviderInfo')
async def _rpc_23(ctx, params):
    return await ctx.handle_get_provider_info(params)

@register('poor-cli/setApiKey')
async def _rpc_45(ctx, params):
    return await ctx.handle_set_api_key(params)

@register('poor-cli/getApiKeyStatus')
async def _rpc_46(ctx, params):
    return await ctx.handle_get_api_key_status(params)

@register('poor-cli/testApiKey')
async def _rpc_47(ctx, params):
    return await ctx.handle_test_api_key(params)

@register('poor-cli/listProviders')
async def _rpc_48(ctx, params):
    return await ctx.handle_list_providers(params)

@register('poor-cli/listOllamaModels')
async def _rpc_110(ctx, params):
    return await ctx.handle_list_ollama_models(params)
