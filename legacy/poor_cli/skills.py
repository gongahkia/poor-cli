"""
Repo-local and user-global skill discovery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

BUILTIN_INSTRUCTION_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
DEFAULT_CLASSIFIER_TASK_TYPES: Tuple[str, ...] = (
    "edit",
    "refactor",
    "debug",
    "test",
    "review",
    "git",
    "deploy",
)


@dataclass(frozen=True)
class InstructionSkillDefinition:
    name: str
    skill_file: Path
    description: str
    scope: str
    target: str = "prompt"
    always_load: bool = False
    keywords: Tuple[str, ...] = ()
    contexts: Tuple[str, ...] = ()
    priority: int = 100

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "skillFile": str(self.skill_file),
            "description": self.description,
            "scope": self.scope,
            "target": self.target,
            "alwaysLoad": self.always_load,
            "keywords": list(self.keywords),
            "contexts": list(self.contexts),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class InstructionSkillContext:
    current_dir: str
    plan_mode_enabled: bool = False
    sandbox_preset: str = "workspace-write"
    terse_mode: bool = False
    batched_reads: bool = False
    most_used_task_types: Tuple[str, ...] = DEFAULT_CLASSIFIER_TASK_TYPES

    def tags(self) -> Tuple[str, ...]:
        tags: List[str] = []
        if self.plan_mode_enabled:
            tags.append("plan_mode")
        if self.sandbox_preset == "read-only":
            tags.append("read_only")
        if self.terse_mode:
            tags.append("terse_mode")
        if self.batched_reads:
            tags.append("batched_reads")
        return tuple(tags)

    def render_vars(self) -> Dict[str, str]:
        return {
            "current_dir": self.current_dir,
            "most_used_task_types": ", ".join(self.most_used_task_types),
        }


@dataclass(frozen=True)
class SkillLoadPlan:
    system_skill_names: Tuple[str, ...] = ()
    prompt_skill_names: Tuple[str, ...] = ()
    fallback_loaded_all: bool = False
    matched_keywords: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def all_skill_names(self) -> Tuple[str, ...]:
        names = list(self.system_skill_names)
        for name in self.prompt_skill_names:
            if name not in names:
                names.append(name)
        return tuple(names)

    def to_dict(self) -> dict:
        return {
            "systemSkills": list(self.system_skill_names),
            "promptSkills": list(self.prompt_skill_names),
            "loadedSkills": list(self.all_skill_names),
            "fallbackLoadedAll": self.fallback_loaded_all,
            "matchedKeywords": dict(self.matched_keywords),
        }


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    root: Path
    skill_file: Path
    description: str
    assets_dir: Optional[Path]
    scripts_dir: Optional[Path]
    scope: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "root": str(self.root),
            "skillFile": str(self.skill_file),
            "description": self.description,
            "assetsDir": str(self.assets_dir) if self.assets_dir else None,
            "scriptsDir": str(self.scripts_dir) if self.scripts_dir else None,
            "scope": self.scope,
        }


def default_skill_search_paths(repo_root: Path) -> List[Path]:
    return [
        repo_root / ".poor-cli" / "skills",
        Path.home() / ".poor-cli" / "skills",
    ]


class SkillRegistry:
    def __init__(
        self,
        repo_root: Optional[Path] = None,
        search_paths: Optional[Sequence[str]] = None,
    ) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        configured = [Path(path).expanduser() for path in (search_paths or []) if str(path).strip()]
        self.search_paths = _dedupe_paths(
            list(default_skill_search_paths(self.repo_root)) + configured
        )

    def list_skills(self) -> List[SkillDefinition]:
        # trust check: filter repo-local skills in untrusted repos
        _repo_skill_dir = self.repo_root / ".poor-cli" / "skills"
        _skip_repo = False
        try:
            from .trust import TrustManager
            if not TrustManager().is_trusted(str(self.repo_root)):
                _skip_repo = True
        except Exception:
            pass
        discovered: List[SkillDefinition] = []
        seen: set[str] = set()
        for root in self.search_paths:
            if _skip_repo and root == _repo_skill_dir:
                continue
            if not root.is_dir():
                continue
            for skill_dir in sorted(path for path in root.iterdir() if path.is_dir()):
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.is_file():
                    continue
                name = skill_dir.name
                if name in seen:
                    continue
                seen.add(name)
                discovered.append(_build_skill_definition(root, skill_dir, skill_file, self.repo_root))
        return discovered

    def list_instruction_skills(self) -> List[InstructionSkillDefinition]:
        discovered: List[InstructionSkillDefinition] = []
        seen: set[str] = set()
        roots: List[tuple[Path, str]] = [(BUILTIN_INSTRUCTION_SKILLS_DIR, "builtin")]
        roots.extend((root, _instruction_scope(root, self.repo_root)) for root in self.search_paths)
        skip_repo = _skip_untrusted_repo_skills(self.repo_root)
        repo_skill_dir = self.repo_root / ".poor-cli" / "skills"
        for root, scope in roots:
            if skip_repo and root == repo_skill_dir:
                continue
            if not root.is_dir():
                continue
            for skill_file in sorted(root.glob("*.md")):
                if skill_file.name == "SKILL.md":
                    continue
                name = skill_file.stem
                if name in seen:
                    continue
                seen.add(name)
                discovered.append(_build_instruction_skill_definition(skill_file, scope))
        return discovered

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        normalized = str(name).strip()
        if not normalized:
            return None
        for skill in self.list_skills():
            if skill.name == normalized:
                return skill
        return None

    def render_skill_prompt(self, name: str, request: str) -> str:
        skill = self.get_skill(name)
        if skill is None:
            raise FileNotFoundError(f"Unknown skill: {name}")
        body = skill.skill_file.read_text(encoding="utf-8")
        sections = [f"[Skill: {skill.name}]", body.strip()]
        if skill.assets_dir and skill.assets_dir.is_dir():
            sections.append(f"[Assets directory]\n{skill.assets_dir}")
        if skill.scripts_dir and skill.scripts_dir.is_dir():
            sections.append(f"[Scripts directory]\n{skill.scripts_dir}")
        if request.strip():
            sections.append(f"[User request]\n{request.strip()}")
        return "\n\n".join(section for section in sections if section)

    def build_instruction_plan(
        self,
        prompt: str,
        context: Optional[InstructionSkillContext] = None,
    ) -> SkillLoadPlan:
        ctx = context or InstructionSkillContext(current_dir=str(self.repo_root))
        try:
            defs = self.list_instruction_skills()
            if not defs:
                return SkillLoadPlan()
            matched_keywords = _match_instruction_skills(prompt, defs, ctx)
            system: List[str] = []
            prompt_names: List[str] = []
            for definition in sorted(defs, key=lambda item: (item.priority, item.name)):
                has_context = any(tag in ctx.tags() for tag in definition.contexts)
                has_keyword = bool(matched_keywords.get(definition.name))
                if not definition.always_load and not has_context and not has_keyword:
                    continue
                target = system if definition.target == "system" else prompt_names
                if definition.name not in target:
                    target.append(definition.name)
            return SkillLoadPlan(
                system_skill_names=tuple(system),
                prompt_skill_names=tuple(prompt_names),
                fallback_loaded_all=False,
                matched_keywords=matched_keywords,
            )
        except Exception:
            defs = self.list_instruction_skills()
            system = tuple(
                definition.name
                for definition in sorted(defs, key=lambda item: (item.priority, item.name))
                if definition.target == "system"
            )
            prompt_names = tuple(
                definition.name
                for definition in sorted(defs, key=lambda item: (item.priority, item.name))
                if definition.target != "system"
            )
            return SkillLoadPlan(
                system_skill_names=system,
                prompt_skill_names=prompt_names,
                fallback_loaded_all=True,
                matched_keywords={},
            )

    def render_instruction_skills(
        self,
        skill_names: Sequence[str],
        context: Optional[InstructionSkillContext] = None,
    ) -> str:
        ctx = context or InstructionSkillContext(current_dir=str(self.repo_root))
        if not skill_names:
            return ""
        skill_map = {skill.name: skill for skill in self.list_instruction_skills()}
        rendered: List[str] = []
        for name in skill_names:
            definition = skill_map.get(name)
            if definition is None:
                continue
            body = _load_instruction_skill_body(definition.skill_file)
            if not body:
                continue
            rendered.append(_render_instruction_body(body, ctx.render_vars()).strip())
        return "\n\n".join(chunk for chunk in rendered if chunk).strip()

    def render_system_instruction(
        self,
        prompt: str,
        context: Optional[InstructionSkillContext] = None,
        *,
        max_system_tokens: int = 0,
    ) -> str:
        ctx = context or InstructionSkillContext(current_dir=str(self.repo_root))
        plan = self.build_instruction_plan(prompt, ctx)
        definitions = {skill.name: skill for skill in self.list_instruction_skills()}
        ordered = [
            name for name in plan.system_skill_names
            if name in definitions
        ]
        if not ordered:
            return ""
        if max_system_tokens > 0:
            keep = list(ordered)
            while len(self.render_instruction_skills(keep, ctx)) // 4 > max_system_tokens and len(keep) > 1:
                keep.pop()
            ordered = keep
        return self.render_instruction_skills(ordered, ctx)


def _build_skill_definition(root: Path, skill_dir: Path, skill_file: Path, repo_root: Path) -> SkillDefinition:
    scope = "repo" if root == repo_root / ".poor-cli" / "skills" else "user"
    body = skill_file.read_text(encoding="utf-8")
    description = _skill_description(body)
    assets_dir = skill_dir / "assets"
    scripts_dir = skill_dir / "scripts"
    return SkillDefinition(
        name=skill_dir.name,
        root=skill_dir,
        skill_file=skill_file,
        description=description,
        assets_dir=assets_dir if assets_dir.is_dir() else None,
        scripts_dir=scripts_dir if scripts_dir.is_dir() else None,
        scope=scope,
    )


def _skill_description(body: str) -> str:
    lines = [line.strip() for line in body.splitlines()]
    for line in lines:
        if not line or line.startswith("#"):
            continue
        return line
    return "No description provided."


def _build_instruction_skill_definition(skill_file: Path, scope: str) -> InstructionSkillDefinition:
    raw = skill_file.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(raw)
    keywords = tuple(_normalize_string_list(metadata.get("keywords")))
    contexts = tuple(_normalize_string_list(metadata.get("contexts")))
    target = str(metadata.get("target", "prompt") or "prompt").strip().lower()
    if target not in {"system", "prompt"}:
        target = "prompt"
    priority = _coerce_int(metadata.get("priority"), default=100)
    description = str(metadata.get("description", "")).strip() or _skill_description(body)
    return InstructionSkillDefinition(
        name=skill_file.stem,
        skill_file=skill_file,
        description=description,
        scope=scope,
        target=target,
        always_load=_coerce_bool(metadata.get("always_load")),
        keywords=keywords,
        contexts=contexts,
        priority=priority,
    )


def _load_instruction_skill_body(skill_file: Path) -> str:
    raw = skill_file.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    return body.strip()


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end == -1:
        return {}, raw
    frontmatter = raw[4:end]
    body = raw[end + 5 :]
    try:
        parsed = yaml.safe_load(frontmatter) or {}
    except Exception:
        return {}, raw
    if not isinstance(parsed, dict):
        return {}, body
    return parsed, body


def _normalize_string_list(raw: object) -> List[str]:
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = [item for item in raw if isinstance(item, str)]
    else:
        items = []
    return [item.strip() for item in items if item and item.strip()]


def _coerce_bool(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _coerce_int(raw: object, *, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _instruction_scope(root: Path, repo_root: Path) -> str:
    if root == repo_root / ".poor-cli" / "skills":
        return "repo"
    if root == Path.home() / ".poor-cli" / "skills":
        return "user"
    return "custom"


def _skip_untrusted_repo_skills(repo_root: Path) -> bool:
    try:
        from .trust import TrustManager
        return not TrustManager().is_trusted(str(repo_root))
    except Exception:
        return False


def _match_instruction_skills(
    prompt: str,
    definitions: Sequence[InstructionSkillDefinition],
    context: InstructionSkillContext,
) -> Dict[str, List[str]]:
    lowered = str(prompt or "").lower()
    matches: Dict[str, List[str]] = {}
    if not lowered:
        return matches
    for definition in definitions:
        hits: List[str] = []
        for keyword in definition.keywords:
            if _keyword_matches(lowered, keyword):
                hits.append(keyword)
        if not hits and definition.scope != "builtin" and _keyword_matches(lowered, definition.name):
            hits.append(definition.name)
        if hits:
            matches[definition.name] = hits
    return matches


def _keyword_matches(prompt: str, keyword: str) -> bool:
    normalized = str(keyword or "").strip().lower()
    if not normalized:
        return False
    if " " in normalized:
        return normalized in prompt
    return re.search(rf"\b{re.escape(normalized)}\b", prompt) is not None


def _render_instruction_body(body: str, vars_map: Dict[str, str]) -> str:
    rendered = body
    for key, value in vars_map.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


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
