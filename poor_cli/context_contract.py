"""Deterministic cache-friendly prompt prefix blocks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .instructions import InstructionManager, InstructionSnapshot, InstructionSource


@dataclass(frozen=True)
class ContextContractSnapshot:
    repo_map_context: str
    instruction_context: str
    rendered_prompt_prefix: str

    @property
    def system_context(self) -> str:
        return self.repo_map_context

    @property
    def user_context(self) -> str:
        return self.instruction_context

    def to_dict(self) -> dict:
        return {
            "repoMapContext": self.repo_map_context,
            "instructionContext": self.instruction_context,
            "renderedPromptPrefix": self.rendered_prompt_prefix,
        }

    def retention_tiers(self) -> dict:
        return {
            "repoMapContext": "preserve",
            "instructionContext": "preserve",
            "renderedPromptPrefix": "preserve",
        }


class ContextContractManager:
    """Builds memoized static prefix blocks for each model turn."""

    def __init__(
        self,
        repo_root: Path,
        instruction_manager: Optional[InstructionManager] = None,
    ):
        self.repo_root = Path(repo_root).resolve()
        self._instruction_manager = instruction_manager or InstructionManager(self.repo_root)
        self._cache_key: str = ""
        self._cache_value: Optional[ContextContractSnapshot] = None

    def invalidate_cache(self) -> None:
        self._cache_key = ""
        self._cache_value = None

    def build_snapshot(
        self,
        *,
        referenced_files: Optional[Sequence[str]] = None,
        plan_mode_enabled: bool = False,
        repo_summary: str = "",
        instruction_snapshot: Optional[InstructionSnapshot] = None,
    ) -> ContextContractSnapshot:
        resolved_snapshot = instruction_snapshot or self._instruction_manager.build_snapshot(
            list(referenced_files or []),
            plan_mode_enabled=plan_mode_enabled,
            repo_summary=repo_summary,
        )
        ordered_sources = self._ordered_sources(resolved_snapshot.sources)
        key = hashlib.sha256(
            "|".join(
                [
                    str(self.repo_root),
                    hashlib.sha256(
                        "\n".join(
                            f"{source.kind}|{source.label}|{source.path or ''}|{source.content}"
                            for source in ordered_sources
                        ).encode("utf-8", errors="replace")
                    ).hexdigest(),
                ]
            ).encode("utf-8", errors="replace")
        ).hexdigest()
        if key == self._cache_key and self._cache_value is not None:
            return self._cache_value

        repo_sources = [source for source in ordered_sources if source.kind == "repo_graph"]
        instruction_sources = [source for source in ordered_sources if source.kind != "repo_graph"]
        repo_map_context = self._render_sources(repo_sources)
        instruction_context = self._render_sources(instruction_sources)
        rendered_parts = [part for part in (repo_map_context, instruction_context) if part]
        snapshot = ContextContractSnapshot(
            repo_map_context=repo_map_context,
            instruction_context=instruction_context,
            rendered_prompt_prefix="\n\n".join(rendered_parts).strip(),
        )
        self._cache_key = key
        self._cache_value = snapshot
        return snapshot

    @staticmethod
    def _ordered_sources(sources: Sequence[InstructionSource]) -> list[InstructionSource]:
        repo_graph = [source for source in sources if source.kind == "repo_graph"]
        remainder = [source for source in sources if source.kind != "repo_graph"]
        return [*repo_graph, *remainder]

    @staticmethod
    def _render_sources(sources: Sequence[InstructionSource]) -> str:
        if not sources:
            return ""
        sections = ["## Active Instruction Stack"]
        for source in sources:
            title = source.label
            if source.path:
                title = f"{title} ({source.path})"
            sections.append(f"### {title}\n{source.content}")
        return "\n\n".join(sections).strip()
