from __future__ import annotations

from typing import Any

from ..config_fast import load_runtime_model_settings


def get_startup_state_payload() -> dict[str, Any]:
    settings = load_runtime_model_settings()
    return {
        "provider": str(settings.get("provider", "openai")),
        "model": str(settings.get("model", "")),
    }
