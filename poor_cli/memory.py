"""
Persistent memory system for poor-cli.

Stores cross-session memories (user prefs, feedback, project context, references)
in ~/.poor-cli/memory/ as individual markdown files with YAML frontmatter.
MEMORY.md acts as a searchable index loaded into every session.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger, ValidationError

logger = setup_logger(__name__)

MEMORY_TYPES = ("user", "feedback", "project", "reference")
MAX_INDEX_ENTRIES = 200
MEMORY_DIR_NAME = "memory"
INDEX_FILE = "MEMORY.md"


@dataclass
class MemoryEntry:
    """Single memory record."""
    name: str
    description: str
    type: str # user | feedback | project | reference
    content: str
    filename: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if self.type not in MEMORY_TYPES:
            raise ValidationError(f"invalid memory type: {self.type}; expected one of {MEMORY_TYPES}")
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.filename:
            self.filename = _slugify(self.name) + ".md"

    def render_file(self) -> str:
        """Render as markdown with YAML frontmatter."""
        return (
            f"---\n"
            f"name: {self.name}\n"
            f"description: {self.description}\n"
            f"type: {self.type}\n"
            f"created_at: {self.created_at}\n"
            f"updated_at: {self.updated_at}\n"
            f"---\n\n"
            f"{self.content}\n"
        )

    def index_line(self) -> str:
        """One-line entry for MEMORY.md index."""
        return f"- [{self.name}]({self.filename}) — {self.description}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "content": self.content,
            "filename": self.filename,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def _slugify(text: str) -> str:
    """Convert text to filesystem-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower().strip())
    slug = re.sub(r"[\s_]+", "_", slug)
    return slug[:80] or "memory"


