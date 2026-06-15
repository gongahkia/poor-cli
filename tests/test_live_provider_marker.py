from __future__ import annotations

import os

import pytest


@pytest.mark.live_provider
def test_live_provider_marker_requires_explicit_env() -> None:
    assert os.environ["POOR_CLI_LIVE_PROVIDER_TESTS"] == "1"
