from __future__ import annotations

import os

OFFLINE_ENV = "POOR_CLI_OFFLINE"


class OfflineModeError(RuntimeError):
    pass


def enable_offline() -> None:
    os.environ[OFFLINE_ENV] = "1"


def offline_enabled() -> bool:
    return os.environ.get(OFFLINE_ENV, "").lower() in {"1", "true", "yes", "on"}


def require_online(operation: str) -> None:
    if offline_enabled():
        raise OfflineModeError(f"offline mode blocks network call: {operation}")
