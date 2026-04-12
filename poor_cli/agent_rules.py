"""AGENTS.md / CLAUDE.md rule source loading."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

import yaml

RuleKind = Literal["agents_md", "claude_md", "poor_memory", "user_global"]
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


@dataclass(frozen=True)
class RuleSource:
    path: Path
    content: str
    precedence: int
    kind: RuleKind
    apply_to: tuple[str, ...] = ("**/*",)
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def load_rules(
    cwd: Path,
    *,
    repo_root: Optional[Path] = None,
    referenced_files: Optional[Sequence[str]] = None,
) -> list[RuleSource]:
    cwd = Path(cwd).expanduser().resolve()
    root = Path(repo_root).expanduser().resolve() if repo_root else None
    refs = tuple(str(path).replace("\\", "/") for path in (referenced_files or []) if str(path).strip())
    sources: list[RuleSource] = []
    seen_paths: set[Path] = set()
    dirs = _dirs_closest_to_root(cwd, root)

    precedence = 0
    agent_dirs: set[Path] = set()
    for directory in dirs:
        path = directory / "AGENTS.md"
        source = _source_from_file(path, precedence=precedence, kind="agents_md", refs=refs, repo_root=root)
        if source is None:
            continue
        sources.append(source)
        seen_paths.add(path.resolve())
        agent_dirs.add(directory.resolve())
        precedence += 1

    for directory in dirs:
        if directory.resolve() in agent_dirs:
            continue
        path = directory / "CLAUDE.md"
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        source = _source_from_file(path, precedence=precedence, kind="claude_md", refs=refs, repo_root=root)
        if source is None:
            continue
        sources.append(source)
        seen_paths.add(resolved)
        precedence += 1

    global_path = (Path.home() / ".poor-cli" / "AGENTS.md").resolve()
    if global_path not in seen_paths:
        source = _source_from_file(global_path, precedence=precedence, kind="user_global", refs=refs, repo_root=None)
        if source is not None:
            sources.append(source)
    return sources


def discover_rule_paths(cwd: Path, *, repo_root: Optional[Path] = None) -> list[Path]:
    cwd = Path(cwd).expanduser().resolve()
    root = Path(repo_root).expanduser().resolve() if repo_root else None
    paths: list[Path] = []
    seen: set[Path] = set()
    for directory in _dirs_closest_to_root(cwd, root):
        for name in ("AGENTS.md", "CLAUDE.md"):
            path = (directory / name).resolve()
            if path in seen:
                continue
            seen.add(path)
            paths.append(path)
    global_path = (Path.home() / ".poor-cli" / "AGENTS.md").resolve()
    if global_path not in seen:
        paths.append(global_path)
    return paths


def merge(sources: Sequence[RuleSource]) -> str:
    paragraphs: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for paragraph in source.content.split("\n\n"):
            normalized = " ".join(paragraph.split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            paragraphs.append(paragraph.strip())
    return "\n\n".join(paragraphs)


def append_memory_entry(repo_root: Path, title: str, content: str, description: str = "") -> Optional[Path]:
    path = Path(repo_root).expanduser().resolve() / "AGENTS.md"
    if not path.is_file():
        return None
    lines = ["", f"## Memory: {title.strip() or 'project note'}"]
    if description.strip():
        lines.append(description.strip())
    if content.strip():
        lines.extend(["", content.strip()])
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return path


def _dirs_closest_to_root(cwd: Path, root: Optional[Path]) -> list[Path]:
    current = cwd if cwd.is_dir() else cwd.parent
    dirs = [current]
    while current.parent != current:
        if root is not None and current == root:
            break
        current = current.parent
        dirs.append(current)
    return dirs


def _source_from_file(
    path: Path,
    *,
    precedence: int,
    kind: RuleKind,
    refs: Sequence[str],
    repo_root: Optional[Path],
) -> Optional[RuleSource]:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    body, metadata = _split_frontmatter(raw)
    content = _expand_includes(
        body,
        including_path=path,
        repo_root=repo_root,
        seen={path.resolve()},
        depth=0,
    ).strip()
    if not content:
        return None
    apply_to = _normalize_patterns(metadata.get("apply_to") or metadata.get("paths") or ("**/*",))
    if not _matches_apply_to(apply_to or ("**/*",), refs):
        return None
    try:
        priority = int(metadata.get("priority", 0) or 0)
    except (TypeError, ValueError):
        priority = 0
    return RuleSource(
        path=path.resolve(),
        content=content,
        precedence=precedence,
        kind=kind,
        apply_to=apply_to or ("**/*",),
        priority=priority,
        metadata=metadata,
    )


def _split_frontmatter(raw: str) -> tuple[str, dict[str, Any]]:
    if not raw.startswith("---"):
        return raw, {}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return raw, {}
    try:
        parsed = yaml.safe_load(parts[1]) or {}
    except Exception:
        return raw, {}
    if not isinstance(parsed, dict):
        return parts[2], {}
    return parts[2], parsed


def _normalize_patterns(raw: Any) -> tuple[str, ...]:
    if isinstance(raw, str):
        values = (raw,)
    elif isinstance(raw, Sequence):
        values = tuple(raw)
    else:
        values = ("**/*",)
    return tuple(str(item).strip() for item in values if str(item).strip())


def _matches_apply_to(patterns: Sequence[str], refs: Sequence[str]) -> bool:
    positives = [pattern for pattern in patterns if not pattern.startswith("!")]
    negatives = [pattern[1:] for pattern in patterns if pattern.startswith("!")]
    if not refs:
        return True
    for ref in refs:
        positive_hit = not positives or any(fnmatch.fnmatch(ref, pattern) for pattern in positives)
        negative_hit = any(fnmatch.fnmatch(ref, pattern) for pattern in negatives)
        if positive_hit and not negative_hit:
            return True
    return False


def _expand_includes(
    text: str,
    *,
    including_path: Path,
    repo_root: Optional[Path],
    seen: set[Path],
    depth: int,
) -> str:
    if depth >= 5:
        return text
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            lines.append(line)
            continue
        if in_fence or not stripped.startswith("@"):
            lines.append(line)
            continue
        token = stripped[1:].strip().strip("'\"")
        if not token:
            lines.append(line)
            continue
        target = (Path.home() / token[2:]).resolve() if token.startswith("~/") else (including_path.parent / token).resolve()
        if Path(token).is_absolute():
            target = Path(token).expanduser().resolve()
        if repo_root is not None:
            try:
                target.relative_to(repo_root)
            except ValueError:
                continue
        if target in seen or not target.is_file() or target.suffix.lower() not in _TEXT_INCLUDE_SUFFIXES:
            continue
        nested = target.read_text(encoding="utf-8")
        expanded = _expand_includes(
            nested,
            including_path=target,
            repo_root=repo_root,
            seen={*seen, target},
            depth=depth + 1,
        ).strip()
        if expanded:
            lines.append(expanded)
    return "\n".join(lines)
