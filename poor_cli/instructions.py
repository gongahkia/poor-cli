"""
Instruction stack loading for poor-cli.

This module builds a deterministic per-request instruction stack from:
- repo-root instruction files
- path-local instruction files for referenced files
- repo-local memory
- active focus state
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

INSTRUCTION_FILE_NAMES: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")


@dataclass
class InstructionSource:
    """Single instruction source loaded into the merged stack."""

    kind: str
    label: str
    content: str
    path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "path": self.path,
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass
class InstructionSnapshot:
    """Resolved instruction stack for a single request."""

    repo_root: str
    sources: List[InstructionSource] = field(default_factory=list)

    def render_prompt_prefix(self) -> str:
        """Render a compact instruction block for the active request."""
        if not self.sources:
            return ""

        sections = ["## Active Instruction Stack"]
        for source in self.sources:
            title = source.label
            if source.path:
                title = f"{title} ({source.path})"
            sections.append(f"### {title}\n{source.content}")
        return "\n\n".join(sections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repoRoot": self.repo_root,
            "sourceCount": len(self.sources),
            "sources": [source.to_dict() for source in self.sources],
            "renderedPromptPrefix": self.render_prompt_prefix(),
        }


class InstructionManager:
    """Load deterministic instruction sources for the current repository."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()

    def build_snapshot(
        self,
        referenced_files: Optional[Sequence[str]] = None,
        *,
        plan_mode_enabled: bool = False,
    ) -> InstructionSnapshot:
        sources: List[InstructionSource] = []
        sources.extend(self._load_runtime_policy(plan_mode_enabled))
        sources.extend(self._load_repo_root_instructions())
        sources.extend(self._load_path_local_instructions(referenced_files or []))
        memory = self._load_memory()
        if memory is not None:
            sources.append(memory)
        focus = self._load_focus()
        if focus is not None:
            sources.append(focus)
        return InstructionSnapshot(repo_root=str(self.repo_root), sources=sources)

    def _load_runtime_policy(self, plan_mode_enabled: bool) -> List[InstructionSource]:
        if not plan_mode_enabled:
            return []
        return [
            InstructionSource(
                kind="runtime_policy",
                label="Plan Mode",
                content=(
                    "Plan mode is enabled for this session. Present a concise numbered plan "
                    "before taking action on complex requests, then keep execution scoped. "
                    "Mutating tools still require preview and approval."
                ),
                metadata={"planMode": True},
            )
        ]

    def _load_repo_root_instructions(self) -> List[InstructionSource]:
        sources: List[InstructionSource] = []
        for file_name in INSTRUCTION_FILE_NAMES:
            path = self.repo_root / file_name
            content = self._read_text(path)
            if not content:
                continue
            sources.append(
                InstructionSource(
                    kind="repo_root",
                    label=f"Repo Root {file_name}",
                    content=content,
                    path=self._relative_or_absolute(path),
                )
            )
        return sources

    def _load_path_local_instructions(self, referenced_files: Sequence[str]) -> List[InstructionSource]:
        directories = self._referenced_directories(referenced_files)
        ordered_instruction_paths: List[Path] = []
        seen: set[Path] = set()

        for directory in directories:
            for candidate_dir in self._ancestor_dirs_between_root(directory):
                for file_name in INSTRUCTION_FILE_NAMES:
                    path = candidate_dir / file_name
                    if path in seen or not path.is_file():
                        continue
                    seen.add(path)
                    ordered_instruction_paths.append(path)

        sources: List[InstructionSource] = []
        for path in ordered_instruction_paths:
            content = self._read_text(path)
            if not content:
                continue
            sources.append(
                InstructionSource(
                    kind="path_local",
                    label=f"Path Local {path.name}",
                    content=content,
                    path=self._relative_or_absolute(path),
                )
            )
        return sources

    def _referenced_directories(self, referenced_files: Sequence[str]) -> List[Path]:
        directories: List[Path] = []
        seen: set[Path] = set()
        for raw_path in referenced_files:
            if not raw_path:
                continue
            candidate = Path(str(raw_path)).expanduser()
            if not candidate.is_absolute():
                candidate = (self.repo_root / candidate).resolve()
            else:
                candidate = candidate.resolve()
            directory = candidate if candidate.is_dir() else candidate.parent
            try:
                directory.relative_to(self.repo_root)
            except ValueError:
                continue
            if directory == self.repo_root or directory in seen:
                continue
            seen.add(directory)
            directories.append(directory)
        directories.sort(key=lambda path: str(path))
        return directories

    def _ancestor_dirs_between_root(self, directory: Path) -> Iterable[Path]:
        current = directory.resolve()
        if current == self.repo_root:
            return []

        chain: List[Path] = []
        while current != self.repo_root and self.repo_root in current.parents:
            chain.append(current)
            current = current.parent
        chain.reverse()
        return chain

    def _load_memory(self) -> Optional[InstructionSource]:
        path = self.repo_root / ".poor-cli" / "memory.md"
        content = self._read_text(path)
        if not content:
            return None
        return InstructionSource(
            kind="memory",
            label="Repo Memory",
            content=content,
            path=self._relative_or_absolute(path),
        )

    def _load_focus(self) -> Optional[InstructionSource]:
        path = self.repo_root / ".poor-cli" / "focus.json"
        if not path.is_file():
            return None

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        goal = str(raw.get("goal", "")).strip()
        constraints = str(raw.get("constraints", "")).strip()
        definition_of_done = str(raw.get("definition_of_done", "")).strip()
        started_at = str(raw.get("started_at", "")).strip()
        completed = bool(raw.get("completed", False))

        lines = []
        if goal:
            lines.append(f"Goal: {goal}")
        if constraints:
            lines.append(f"Constraints: {constraints}")
        if definition_of_done:
            lines.append(f"Definition of done: {definition_of_done}")
        if started_at:
            lines.append(f"Started at: {started_at}")
        lines.append(f"Completed: {'yes' if completed else 'no'}")

        if not lines:
            return None

        return InstructionSource(
            kind="focus",
            label="Active Focus",
            content="\n".join(lines),
            path=self._relative_or_absolute(path),
            metadata={"completed": completed},
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _relative_or_absolute(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.repo_root))
        except ValueError:
            return str(path.resolve())
