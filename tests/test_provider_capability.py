from types import SimpleNamespace

import pytest

from poor_cli.core_provider_info import ProviderInfoMixin
from poor_cli.config import ModelConfig
from poor_cli.exceptions import CapabilityError
from poor_cli.provider_catalog import provider_catalog
from poor_cli.providers.anthropic_provider import AnthropicProvider
from poor_cli.providers.base import ProviderCapabilities
from poor_cli.providers.capability import ProviderCapability
from poor_cli.providers.gemini_provider import GeminiProvider
from poor_cli.providers.hf_local_provider import HFLocalProvider
from poor_cli.providers.hf_tgi_provider import HFTGIProvider
from poor_cli.providers.llama_server_provider import LlamaServerProvider
from poor_cli.providers.lmstudio_provider import LMStudioProvider
from poor_cli.providers.ollama_provider import OllamaProvider
from poor_cli.providers.openai_provider import OpenAIProvider
from poor_cli.providers.openrouter_provider import OpenRouterProvider
from poor_cli.providers.sglang_provider import SGLangProvider
from poor_cli.providers.vllm_provider import VLLMProvider
from poor_cli.thinking_budget import ThinkingBudgetOptimizer
from poor_cli.vision import detect_image_paths_for_provider


def test_anthropic_has_extended_thinking():
    assert ProviderCapability.EXTENDED_THINKING in AnthropicProvider.capabilities


def test_openai_has_streaming():
    assert ProviderCapability.STREAMING in OpenAIProvider.capabilities


def test_ollama_has_no_prompt_caching():
    assert ProviderCapability.PROMPT_CACHING_PREFIX not in OllamaProvider.capabilities
    assert ProviderCapability.PROMPT_CACHING_BLOCK not in OllamaProvider.capabilities


def test_only_hf_local_declares_latent_communication():
    providers = (
        AnthropicProvider,
        GeminiProvider,
        OpenAIProvider,
        OpenRouterProvider,
        OllamaProvider,
        VLLMProvider,
        LlamaServerProvider,
        SGLangProvider,
        HFTGIProvider,
        LMStudioProvider,
    )
    for provider_cls in providers:
        assert ProviderCapability.LATENT_COMMUNICATION not in provider_cls.capabilities
    assert ProviderCapability.LATENT_COMMUNICATION in HFLocalProvider.capabilities


def test_thinking_allocation_refused_without_capability():
    provider = SimpleNamespace(capabilities=OllamaProvider.capabilities)
    with pytest.raises(CapabilityError):
        ThinkingBudgetOptimizer().allocate(provider, 0.5)


def test_vision_refused_without_capability(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    provider = SimpleNamespace(capabilities=OllamaProvider.capabilities)
    with pytest.raises(CapabilityError):
        detect_image_paths_for_provider(f"inspect {image}", provider)


def test_provider_declarations_match_default_runtime_capabilities():
    cases = [
        (AnthropicProvider, "claude-sonnet-4-20250514"),
        (GeminiProvider, "gemini-2.5-flash"),
        (OpenAIProvider, "gpt-5.1"),
        (OpenRouterProvider, "anthropic/claude-sonnet-4-20250514"),
        (OllamaProvider, "llama3.1"),
        (HFLocalProvider, "Qwen/Qwen2.5-3B"),
        (VLLMProvider, "Qwen/Qwen2.5-3B"),
        (LlamaServerProvider, "local-model"),
        (SGLangProvider, "Qwen/Qwen2.5-3B"),
        (HFTGIProvider, "tgi"),
        (LMStudioProvider, "local-model"),
    ]
    for provider_cls, model in cases:
        provider = provider_cls.__new__(provider_cls)
        provider.model_name = model
        caps = provider.get_capabilities()
        declared = provider_cls.capabilities
        assert caps.supports_streaming == (ProviderCapability.STREAMING in declared)
        assert caps.supports_function_calling == (ProviderCapability.TOOL_CALLING in declared)
        assert caps.supports_system_instructions == (ProviderCapability.SYSTEM_INSTRUCTIONS in declared)
        assert caps.supports_json_mode == (ProviderCapability.JSON_MODE in declared)
        assert caps.supports_vision == (ProviderCapability.VISION in declared)
        assert caps.supports_latent_communication == (ProviderCapability.LATENT_COMMUNICATION in declared)


def test_provider_catalog_entries_include_capabilities():
    catalog = provider_catalog()
    assert "extended_thinking" in catalog["anthropic"].capabilities
    assert "streaming" in catalog["openai"].capabilities
    assert "streaming" in catalog["vllm"].capabilities
    assert "latent_communication" not in catalog["vllm"].capabilities


def test_model_config_merges_new_catalog_providers_into_old_configs():
    config = ModelConfig.from_dict({
        "providers": {
            "openai": {
                "name": "openai",
                "api_key_env_var": "OPENAI_API_KEY",
                "default_model": "gpt-5.1",
            }
        }
    })
    assert "vllm" in config.providers
    assert "llama_server" in config.providers
    assert "sglang" in config.providers
    assert "hf_tgi" in config.providers
    assert "lmstudio" in config.providers


def test_provider_info_exposes_capability_flags():
    class Core(ProviderInfoMixin):
        _initialized = True
        SUPPORTED_CLIENTS = ()
        config = SimpleNamespace(
            model=SimpleNamespace(provider="openai", model_name="gpt-5.1")
        )
        provider = SimpleNamespace(
            capabilities=OpenAIProvider.capabilities,
            get_capabilities=lambda: ProviderCapabilities(max_context_tokens=1000000),
        )

        def get_routing_mode(self):
            return "manual"

    info = Core().get_provider_info()
    assert "streaming" in info["capabilities"]["flags"]
    assert info["capabilities"]["json_mode"] is True
    assert info["capabilities"]["max_context_tokens"] == 1000000
