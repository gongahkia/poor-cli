"""
Repo-local and user-global skill discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


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
