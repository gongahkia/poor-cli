"""provider factory lazy-loading regression tests."""

from __future__ import annotations

from poor_cli.providers.provider_factory import ProviderFactory


def _reset_factory_state() -> None:
    ProviderFactory._providers = {}
    ProviderFactory._initialized = False
    ProviderFactory._load_errors = {}


def test_get_provider_info_avoids_materializing_provider_classes() -> None:
    _reset_factory_state()
    info = ProviderFactory.get_provider_info("openai")
    assert isinstance(info, dict)
    assert info.get("class") == "OpenAIProvider"
    assert ProviderFactory._providers == {}


def test_is_provider_available_avoids_materializing_provider_classes() -> None:
    _reset_factory_state()
    available = ProviderFactory.is_provider_available("openai")
    assert isinstance(available, bool)
    assert ProviderFactory._providers == {}


def test_list_providers_materializes_registry_on_demand() -> None:
    _reset_factory_state()
    providers = ProviderFactory.list_providers()
    assert "openai" in providers
    assert "anthropic" in providers
    assert ProviderFactory._providers
