"""
Instruction stack loading for poor-cli.

This module builds a deterministic per-request instruction stack from:
- runtime policy
- hierarchical memory files (managed -> user -> project -> local)
- repo/path-local instruction files (compatibility)
- repo-local memory + focus state
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from .agent_rules import discover_rule_paths, load_rules
from .skills import InstructionSkillContext, SkillLoadPlan, SkillRegistry

INSTRUCTION_FILE_NAMES: tuple[str, ...] = ("AGENTS.md", "POOR.md", "CLAUDE.md", "GEMINI.md")
MAX_INCLUDE_DEPTH = 5
MANAGED_MEMORY_ENV = "POOR_CLI_MANAGED_MEMORY"
DEFAULT_MANAGED_MEMORY = "/etc/poor-cli/CLAUDE.md"
DISABLE_MEMORY_ENV = "CLAUDE_CODE_DISABLE_CLAUDE_MDS"
DISABLE_MEMORY_ENV_ALT = "POOR_CLI_DISABLE_CLAUDE_MDS"
ALLOW_EXTERNAL_INCLUDES_ENV = "POOR_CLI_ALLOW_EXTERNAL_INCLUDES"
EXTERNAL_INCLUDE_ALLOWLIST_ENV = "POOR_CLI_EXTERNAL_INCLUDE_ALLOWLIST"
MAX_MEMORY_CHARACTER_COUNT = 40_000
RULES_DIR = ".claude/rules"
RULES_FILE_NAME = ".claude/CLAUDE.md"
LOCAL_MEMORY_FILE_NAME = "CLAUDE.local.md"
PROJECT_MEMORY_FILE_NAME = "CLAUDE.md"
USER_MEMORY_FILE_NAME = "CLAUDE.md"
_TEXT_INCLUDE_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".toml",
    ".cfg",
    ".ini",
    ".sh",
    ".zsh",
    ".bash",
}


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
    loaded_skills: List[str] = field(default_factory=list)
    system_skills: List[str] = field(default_factory=list)
    prompt_skills: List[str] = field(default_factory=list)
    skill_plan: Dict[str, Any] = field(default_factory=dict)

    def render_prompt_prefix(self) -> str:
        """Render a compact instruction block for the active request."""
        if not self.sources:
            return ""

        sections = ["## Active Instruction Stack"]
        ordered_sources = [
            *[source for source in self.sources if source.kind == "repo_graph"],
            *[source for source in self.sources if source.kind != "repo_graph"],
        ]
        for source in ordered_sources:
            title = source.label
            if source.path:
                title = f"{title} ({source.path})"
            sections.append(f"### {title}\n{source.content}")
        return "\n\n".join(sections)

    def to_dict(self) -> Dict[str, Any]:
        rendered = self.render_prompt_prefix()
        return {
            "repoRoot": self.repo_root,
            "sourceCount": len(self.sources),
            "loadedSkills": list(self.loaded_skills),
            "systemSkills": list(self.system_skills),
            "promptSkills": list(self.prompt_skills),
            "skillPlan": dict(self.skill_plan),
            "instructionChars": len(rendered),
            "instructionTokensEstimate": len(rendered) // 4,
            "sources": [source.to_dict() for source in self.sources],
            "renderedPromptPrefix": rendered,
        }


class InstructionManager:
    """Load deterministic instruction sources for the current repository."""

    _WATCHED_PATHS: tuple[str, ...] = (
        *INSTRUCTION_FILE_NAMES,
        os.path.join(".poor-cli", "memory.md"),
        os.path.join(".poor-cli", "focus.json"),
        PROJECT_MEMORY_FILE_NAME,
        LOCAL_MEMORY_FILE_NAME,
        RULES_FILE_NAME,
    )

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        *,
        skill_search_paths: Optional[Sequence[str]] = None,
    ):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self._skill_search_paths = [str(path) for path in (skill_search_paths or []) if str(path).strip()]
        self._cache_key: Optional[str] = None
        self._cached_snapshot: Optional[InstructionSnapshot] = None

    def invalidate_cache(self) -> None:
        """Force the next build_snapshot call to rebuild from disk."""
        self._cache_key = None
        self._cached_snapshot = None

    def attach_rule_watcher(self, watcher: Any) -> None:
        def _invalidate_on_rule_change(event: Any) -> None:
            paths = getattr(event, "paths", ()) or ()
            if any(Path(str(path)).name in {"AGENTS.md", "CLAUDE.md"} for path in paths):
                self.invalidate_cache()

        watcher.on_change(_invalidate_on_rule_change)

    def _compute_cache_key(
        self,
        plan_mode_enabled: bool,
        repo_summary_hash: str,
        hierarchy_signature: str = "",
    ) -> str:
        parts: list[str] = [
            str(self.repo_root),
            str(plan_mode_enabled),
            repo_summary_hash,
            hierarchy_signature,
        ]
        for rel in self._WATCHED_PATHS:
            path = self.repo_root / rel
            try:
                parts.append(f"{rel}:{os.stat(path).st_mtime_ns}")
            except OSError:
                parts.append(f"{rel}:0")
        parts.append(self._instruction_skill_signature())
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def build_snapshot(
        self,
        referenced_files: Optional[Sequence[str]] = None,
        *,
        plan_mode_enabled: bool = False,
        repo_summary: str = "",
        user_prompt: str = "",
        skill_context: Optional[InstructionSkillContext] = None,
        skill_plan: Optional[SkillLoadPlan] = None,
    ) -> InstructionSnapshot:
        referenced_files = list(referenced_files or [])
        summary_hash = hashlib.sha256(repo_summary.encode()).hexdigest()[:8] if repo_summary else ""
        hierarchy_sig = self._hierarchy_signature(referenced_files)

        use_cache = (
            not referenced_files
            and not user_prompt
            and skill_plan is None
            and skill_context is None
        )
        if use_cache: # only cache when no path-local files requested
            key = self._compute_cache_key(plan_mode_enabled, summary_hash, hierarchy_signature=hierarchy_sig)
            if key == self._cache_key and self._cached_snapshot is not None:
                return self._cached_snapshot

        sources: List[InstructionSource] = []
        sources.extend(self._load_runtime_policy(plan_mode_enabled))
        sources.extend(self._load_hierarchical_memory(referenced_files))

        memory = self._load_memory()
        if memory is not None:
            sources.append(memory)
        focus = self._load_focus()
        if focus is not None:
            sources.append(focus)
        if repo_summary:
            sources.append(self._load_repo_graph_summary(repo_summary))
        resolved_plan = skill_plan or self._build_skill_plan(user_prompt, skill_context)
        sources.extend(self._load_task_skill_sources(resolved_plan, skill_context))

        snapshot = InstructionSnapshot(
            repo_root=str(self.repo_root),
            sources=self._dedupe_sources(sources),
            loaded_skills=list(resolved_plan.all_skill_names),
            system_skills=list(resolved_plan.system_skill_names),
            prompt_skills=list(resolved_plan.prompt_skill_names),
            skill_plan=resolved_plan.to_dict(),
        )

        if use_cache:
            self._cache_key = self._compute_cache_key(
                plan_mode_enabled,
                summary_hash,
                hierarchy_signature=hierarchy_sig,
            )
            self._cached_snapshot = snapshot
        return snapshot

    @staticmethod
    def _load_repo_graph_summary(summary: str) -> InstructionSource:
        return InstructionSource(
            kind="repo_graph",
            label="Repo Structure",
            content=summary,
        )

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

    def _load_hierarchical_memory(self, referenced_files: Sequence[str]) -> List[InstructionSource]:
        if self._memory_loading_disabled():
            return []
        normalized_refs = self._normalize_referenced_paths(referenced_files)
        sources: List[InstructionSource] = []

        # 1) managed memory (lowest priority)
        for path in self._managed_memory_paths():
            source = self._build_memory_source(
                path,
                kind="memory_managed",
                label="Managed Memory",
                normalized_refs=normalized_refs,
            )
            if source is not None:
                sources.append(source)

        # 2) user memory
        for path in self._user_memory_paths():
            source = self._build_memory_source(
                path,
                kind="memory_user",
                label="User Memory",
                normalized_refs=normalized_refs,
            )
            if source is not None:
                sources.append(source)

        sources.extend(self._load_agent_rule_sources(referenced_files, normalized_refs))

        # 3 + 4) project + local memory from root -> cwd
        for directory in self._dirs_root_to_cwd(self.repo_root):
            project_candidates = [directory / RULES_FILE_NAME]
            for path in project_candidates:
                source = self._build_memory_source(
                    path,
                    kind="memory_project",
                    label="Project Memory",
                    normalized_refs=normalized_refs,
                )
                if source is not None:
                    sources.append(source)

            rules_dir = directory / RULES_DIR
            if rules_dir.is_dir():
                for path in sorted(rules_dir.rglob("*.md")):
                    source = self._build_memory_source(
                        path,
                        kind="memory_rule",
                        label="Path Rule",
                        normalized_refs=normalized_refs,
                    )
                    if source is not None:
                        sources.append(source)

            local_source = self._build_memory_source(
                directory / LOCAL_MEMORY_FILE_NAME,
                kind="memory_local",
                label="Local Memory",
                normalized_refs=normalized_refs,
            )
            if local_source is not None:
                sources.append(local_source)

        return sources

    def _load_agent_rule_sources(
        self,
        referenced_files: Sequence[str],
        normalized_refs: Sequence[str],
    ) -> List[InstructionSource]:
        targets = self._rule_target_directories(referenced_files)
        seen: set[Path] = set()
        sources: List[InstructionSource] = []
        for target in targets:
            for rule in load_rules(target, repo_root=self.repo_root, referenced_files=normalized_refs):
                if rule.path in seen:
                    continue
                seen.add(rule.path)
                sources.append(
                    InstructionSource(
                        kind=rule.kind,
                        label=self._rule_label(rule.kind, rule.precedence),
                        content=rule.content,
                        path=self._relative_or_absolute(rule.path),
                        metadata={
                            "precedence": rule.precedence,
                            "applyTo": list(rule.apply_to),
                            "priority": rule.priority,
                        },
                    )
                )
        return sources

    def _rule_target_directories(self, referenced_files: Sequence[str]) -> List[Path]:
        if not referenced_files:
            return [self.repo_root]
        targets: List[Path] = []
        seen: set[Path] = set()
        for raw_path in referenced_files:
            candidate = Path(str(raw_path)).expanduser()
            if not candidate.is_absolute():
                candidate = (self.repo_root / candidate).resolve()
            else:
                candidate = candidate.resolve()
            directory = candidate if candidate.is_dir() else candidate.parent
            try:
                directory.relative_to(self.repo_root)
            except ValueError:
                directory = self.repo_root
            if directory in seen:
                continue
            seen.add(directory)
            targets.append(directory)
        return targets or [self.repo_root]

    @staticmethod
    def _rule_label(kind: str, precedence: int) -> str:
        if kind == "agents_md":
            return f"Rule Source {precedence + 1}: AGENTS.md"
        if kind == "claude_md":
            return f"Rule Source {precedence + 1}: CLAUDE.md"
        if kind == "user_global":
            return f"Rule Source {precedence + 1}: User AGENTS.md"
        return f"Rule Source {precedence + 1}"

    def _managed_memory_paths(self) -> List[Path]:
        raw = str(os.getenv(MANAGED_MEMORY_ENV, DEFAULT_MANAGED_MEMORY)).strip()
        if not raw:
            return []
        return [Path(raw).expanduser().resolve()]

    def _user_memory_paths(self) -> List[Path]:
        home = Path.home()
        candidates: List[Path] = [home / ".poor-cli" / USER_MEMORY_FILE_NAME]
        rules_dir = home / ".poor-cli" / "rules"
        if rules_dir.is_dir():
            candidates.extend(sorted(rules_dir.rglob("*.md")))
        return [path.resolve() for path in candidates]

    def _memory_loading_disabled(self) -> bool:
        return self._env_flag_enabled(DISABLE_MEMORY_ENV) or self._env_flag_enabled(DISABLE_MEMORY_ENV_ALT)

    def _allow_external_includes(self) -> bool:
        return self._env_flag_enabled(ALLOW_EXTERNAL_INCLUDES_ENV)

    def _is_memory_path_excluded(self, path: Path) -> bool:
        resolved = path.resolve()
        patterns = self._memory_exclude_patterns()
        if not patterns:
            return False
        candidates = {str(resolved), resolved.name}
        try:
            candidates.add(str(resolved.relative_to(self.repo_root)).replace("\\", "/"))
        except ValueError:
            pass
        for pattern in patterns:
            if any(fnmatch.fnmatch(candidate, pattern) for candidate in candidates):
                return True
        return False

    def _memory_exclude_patterns(self) -> List[str]:
        env_raw = str(os.getenv("POOR_CLI_MEMORY_EXCLUDES", "")).strip()
        env_patterns = [
            token.strip()
            for token in env_raw.split(",")
            if token.strip()
        ]

        file_patterns: List[str] = []
        settings_paths = [
            Path.home() / ".poor-cli" / "settings.json",
            self.repo_root / ".poor-cli" / "settings.json",
            self.repo_root / ".poor-cli" / "settings.local.json",
        ]
        for settings_path in settings_paths:
            payload = self._read_json(settings_path)
            if not isinstance(payload, dict):
                continue
            for key in ("claudeMdExcludes", "memoryExcludes"):
                raw_value = payload.get(key)
                if not isinstance(raw_value, list):
                    continue
                for value in raw_value:
                    if isinstance(value, str) and value.strip():
                        file_patterns.append(value.strip())

        seen: set[str] = set()
        deduped: List[str] = []
        for pattern in [*env_patterns, *file_patterns]:
            if pattern in seen:
                continue
            seen.add(pattern)
            deduped.append(pattern)
        return deduped

    def _approved_external_include_patterns(self) -> List[str]:
        env_raw = str(os.getenv(EXTERNAL_INCLUDE_ALLOWLIST_ENV, "")).strip()
        env_patterns = [
            token.strip()
            for token in env_raw.split(",")
            if token.strip()
        ]

        file_patterns: List[str] = []
        settings_paths = [
            Path.home() / ".poor-cli" / "settings.json",
            self.repo_root / ".poor-cli" / "settings.json",
            self.repo_root / ".poor-cli" / "settings.local.json",
        ]
        for settings_path in settings_paths:
            payload = self._read_json(settings_path)
            if not isinstance(payload, dict):
                continue
            raw_value = payload.get("approvedExternalIncludes")
            if isinstance(raw_value, list):
                for value in raw_value:
                    if isinstance(value, str) and value.strip():
                        file_patterns.append(value.strip())

        seen: set[str] = set()
        deduped: List[str] = []
        for pattern in [*env_patterns, *file_patterns]:
            if pattern in seen:
                continue
            seen.add(pattern)
            deduped.append(pattern)
        return deduped

    def _is_external_include_allowed(self, candidate: Path) -> bool:
        patterns = self._approved_external_include_patterns()
        if not patterns:
            return False
        candidate_abs = str(candidate.resolve())
        for pattern in patterns:
            if not pattern:
                continue
            expanded = str(Path(pattern).expanduser())
            if any(ch in expanded for ch in "*?[]"):
                if fnmatch.fnmatch(candidate_abs, expanded):
                    return True
                continue
            approved_path = Path(expanded)
            if not approved_path.is_absolute():
                approved_path = (self.repo_root / approved_path).resolve()
            else:
                approved_path = approved_path.resolve()
            if approved_path.is_dir():
                try:
                    candidate.relative_to(approved_path)
                    return True
                except ValueError:
                    continue
            if candidate == approved_path:
                return True
        return False

    def _build_memory_source(
        self,
        path: Path,
        *,
        kind: str,
        label: str,
        normalized_refs: Sequence[str],
    ) -> Optional[InstructionSource]:
        if not path.is_file():
            return None
        if self._is_memory_path_excluded(path):
            return None
        raw = self._read_text_raw(path)
        if not raw.strip():
            return None

        metadata: Dict[str, Any] = {}
        body = raw
        scoped_paths, stripped = self._extract_paths_frontmatter(raw)
        if scoped_paths:
            if not self._rule_paths_match(scoped_paths, normalized_refs):
                return None
            metadata["paths"] = list(scoped_paths)
            metadata["scoped"] = True
            body = stripped

        content = self._expand_includes(
            body,
            including_path=path,
            seen={path.resolve()},
            depth=0,
        ).strip()
        if not content:
            return None
        if len(content) > MAX_MEMORY_CHARACTER_COUNT:
            omitted = len(content) - MAX_MEMORY_CHARACTER_COUNT
            content = (
                content[:MAX_MEMORY_CHARACTER_COUNT]
                + f"\n\n[memory truncated: {omitted} chars omitted; size cap is {MAX_MEMORY_CHARACTER_COUNT}]"
            )
            metadata["truncated"] = True
            metadata["maxChars"] = MAX_MEMORY_CHARACTER_COUNT

        return InstructionSource(
            kind=kind,
            label=label,
            content=content,
            path=self._relative_or_absolute(path),
            metadata=metadata,
        )

    def _extract_paths_frontmatter(self, raw_text: str) -> Tuple[List[str], str]:
        if not raw_text.startswith("---"):
            return [], raw_text
        parts = raw_text.split("---", 2)
        if len(parts) < 3:
            return [], raw_text
        frontmatter = parts[1]
        body = parts[2]
        try:
            parsed = yaml.safe_load(frontmatter) or {}
        except Exception:
            return [], raw_text
        if not isinstance(parsed, dict):
            return [], raw_text
        paths = parsed.get("paths")
        if not isinstance(paths, list):
            return [], body
        normalized = [
            str(path).strip()
            for path in paths
            if isinstance(path, str) and str(path).strip()
        ]
        return normalized, body

    def _rule_paths_match(self, globs: Sequence[str], normalized_refs: Sequence[str]) -> bool:
        if not globs:
            return True
        if not normalized_refs:
            return False
        for ref in normalized_refs:
            for pattern in globs:
                if fnmatch.fnmatch(ref, pattern):
                    return True
        return False

    def _normalize_referenced_paths(self, referenced_files: Sequence[str]) -> List[str]:
        normalized: List[str] = []
        for raw in referenced_files:
            if not raw:
                continue
            candidate = Path(str(raw)).expanduser()
            if not candidate.is_absolute():
                candidate = (self.repo_root / candidate).resolve()
            else:
                candidate = candidate.resolve()
            try:
                rel = candidate.relative_to(self.repo_root)
            except ValueError:
                continue
            normalized.append(str(rel).replace("\\", "/"))
        return normalized

    def _expand_includes(
        self,
        text: str,
        *,
        including_path: Path,
        seen: set[Path],
        depth: int,
    ) -> str:
        if depth >= MAX_INCLUDE_DEPTH:
            return text

        lines = text.splitlines()
        expanded: List[str] = []
        in_fence = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                expanded.append(line)
                continue
            if in_fence:
                expanded.append(line)
                continue

            include_target = self._parse_include_target(stripped)
            if include_target is None:
                expanded.append(line)
                continue

            include_path = self._resolve_include_path(include_target, including_path.parent)
            if include_path is None:
                continue
            if include_path in seen:
                continue
            if not include_path.is_file():
                continue
            if include_path.suffix.lower() not in _TEXT_INCLUDE_SUFFIXES:
                continue

            include_text = self._read_text_raw(include_path)
            if not include_text:
                continue
            nested = self._expand_includes(
                include_text,
                including_path=include_path,
                seen={*seen, include_path},
                depth=depth + 1,
            ).strip()
            if nested:
                expanded.append(nested)

        return "\n".join(expanded)

    @staticmethod
    def _parse_include_target(stripped_line: str) -> Optional[str]:
        if not stripped_line.startswith("@"):
            return None
        token = stripped_line[1:].strip()
        if not token:
            return None
        if (token.startswith('"') and token.endswith('"')) or (
            token.startswith("'") and token.endswith("'")
        ):
            token = token[1:-1].strip()
        return token or None

    def _resolve_include_path(self, token: str, base_dir: Path) -> Optional[Path]:
        if token.startswith("~/"):
            candidate = (Path.home() / token[2:]).expanduser().resolve()
        elif token.startswith("/"):
            candidate = Path(token).expanduser().resolve()
        else:
            candidate = (base_dir / token).expanduser().resolve()

        if self._allow_external_includes():
            return candidate
        try:
            candidate.relative_to(self.repo_root)
            return candidate
        except ValueError:
            if self._is_external_include_allowed(candidate):
                return candidate
            return None

    def _load_repo_root_instructions(self) -> List[InstructionSource]:
        # trust check: skip repo instructions in untrusted repos
        try:
            from .trust import TrustManager

            if not TrustManager().is_trusted(str(self.repo_root)):
                return []
        except Exception:
            pass
        sources: List[InstructionSource] = []
        for file_name in INSTRUCTION_FILE_NAMES:
            path = self.repo_root / file_name
            content = self._load_text_with_includes(path)
            if not content:
                continue
            label = (
                f"Repo Root {file_name}"
                if file_name == "AGENTS.md"
                else f"Compatibility {file_name}"
            )
            sources.append(
                InstructionSource(
                    kind="repo_root",
                    label=label,
                    content=content,
                    path=self._relative_or_absolute(path),
                    metadata={"canonical": file_name == "AGENTS.md"},
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
            content = self._load_text_with_includes(path)
            if not content:
                continue
            label = (
                f"Path Local {path.name}"
                if path.name == "AGENTS.md"
                else f"Compatibility {path.name}"
            )
            sources.append(
                InstructionSource(
                    kind="path_local",
                    label=label,
                    content=content,
                    path=self._relative_or_absolute(path),
                    metadata={"canonical": path.name == "AGENTS.md"},
                )
            )
        return sources

    def _load_text_with_includes(self, path: Path) -> str:
        raw = self._read_text_raw(path)
        if not raw:
            return ""
        return self._expand_includes(
            raw,
            including_path=path,
            seen={path.resolve()},
            depth=0,
        ).strip()

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

    def _dirs_root_to_cwd(self, cwd: Path) -> List[Path]:
        current = cwd.resolve()
        chain = [current]
        while current.parent != current:
            current = current.parent
            chain.append(current)
        chain.reverse()
        return chain

    def _discover_hierarchical_memory_paths(self) -> List[Path]:
        if self._memory_loading_disabled():
            return []
        discovered: List[Path] = []
        seen: set[Path] = set()

        for path in self._managed_memory_paths():
            if path in seen:
                continue
            seen.add(path)
            discovered.append(path)

        for path in self._user_memory_paths():
            if path in seen:
                continue
            seen.add(path)
            discovered.append(path)

        for directory in self._dirs_root_to_cwd(self.repo_root):
            for path in (
                directory / PROJECT_MEMORY_FILE_NAME,
                directory / RULES_FILE_NAME,
                directory / LOCAL_MEMORY_FILE_NAME,
            ):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                discovered.append(resolved)
            rules_dir = directory / RULES_DIR
            if rules_dir.is_dir():
                for path in sorted(rules_dir.rglob("*.md")):
                    resolved = path.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    discovered.append(resolved)
        return discovered

    def _hierarchy_signature(self, referenced_files: Sequence[str]) -> str:
        refs = ",".join(self._normalize_referenced_paths(referenced_files))
        entries = [refs]
        for path in self._discover_hierarchical_memory_paths():
            try:
                stat = path.stat()
                entries.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError:
                entries.append(f"{path}:0:0")
        for directory in self._rule_target_directories(referenced_files):
            for path in discover_rule_paths(directory, repo_root=self.repo_root):
                try:
                    stat = path.stat()
                    entries.append(f"{path}:{stat.st_mtime_ns}:{stat.st_size}")
                except OSError:
                    entries.append(f"{path}:0:0")
        return hashlib.sha256("|".join(entries).encode("utf-8", errors="replace")).hexdigest()

    def _load_memory(self) -> Optional[InstructionSource]:
        path = self.repo_root / ".poor-cli" / "memory.md"
        content = self._load_text_with_includes(path)
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

    def _skill_registry(self) -> SkillRegistry:
        return SkillRegistry(self.repo_root, search_paths=self._skill_search_paths)

    def _instruction_skill_signature(self) -> str:
        entries: List[str] = []
        for definition in self._skill_registry().list_instruction_skills():
            try:
                stat = definition.skill_file.stat()
                entries.append(f"{definition.name}:{stat.st_mtime_ns}:{stat.st_size}")
            except OSError:
                entries.append(f"{definition.name}:0:0")
        return hashlib.sha256("|".join(entries).encode("utf-8", errors="replace")).hexdigest()

    def _build_skill_plan(
        self,
        user_prompt: str,
        skill_context: Optional[InstructionSkillContext],
    ) -> SkillLoadPlan:
        registry = self._skill_registry()
        context = skill_context or InstructionSkillContext(current_dir=str(self.repo_root))
        return registry.build_instruction_plan(user_prompt, context)

    def _load_task_skill_sources(
        self,
        skill_plan: SkillLoadPlan,
        skill_context: Optional[InstructionSkillContext],
    ) -> List[InstructionSource]:
        prompt_skills = list(skill_plan.prompt_skill_names)
        if not prompt_skills:
            return []
        registry = self._skill_registry()
        context = skill_context or InstructionSkillContext(current_dir=str(self.repo_root))
        definitions = {skill.name: skill for skill in registry.list_instruction_skills()}
        sources: List[InstructionSource] = []
        for name in prompt_skills:
            definition = definitions.get(name)
            if definition is None:
                continue
            content = registry.render_instruction_skills([name], context)
            if not content:
                continue
            sources.append(
                InstructionSource(
                    kind="task_skill",
                    label=f"Task Skill: {name}",
                    content=content,
                    path=str(definition.skill_file),
                    metadata={
                        "skillName": name,
                        "scope": definition.scope,
                        "description": definition.description,
                    },
                )
            )
        return sources

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @staticmethod
    def _read_text_raw(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    @staticmethod
    def _read_json(path: Path) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @staticmethod
    def _env_flag_enabled(name: str) -> bool:
        raw = str(os.getenv(name, "")).strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _dedupe_sources(sources: Sequence[InstructionSource]) -> List[InstructionSource]:
        deduped: List[InstructionSource] = []
        seen_paths: set[str] = set()
        for source in sources:
            path_key = source.path or ""
            if path_key and path_key in seen_paths:
                continue
            if path_key:
                seen_paths.add(path_key)
            deduped.append(source)
        return deduped

    def _relative_or_absolute(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.repo_root))
        except ValueError:
            return str(path.resolve())
