"""
Autonomous memory generation for poor-cli.

Analyzes conversation sessions and automatically extracts memorable
patterns — user preferences, project decisions, and coding conventions.
Supports both heuristic extraction and LLM-based distillation.
Runs at session end or on-demand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory import MemoryManager, MemoryEntry, MEMORY_TYPES, hash_source_message
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

_LLM_DISTILL_PROMPT = """Analyze this conversation and extract key learnings worth remembering for future sessions.
Return a JSON array of objects with fields: name, description, type, content.
- type must be one of: user, feedback, project, reference
- "user": info about the user's role, preferences, expertise
- "feedback": guidance on how to approach work (corrections or confirmations)
- "project": ongoing project context (goals, deadlines, decisions)
- "reference": pointers to external systems/resources
- Only extract genuinely useful, non-obvious information
- Skip anything derivable from code or git history
- Maximum 5 entries
- Return [] if nothing worth remembering

Conversation:
"""
_LLM_DISTILL_MAX_CHARS = 30000


def extract_memories_from_history(
    messages: List[Dict[str, Any]],
    existing_names: Optional[set[str]] = None,
    *,
    source_session_id: str = "",
) -> List[MemoryEntry]:
    """
    Analyze conversation messages and extract candidate memories via heuristics.

    Looks for user messages containing preference signals, decisions,
    or contextual information worth persisting. Records provenance
    (source_session_id, source_turn_id, source_message_hash, extractor)
    on every candidate so future cascading deletes and audit trails work.
    """
    existing = existing_names or set()
    candidates: List[MemoryEntry] = []

    for turn_index, msg in enumerate(messages):
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
                    source_session_id=source_session_id,
                    source_turn_id=str(turn_index),
                    source_message_hash=hash_source_message(content),
                    extractor="heuristic",
                    derivation_depth=0,
                ))
                existing.add(name.lower())
                break # one memory per message

        if len(candidates) >= _MAX_MEMORIES_PER_SESSION:
            break

    return candidates


async def extract_memories_with_llm(
    messages: List[Dict[str, Any]],
    provider: Any,
    existing_names: Optional[set[str]] = None,
    *,
    source_session_id: str = "",
) -> List[MemoryEntry]:
    """Use LLM to distill memorable learnings from conversation history.

    Records provenance on every extracted memory including source_session_id,
    an aggregate source_message_hash covering the distilled prompt, and
    derivation_depth=1 (the LLM did one layer of summarization).
    """
    existing = existing_names or set()
    conversation_parts = []
    total_chars = 0
    for msg in messages:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", ""))[:500]
        entry = f"[{role}]: {content}"
        if total_chars + len(entry) > _LLM_DISTILL_MAX_CHARS:
            break
        conversation_parts.append(entry)
        total_chars += len(entry)
    if not conversation_parts:
        return []
    joined = "\n".join(conversation_parts)
    prompt = _LLM_DISTILL_PROMPT + joined
    source_hash = hash_source_message(joined)
    response = await provider.send_message(prompt)
    raw = (response.content or "").strip()
    # extract JSON array from response (may be wrapped in ```json blocks)
    json_match = re.search(r'\[[\s\S]*\]', raw)
    if not json_match:
        return []
    try:
        items = json.loads(json_match.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    candidates: List[MemoryEntry] = []
    for item in items[:_MAX_MEMORIES_PER_SESSION]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        mem_type = str(item.get("type", "")).strip()
        if not name or mem_type not in MEMORY_TYPES or name.lower() in existing:
            continue
        candidates.append(MemoryEntry(
            name=name,
            description=str(item.get("description", name))[:100],
            type=mem_type,
            content=str(item.get("content", ""))[:500].strip(),
            source_session_id=source_session_id,
            source_turn_id="aggregate",
            source_message_hash=source_hash,
            extractor="llm",
            derivation_depth=1,
        ))
        existing.add(name.lower())
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
    provider: Any = None,
    *,
    source_session_id: str = "",
    review_mode: str = "auto",
) -> List[str]:
    """
    Analyze a session's messages and auto-save any detected memories.
    Uses LLM distillation if provider is available, else falls back to heuristics.

    review_mode controls MH4 in-loop review:
    - "auto" (default): save candidates directly (legacy behavior).
    - "prompt": write candidates to ``<memory_dir>/_pending/`` instead of
      the live store so a user-facing review surface can accept/edit/reject
      before persistence.

    Returns list of saved memory names. Memories carry provenance
    (source_session_id, extractor, derivation_depth) for MH3 cascading deletes.
    """
    mgr = MemoryManager(base_dir, repo_root=Path.cwd() if base_dir is None else None, prefer_agent_rules=base_dir is None)
    mgr.load()
    existing_names = {e.name.lower() for e in mgr.list_all()}

    if provider:
        try:
            candidates = await extract_memories_with_llm(messages, provider, existing_names, source_session_id=source_session_id)
        except Exception as e:
            logger.warning("LLM memory distillation failed, falling back to heuristics: %s", e)
            candidates = extract_memories_from_history(messages, existing_names, source_session_id=source_session_id)
    else:
        candidates = extract_memories_from_history(messages, existing_names, source_session_id=source_session_id)

    if review_mode == "prompt":
        from .memory_review import stage_pending_memories
        stage_pending_memories(mgr, candidates)
        return [entry.name for entry in candidates]

    saved: List[str] = []
    for entry in candidates:
        try:
            mgr.save(entry)
            saved.append(entry.name)
            logger.info("auto-saved memory: %s (%s)", entry.name, entry.type)
        except Exception as exc:
            logger.warning("failed to auto-save memory %s: %s", entry.name, exc)

    return saved
