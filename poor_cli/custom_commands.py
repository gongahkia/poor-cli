"""
Repo-local and user-global prompt command wrappers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class CustomCommand:
    name: str
    path: Path
    description: str
    scope: str
    template: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "description": self.description,
            "scope": self.scope,
        }


def default_command_search_paths(repo_root: Path) -> List[Path]:
    return [
        repo_root / ".poor-cli" / "commands",
        Path.home() / ".poor-cli" / "commands",
    ]


class CustomCommandRegistry:
    def __init__(
        self,
        repo_root: Optional[Path] = None,
        search_paths: Optional[Sequence[str]] = None,
    ) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        configured = [Path(path).expanduser() for path in (search_paths or []) if str(path).strip()]
        self.search_paths = _dedupe_paths(
            list(default_command_search_paths(self.repo_root)) + configured
        )

    def list_commands(self) -> List[CustomCommand]:
        discovered: List[CustomCommand] = []
        seen: set[str] = set()
        for root in self.search_paths:
            if not root.is_dir():
                continue
            for command_file in sorted(root.glob("*.md")):
                name = command_file.stem
                if name in seen:
                    continue
                seen.add(name)
                body = command_file.read_text(encoding="utf-8")
                discovered.append(
                    CustomCommand(
                        name=name,
                        path=command_file,
                        description=_command_description(body),
                        scope="repo"
                        if root == self.repo_root / ".poor-cli" / "commands"
                        else "user",
                        template=body,
                    )
                )
        return discovered

    def get_command(self, name: str) -> Optional[CustomCommand]:
        normalized = str(name).strip()
        if not normalized:
            return None
        for command in self.list_commands():
            if command.name == normalized:
                return command
        return None

    def render_prompt(self, name: str, args_text: str = "") -> str:
        command = self.get_command(name)
        if command is None:
            raise FileNotFoundError(f"Unknown command wrapper: {name}")
        return (
            command.template.replace("{{args}}", args_text.strip())
            .replace("{{cwd}}", str(Path.cwd().resolve()))
            .replace("{{repo_root}}", str(self.repo_root))
        )


def _command_description(body: str) -> str:
    lines = [line.strip() for line in body.splitlines()]
    for line in lines:
        if not line or line.startswith("#"):
            continue
        return line
    return "No description provided."


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    deduped: List[Path] = []
    for raw_path in paths:
        resolved = raw_path.expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(resolved)
    return deduped
