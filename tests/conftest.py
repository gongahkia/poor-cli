from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_repo_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAUS_DISABLE_DOTENV", "1")
