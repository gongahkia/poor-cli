"""Shared command manifest for CLI help, completion, and docs generation."""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class CommandSpec:
    command: str
    description: str
    recommended: bool
    category: str


@dataclass(frozen=True)
class CommandManifest:
    notes: List[str]
    commands: List[CommandSpec]


def manifest_path() -> Path:
    return Path(__file__).with_name("command_manifest.json")


def readme_path() -> Path:
    return manifest_path().resolve().parent.parent / "README.md"


def commands_doc_path() -> Path:
    return manifest_path().resolve().parent.parent / "docs" / "COMMANDS.md"


def load_command_manifest() -> CommandManifest:
    payload = json.loads(manifest_path().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Command manifest must be a JSON object.")

    raw_notes = payload.get("notes", [])
    raw_commands = payload.get("commands", [])
    if not isinstance(raw_notes, list) or not all(isinstance(note, str) for note in raw_notes):
        raise ValueError("Command manifest notes must be a list of strings.")
    if not isinstance(raw_commands, list):
        raise ValueError("Command manifest commands must be a list.")

    commands: List[CommandSpec] = []
    seen = set()
    for index, raw_command in enumerate(raw_commands):
        if not isinstance(raw_command, dict):
            raise ValueError(f"Command entry {index} must be an object.")
        command = str(raw_command.get("command", "")).strip()
        description = str(raw_command.get("description", "")).strip()
        category = str(raw_command.get("category", "")).strip()
        recommended = bool(raw_command.get("recommended", False))
        if not command.startswith("/"):
            raise ValueError(f"Command entry {index} must start with '/'.")
        if not description:
            raise ValueError(f"Command entry {command} is missing a description.")
        if not category:
            raise ValueError(f"Command entry {command} is missing a category.")
        if command in seen:
            raise ValueError(f"Duplicate command in manifest: {command}")
        seen.add(command)
        commands.append(
            CommandSpec(
                command=command,
                description=description,
                recommended=recommended,
                category=category,
            )
        )
    return CommandManifest(notes=list(raw_notes), commands=commands)


def _group_by_category(commands: Iterable[CommandSpec]) -> OrderedDict[str, List[CommandSpec]]:
    grouped: OrderedDict[str, List[CommandSpec]] = OrderedDict()
    for command in commands:
        grouped.setdefault(command.category, []).append(command)
    return grouped


def render_commands_markdown(*, heading: str = "## Available Commands") -> str:
    manifest = load_command_manifest()
    lines = [heading, ""]
    for note in manifest.notes:
        lines.append(note)
    lines.append("")
    for category, commands in _group_by_category(manifest.commands).items():
        lines.append(f"**{category}:**")
        for command in commands:
            lines.append(f"- `{command.command}` - {command.description}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_command_reference_markdown() -> str:
    manifest = load_command_manifest()
    grouped = _group_by_category(manifest.commands)
    lines = [
        "# Slash Command Reference",
        "",
        f"poor-cli ships **{len(manifest.commands)} slash commands** across {len(grouped)} categories.",
        "",
        "## Categories",
        "",
    ]
    for category, commands in grouped.items():
        slug = category.lower().replace("&", "").replace(" ", "-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        lines.append(f"- [{category}](#{slug}) ({len(commands)} commands)")
    lines.append("")
    for category, commands in grouped.items():
        lines.extend([f"## {category}", "", "| Command | Description |", "|---|---|"])
        for command in commands:
            label = f"`{command.command}` ⭐" if command.recommended else f"`{command.command}`"
            description = command.description.replace("|", "\\|")
            lines.append(f"| {label} | {description} |")
        lines.append("")
    lines.extend([
        "## Conventions",
        "",
        "- ⭐ = recommended starting point for new users.",
        "- Type `/` in chat to trigger the slash command dispatcher.",
        "- Custom slash commands defined via AutomationRule (`type: slash`) appear here only after manifest regeneration; see `docs/AUTOMATIONS.md`.",
        "",
        "## See also",
        "",
        "- [PROVIDERS.md](./PROVIDERS.md) — `/switch`, `/provider`, `/api-key`",
        "- [ECONOMY.md](./ECONOMY.md) — `/broke`, `/my-treat`, `/economy`, `/savings`",
        "- [SANDBOX.md](./SANDBOX.md) — `/sandbox`, `/permission-mode`, `/trust`, `/policy`",
        "- [AUTOMATIONS.md](./AUTOMATIONS.md) — `/automation`, `/workflow`, `/skills`",
        "- [AUTO_COMMIT.md](./AUTO_COMMIT.md) — `/commit`",
    ])
    return "\n".join(lines).rstrip() + "\n"


def sync_command_docs(path: Path | None = None) -> bool:
    target = (path or commands_doc_path()).resolve()
    original = target.read_text(encoding="utf-8")
    rendered = render_command_reference_markdown()
    if rendered == original:
        return False
    target.write_text(rendered, encoding="utf-8")
    return True


def sync_readme(path: Path | None = None) -> bool:
    """Backward-compatible alias; command docs now live in docs/COMMANDS.md."""
    return sync_command_docs(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poor_cli.command_manifest")
    parser.add_argument("--write-docs", action="store_true", help="Rewrite docs/COMMANDS.md")
    parser.add_argument("--write-readme", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help="Fail if docs/COMMANDS.md is stale")
    args = parser.parse_args(argv)

    if args.write_docs or args.write_readme:
        changed = sync_command_docs()
        print("COMMANDS.md updated" if changed else "COMMANDS.md already current")
        return 0

    if args.check:
        target = commands_doc_path()
        rendered = render_command_reference_markdown().rstrip("\n")
        current = target.read_text(encoding="utf-8")
        if current.rstrip("\n") != rendered:
            raise SystemExit("docs/COMMANDS.md is out of date. Run `python -m poor_cli.command_manifest --write-docs`.")
        print("docs/COMMANDS.md is current")
        return 0

    print(render_commands_markdown(heading="**Available Commands**"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
