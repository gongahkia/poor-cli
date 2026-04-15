"""turn pin overlay — per-repo persistent store of soft/hard pins on turn ids.

the underlying turn storage is append-only; to let users toggle pin state at
runtime without rewriting turn files we keep a side-file at
``<repo>/.poor-cli/turn_pins.json`` mapping ``turn_id -> "soft" | "hard"``.

``history_pruning.prune_history`` consults the overlay (via kwarg) and merges
the state into ``message.metadata.pinned`` before scoring, so pruning
respects runtime toggles.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Optional

VALID_STATES = ("soft", "hard")


class TurnPinOverlay:
    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
        self.path = self.repo_root / ".poor-cli" / "turn_pins.json"
        self._pins: Dict[str, str] = {}
        self._loaded = False

    def load(self) -> "TurnPinOverlay":
        if not self.path.exists():
            self._pins = {}
            self._loaded = True
            return self
        try:
            raw = json.loads(self.path.read_text())
            if isinstance(raw, dict):
                self._pins = {
                    str(k): str(v) for k, v in raw.items()
                    if isinstance(v, str) and v in VALID_STATES
                }
            else:
                self._pins = {}
        except (OSError, json.JSONDecodeError):
            self._pins = {}
        self._loaded = True
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._pins, indent=2, sort_keys=True))
        tmp.replace(self.path)

    def get(self, turn_id: str) -> Optional[str]:
        if not self._loaded:
            self.load()
        return self._pins.get(str(turn_id))

    def set(self, turn_id: str, state: Optional[str]) -> None:
        if not self._loaded:
            self.load()
        key = str(turn_id)
        if state is None or state == "":
            self._pins.pop(key, None)
        elif state in VALID_STATES:
            self._pins[key] = state
        else:
            raise ValueError(f"invalid pin state: {state!r}; expected one of {VALID_STATES} or None")
        self.save()

    def all(self) -> Dict[str, str]:
        if not self._loaded:
            self.load()
        return dict(self._pins)

    def clear(self) -> None:
        self._pins = {}
        self._loaded = True
        self.save()
