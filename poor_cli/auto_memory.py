"""
Autonomous memory generation for poor-cli.

Analyzes conversation sessions and automatically extracts memorable
patterns — user preferences, project decisions, and coding conventions.
Runs at session end or on-demand.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .memory import MemoryManager, MemoryEntry, MEMORY_TYPES
from .exceptions import setup_logger

logger = setup_logger(__name__)

# heuristic patterns that signal memorable content
_PREFERENCE_SIGNALS = [
    (r"\b(always|never|prefer|don't|avoid|use|switch to)\b", "feedback"),
    (r"\b(I('m| am) a|my role|I work|my team)\b", "user"),
    (r"\b(deadline|release|freeze|sprint|milestone)\b", "project"),
    (r"\b(tracked in|dashboard at|slack channel|linear|jira)\b", "reference"),
]

_MIN_CONTENT_LENGTH = 20
_MAX_MEMORIES_PER_SESSION = 5


def extract_memories_from_history(
    messages: List[Dict[str, Any]],
    existing_names: Optional[set[str]] = None,
) -> List[MemoryEntry]:
    """
    Analyze conversation messages and extract candidate memories.

    Looks for user messages containing preference signals, decisions,
    or contextual information worth persisting.
    """
    existing = existing_names or set()
    candidates: List[MemoryEntry] = []

    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", "") or msg.get("parts", [""])[0] if isinstance(msg.get("parts"), list) else msg.get("content", ""))
        if role != "user" or len(content) < _MIN_CONTENT_LENGTH:
            continue

        for pattern, mem_type in _PREFERENCE_SIGNALS:
            if re.search(pattern, content, re.IGNORECASE):
                name = _generate_name(content, mem_type)
                if name.lower() in existing:
                    continue
                description = content[:100].strip()
                candidates.append(MemoryEntry(
                    name=name,
                    description=description,
                    type=mem_type,
                    content=content[:500].strip(),
                ))
                existing.add(name.lower())
                break # one memory per message

        if len(candidates) >= _MAX_MEMORIES_PER_SESSION:
            break

    return candidates


def _generate_name(content: str, mem_type: str) -> str:
    """Generate a short descriptive name from content."""
    # take first meaningful clause
    content = content.strip()
    # strip markdown/code
    content = re.sub(r'```[\s\S]*?```', '', content)
    content = re.sub(r'`[^`]+`', '', content)
    # first sentence or clause
    for sep in [".", "!", "?", ",", "\n"]:
        if sep in content[:80]:
            content = content[:content.index(sep)]
            break
    words = content.split()[:6]
    name = " ".join(words).strip()
    if len(name) < 5:
        name = f"{mem_type} note"
    return name[:60]


async def auto_save_session_memories(
    messages: List[Dict[str, Any]],
    base_dir: Any = None,
) -> List[str]:
    """
    Analyze a session's messages and auto-save any detected memories.

    Returns list of saved memory names.
    """
    mgr = MemoryManager(base_dir)
    mgr.load()
    existing_names = {e.name.lower() for e in mgr.list_all()}

    candidates = extract_memories_from_history(messages, existing_names)
    saved: List[str] = []
    for entry in candidates:
        try:
            mgr.save(entry)
            saved.append(entry.name)
            logger.info("auto-saved memory: %s (%s)", entry.name, entry.type)
        except Exception as exc:
            logger.warning("failed to auto-save memory %s: %s", entry.name, exc)

    return saved
