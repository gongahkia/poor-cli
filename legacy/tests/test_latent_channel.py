from types import SimpleNamespace

import pytest

from poor_cli.latent_channel import LatentChannel
from poor_cli.providers.capability import ProviderCapability


class LatentProvider:
    capabilities = frozenset({ProviderCapability.LATENT_COMMUNICATION})

    async def run_latent_pipeline(self, prompt: str, max_new_tokens: int = 512):
        return f"latent:{prompt}:{max_new_tokens}", SimpleNamespace(input_tokens=1, output_tokens=2)


def _config(enabled: bool):
    return SimpleNamespace(
        research=SimpleNamespace(
            latent_communication=SimpleNamespace(enabled=enabled)
        )
    )


def test_latent_channel_requires_config_flag():
    assert not LatentChannel(LatentProvider(), _config(False)).available()
    assert LatentChannel(LatentProvider(), _config(True)).available()


@pytest.mark.asyncio
async def test_latent_channel_runs_provider_pipeline():
    text, bench = await LatentChannel(LatentProvider(), _config(True)).run("task", max_new_tokens=7)
    assert text == "latent:task:7"
    assert bench.input_tokens == 1
    assert bench.output_tokens == 2
