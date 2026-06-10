from __future__ import annotations

from dataclasses import dataclass
from typing import List

from poor_cli.command_manifest import load_command_manifest
from poor_cli.custom_commands import CustomCommandRegistry


@dataclass(frozen=True)
class Suggestion:
    command: str
    description: str
    category: str


def all_suggestions() -> List[Suggestion]:
    manifest = load_command_manifest()
    items = [
        Suggestion(command.command, command.description, command.category)
        for command in manifest.commands
    ]
    try:
        for command in CustomCommandRegistry().list_commands():
            items.append(Suggestion(f"/{command.name}", command.description.strip(), "custom"))
    except Exception:
        pass
    return items


def fuzzy_match(query: str, items: List[Suggestion], limit: int = 8) -> List[Suggestion]:
    q = query.lower().lstrip("/")
    if not q:
        return [item for item in items if item.command.startswith("/")][:limit]

    scored: list[tuple[int, int, Suggestion]] = []
    for item in items:
        name = item.command.lstrip("/").lower()
        if name.startswith(q):
            scored.append((0, len(item.command), item))
        elif q in name:
            scored.append((1, len(item.command), item))
        elif _is_subsequence(q, name):
            scored.append((2, len(item.command), item))
    scored.sort(key=lambda entry: (entry[0], entry[1], entry[2].command))
    return [item for _, _, item in scored[:limit]]


def _is_subsequence(query: str, value: str) -> bool:
    cursor = 0
    for char in value:
        if cursor < len(query) and query[cursor] == char:
            cursor += 1
    return cursor == len(query)
