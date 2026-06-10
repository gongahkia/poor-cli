"""Provider CLI info fast-path tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_provider_info_uses_fast_path_without_api_key() -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    proc = subprocess.run(
        [sys.executable, "-m", "poor_cli", "provider", "info", "--json"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout)
    assert payload.get("initialized") is False
    assert isinstance(payload.get("name"), str)
    assert isinstance(payload.get("model"), str)
