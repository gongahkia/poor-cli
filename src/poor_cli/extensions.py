from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any


class ExtensionLoadError(RuntimeError):
    pass


def load_entry_point_values(group: str) -> list[tuple[str, Any]]:
    loaded: list[tuple[str, Any]] = []
    try:
        selected = entry_points().select(group=group)
    except AttributeError:
        selected = entry_points().get(group, [])
    for entry_point in selected:
        try:
            loaded.append((entry_point.name, entry_point.load()))
        except Exception as exc:
            raise ExtensionLoadError(f"failed to load entry point {entry_point.name} from {group}: {exc}") from exc
    return loaded
