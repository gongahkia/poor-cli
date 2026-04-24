"""Persistent voice preferences for poor-cli."""

from __future__ import annotations

import json
from pathlib import Path

from .controller import VoiceSettings


class VoicePreferencesStore:
    def __init__(self, repo_root: str):
        root = Path(repo_root).expanduser().resolve() if repo_root else Path.cwd().resolve()
        self._path = root / ".poor-cli" / "voice.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> VoiceSettings:
        if not self._path.exists():
            return VoiceSettings()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return VoiceSettings()
        if not isinstance(payload, dict):
            return VoiceSettings()
        return VoiceSettings.from_mapping(payload)

    def save(self, settings: VoiceSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(settings.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