def _parse_frontmatter(text: str) -> tuple[Dict[str, str], str]:
    """Parse YAML frontmatter from markdown file."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: Dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    body = parts[2].strip()
    return meta, body


class MemoryManager:
    """Manages persistent memory files in ~/.poor-cli/memory/."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        *,
        repo_root: Optional[Path] = None,
        prefer_agent_rules: bool = False,
    ):
        self._base = (base_dir or Path.home() / ".poor-cli").resolve()
        self._repo_root = Path(repo_root).resolve() if repo_root is not None else None
        self._prefer_agent_rules = prefer_agent_rules
        self._memory_dir = self._base / MEMORY_DIR_NAME
        self._index_path = self._memory_dir / INDEX_FILE
        self._entries: Dict[str, MemoryEntry] = {} # keyed by filename
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    # ── loading ──────────────────────────────────────────────────────────

    def load(self) -> List[MemoryEntry]:
        """Load all memory files from disk."""
        self._entries.clear()
        for path in sorted(self._memory_dir.glob("*.md")):
            if path.name == INDEX_FILE:
                continue
            try:
                text = path.read_text(encoding="utf-8")
                meta, body = _parse_frontmatter(text)
                entry = MemoryEntry(
                    name=meta.get("name", path.stem),
                    description=meta.get("description", ""),
                    type=meta.get("type", "project"),
                    content=body,
                    filename=path.name,
                    created_at=meta.get("created_at", ""),
                    updated_at=meta.get("updated_at", ""),
                )
                self._entries[path.name] = entry
            except Exception as exc:
                logger.warning("failed to load memory %s: %s", path.name, exc)
        return list(self._entries.values())

    def load_index(self) -> str:
        """Return raw MEMORY.md content (loaded into every session context)."""
        if self._index_path.exists():
            text = self._index_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            if len(lines) > MAX_INDEX_ENTRIES:
                lines = lines[:MAX_INDEX_ENTRIES]
                lines.append(f"\n<!-- truncated at {MAX_INDEX_ENTRIES} entries -->")
            return "\n".join(lines)
        return ""

    # ── writing ──────────────────────────────────────────────────────────

    def save(self, entry: MemoryEntry) -> MemoryEntry:
        """Save a memory entry to disk and update index."""
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        if self._prefer_agent_rules and self._repo_root is not None:
            from .agent_rules import append_memory_entry
            if append_memory_entry(self._repo_root, entry.name, entry.content, entry.description) is not None:
                logger.info("saved memory to AGENTS.md: %s", entry.name)
                return entry
        path = self._memory_dir / entry.filename
        path.write_text(entry.render_file(), encoding="utf-8")
        self._entries[entry.filename] = entry
        self._rebuild_index()
        logger.info("saved memory: %s (%s)", entry.name, entry.filename)
        return entry

    def delete(self, name: str) -> bool:
        """Delete a memory by name. Returns True if found and deleted."""
        target = self._find_by_name(name)
        if not target:
            return False
        path = self._memory_dir / target.filename
        if path.exists():
            path.unlink()
        del self._entries[target.filename]
        self._rebuild_index()
        logger.info("deleted memory: %s", name)
        return True

    def update(self, name: str, content: Optional[str] = None,
               description: Optional[str] = None, type_: Optional[str] = None) -> Optional[MemoryEntry]:
        """Update an existing memory's content/description/type."""
        target = self._find_by_name(name)
        if not target:
            return None
        if content is not None:
            target.content = content
        if description is not None:
            target.description = description
        if type_ is not None:
            target.type = type_
        return self.save(target)

    # ── searching ────────────────────────────────────────────────────────

    def search(self, query: str, type_filter: Optional[str] = None,
               max_results: int = 10) -> List[MemoryEntry]:
        """Keyword search over memory names, descriptions, and content."""
        if not self._entries:
            self.load()
        query_lower = query.lower()
        tokens = query_lower.split()
        scored: List[tuple[float, MemoryEntry]] = []
        for entry in self._entries.values():
            if type_filter and entry.type != type_filter:
                continue
            text = f"{entry.name} {entry.description} {entry.content}".lower()
            score = sum(1.0 for t in tokens if t in text)
            if entry.name.lower() == query_lower:
                score += 5.0 # exact name match bonus
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_results]]

    def get_relevant(self, context: str, max_results: int = 5) -> List[MemoryEntry]:
        """Return memories relevant to the given context string."""
        return self.search(context, max_results=max_results)

    def list_all(self, type_filter: Optional[str] = None) -> List[MemoryEntry]:
        """List all memories, optionally filtered by type."""
        if not self._entries:
            self.load()
        entries = list(self._entries.values())
        if type_filter:
            entries = [e for e in entries if e.type == type_filter]
        return sorted(entries, key=lambda e: e.updated_at, reverse=True)

    def get(self, name: str) -> Optional[MemoryEntry]:
        """Get a specific memory by name."""
        if not self._entries:
            self.load()
        return self._find_by_name(name)

    # ── internal ─────────────────────────────────────────────────────────

    def _find_by_name(self, name: str) -> Optional[MemoryEntry]:
        """Find entry by name (case-insensitive)."""
        name_lower = name.lower()
        for entry in self._entries.values():
            if entry.name.lower() == name_lower:
                return entry
        # fallback: filename match
        slug = _slugify(name) + ".md"
        return self._entries.get(slug)

    def _rebuild_index(self) -> None:
        """Rebuild MEMORY.md index from current entries."""
        lines = ["# Memory Index", ""]
        by_type: Dict[str, List[MemoryEntry]] = {}
        for entry in self._entries.values():
            by_type.setdefault(entry.type, []).append(entry)
        for mtype in MEMORY_TYPES:
            entries = by_type.get(mtype, [])
            if not entries:
                continue
            lines.append(f"## {mtype.title()}")
            for entry in sorted(entries, key=lambda e: e.name.lower()):
                lines.append(entry.index_line())
            lines.append("")
        text = "\n".join(lines[:MAX_INDEX_ENTRIES + 10]) # generous header allowance
        self._index_path.write_text(text, encoding="utf-8")
