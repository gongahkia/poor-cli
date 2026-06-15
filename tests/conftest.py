from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    import pytest

    if os.environ.get("POOR_CLI_LIVE_PROVIDER_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="live provider tests require POOR_CLI_LIVE_PROVIDER_TESTS=1")
    for item in items:
        if "live_provider" in item.keywords:
            item.add_marker(skip)
