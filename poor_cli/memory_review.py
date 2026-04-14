"""MH4 in-loop memory review.

When ``review_mode="prompt"`` is set on ``auto_save_session_memories``, the
distilled candidates land in ``<memory_dir>/_pending/`` instead of the live
store. This module exposes the lifecycle: stage, list, accept, reject, edit.

Neovim surface (`:PoorCLIMemoryReview`) is a thin Lua wrapper on top of these
RPC-friendly functions. CLI equivalent: ``poor-cli memory review``. Both are
queued as follow-up; backend is what ships here.

Pending files are plain markdown with the same frontmatter shape as live
memories, so the existing `_parse_frontmatter` reader can consume them.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .exceptions import setup_logger
from .memory import MemoryEntry, MemoryManager, _parse_frontmatter

logger = setup_logger(__name__)

PENDING_DIRNAME = "_pending"


def pending_dir(manager: MemoryManager) -> Path:
    return manager._memory_dir / PENDING_DIRNAME  # type: ignore[reportPrivateUsage]


def stage_pending_memories(manager: MemoryManager, entries: Sequence[MemoryEntry]) -> List[Path]:
    """Write candidates to the pending directory instead of the live store."""
    target = pending_dir(manager)
    target.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for entry in entries:
        path = target / entry.filename
        try:
            path.write_text(entry.render_file(), encoding="utf-8")
            written.append(path)
        except Exception as exc:
            logger.warning("failed to stage pending memory %s: %s", entry.filename, exc)
    return written


def list_pending(manager: MemoryManager) -> List[MemoryEntry]:
    """Load all pending entries (does NOT mutate the live store)."""
    target = pending_dir(manager)
    if not target.is_dir():
        return []
    entries: List[MemoryEntry] = []
    for path in sorted(target.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("failed to read pending %s: %s", path.name, exc)
            continue
        meta, body = _parse_frontmatter(text)

        def _int(key: str, default: int = 0) -> int:
            try:
                return int(meta.get(key, default) or default)
            except (TypeError, ValueError):
                return default

        try:
            entry = MemoryEntry(
                name=meta.get("name", path.stem),
                description=meta.get("description", ""),
                type=meta.get("type", "project"),
                content=body,
                filename=path.name,
                created_at=meta.get("created_at", ""),
                updated_at=meta.get("updated_at", ""),
                source_session_id=meta.get("source_session_id", ""),
                source_turn_id=meta.get("source_turn_id", ""),
                source_message_hash=meta.get("source_message_hash", ""),
                extractor=meta.get("extractor", "unknown"),
                derivation_depth=_int("derivation_depth", 0),
                hit_count=_int("hit_count", 0),
                last_accessed_at=meta.get("last_accessed_at", ""),
            )
        except Exception as exc:
            logger.warning("failed to parse pending %s: %s", path.name, exc)
            continue
        entries.append(entry)
    return entries


def accept_pending(
    manager: MemoryManager,
    filename: str,
    *,
    edited_entry: Optional[MemoryEntry] = None,
) -> Optional[MemoryEntry]:
    """Move a pending entry into the live store. Optionally replace with edits."""
    src = pending_dir(manager) / filename
    if not src.is_file():
        return None
    if edited_entry is None:
        pending_entries = list_pending(manager)
        matching = next((e for e in pending_entries if e.filename == filename), None)
        if matching is None:
            return None
        entry = matching
    else:
        entry = edited_entry
    try:
        manager.save(entry)
    except Exception as exc:
        logger.warning("failed to accept pending %s: %s", filename, exc)
        return None
    try:
        src.unlink()
    except Exception as exc:
        logger.debug("failed to remove pending file %s: %s", filename, exc)
    return entry


def reject_pending(manager: MemoryManager, filename: str) -> bool:
    """Discard a pending entry without saving to the live store."""
    src = pending_dir(manager) / filename
    if not src.is_file():
        return False
    try:
        src.unlink()
        return True
    except Exception as exc:
        logger.warning("failed to reject pending %s: %s", filename, exc)
        return False


def clear_pending(manager: MemoryManager) -> int:
    """Delete every pending entry. Returns count removed."""
    target = pending_dir(manager)
    if not target.is_dir():
        return 0
    count = 0
    for path in target.glob("*.md"):
        try:
            path.unlink()
            count += 1
        except Exception as exc:
            logger.debug("failed to clear pending %s: %s", path.name, exc)
    return count


@dataclass
class ReviewSummary:
    accepted: List[str]
    rejected: List[str]

    def to_dict(self) -> dict:
        return {"accepted": list(self.accepted), "rejected": list(self.rejected)}


def bulk_accept(manager: MemoryManager) -> ReviewSummary:
    """Accept every pending entry as-is. Returns summary."""
    pending = list_pending(manager)
    summary = ReviewSummary(accepted=[], rejected=[])
    for entry in pending:
        result = accept_pending(manager, entry.filename)
        if result:
            summary.accepted.append(entry.name)
    return summary


def bulk_reject(manager: MemoryManager) -> ReviewSummary:
    """Reject every pending entry. Returns summary."""
    pending = list_pending(manager)
    summary = ReviewSummary(accepted=[], rejected=[])
    for entry in pending:
        if reject_pending(manager, entry.filename):
            summary.rejected.append(entry.name)
    return summary
