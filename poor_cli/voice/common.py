"""Shared helpers for poor-cli voice mode."""

from __future__ import annotations

import os


class VoiceError(RuntimeError):
    """Voice subsystem failure."""


def env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default
