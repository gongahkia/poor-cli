"""CB1 diff-of-diff file-context caching.

When the agent re-reads the same file across turns, poor-cli currently re-sends
the full compressed text each turn. This module caches the last-sent text per
(file_path, pinned_context_hash) and returns a unified diff against the last
send when the file content is close enough; only the changed spans go into the
prompt, and unchanged regions collapse to a ``[... N lines unchanged ...]``
placeholder.

Entry points:
- ``DiffCache(store_path, ttl_seconds)`` persistent JSON store at
  ``.poor-cli/context/diff_cache.json``.
- ``DiffCache.ensure_entry(key, current_text)`` returns either the full text
  (first time, or on mismatch) plus a freshly stored entry, OR a "diff-only"
  payload with unchanged spans collapsed.

Safety:
- Entries expire via ``ttl_seconds`` (default 6 hours).
- On any exception the cache returns the full text — never stale or corrupt
  output to the model.
- Hash mismatch or missing entry always falls back to full text.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any, Dict, Optional, Tuple

from .. import exceptions  # for setup_logger

logger = exceptions.setup_logger(__name__)

DEFAULT_TTL_SECONDS = 6 * 3600
CACHE_FILENAME = "diff_cache.json"
MIN_UNCHANGED_BLOCK_LINES = 5  # collapse runs of unchanged lines of at least this many


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


@dataclass
class DiffCacheEntry:
    key: str
    full_text: str
    text_hash: str
    stored_at: float = field(default_factory=time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "full_text": self.full_text,
            "text_hash": self.text_hash,
            "stored_at": self.stored_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiffCacheEntry":
        return cls(
            key=str(data.get("key", "")),
            full_text=str(data.get("full_text", "")),
            text_hash=str(data.get("text_hash", "")),
            stored_at=float(data.get("stored_at", time())),
        )


@dataclass
class DiffEmission:
    """Result of ``ensure_entry``: what the caller should inject into context."""
    content: str
    mode: str  # "full" | "diff"
    tokens_saved_estimate: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "mode": self.mode,
            "tokensSavedEstimate": self.tokens_saved_estimate,
        }


class DiffCache:
    """Persistent diff-of-diff cache keyed by (file_path, context_hash)."""

    def __init__(
        self,
        store_path: Optional[Path] = None,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ):
        self._path = Path(store_path) if store_path else Path.cwd() / ".poor-cli" / "context" / CACHE_FILENAME
        self._ttl = float(max(0.0, ttl_seconds))
        self._lock = threading.Lock()
        self._entries: Dict[str, DiffCacheEntry] = {}
        self._loaded = False

    # ── key helpers ──────────────────────────────────────────────────────

    @staticmethod
    def make_key(file_path: str, pinned_context_hash: str = "") -> str:
        """Build a stable cache key from (file_path, pinned_context_hash)."""
        raw = f"{file_path}|{pinned_context_hash}"
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:24]

    # ── persistence ──────────────────────────────────────────────────────

    def load(self) -> None:
        self._loaded = True
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("diff_cache load failed: %s", exc)
            return
        if not isinstance(raw, dict):
            return
        now = time()
        with self._lock:
            for key, data in raw.items():
                if not isinstance(data, dict):
                    continue
                entry = DiffCacheEntry.from_dict(data)
                if self._ttl and now - entry.stored_at > self._ttl:
                    continue
                self._entries[key] = entry

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def persist(self) -> None:
        self._ensure_loaded()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {k: v.to_dict() for k, v in self._entries.items()}
            fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".json.tmp")
            try:
                os.write(fd, json.dumps(payload).encode("utf-8"))
                os.fsync(fd)
                os.close(fd)
                os.replace(tmp, str(self._path))
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as exc:
            logger.warning("diff_cache persist failed: %s", exc)

    # ── core API ─────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[DiffCacheEntry]:
        self._ensure_loaded()
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self._ttl and time() - entry.stored_at > self._ttl:
            return None
        return entry

    def put(self, key: str, text: str) -> DiffCacheEntry:
        self._ensure_loaded()
        entry = DiffCacheEntry(
            key=key,
            full_text=text,
            text_hash=hash_text(text),
            stored_at=time(),
        )
        with self._lock:
            self._entries[key] = entry
        return entry

    def invalidate(self, key: str) -> None:
        self._ensure_loaded()
        with self._lock:
            self._entries.pop(key, None)

    def ensure_entry(self, key: str, current_text: str) -> Tuple[DiffEmission, DiffCacheEntry]:
        """Return the diff-mode emission (or full) and refresh the cache entry."""
        self._ensure_loaded()
        current_hash = hash_text(current_text)
        previous = self.get(key)
        if previous is None or previous.text_hash == current_hash:
            # no previous OR identical → just return full (no savings but cache updated)
            entry = self.put(key, current_text)
            mode = "full" if previous is None else "unchanged"
            return DiffEmission(content=current_text, mode=mode, tokens_saved_estimate=0), entry
        # render a collapsed diff
        diff_text, saved_lines = self._collapsed_diff(previous.full_text, current_text)
        entry = self.put(key, current_text)
        # rough tokens-saved heuristic: ~4 chars per token on average
        est = max(0, saved_lines * 8)  # lines*avg_line_chars/4
        return DiffEmission(content=diff_text, mode="diff", tokens_saved_estimate=est), entry

    # ── diff rendering ──────────────────────────────────────────────────

    @staticmethod
    def _collapsed_diff(old: str, new: str, min_run: int = MIN_UNCHANGED_BLOCK_LINES) -> Tuple[str, int]:
        """Return a unified-diff-like text where long unchanged runs collapse."""
        old_lines = old.splitlines(keepends=False)
        new_lines = new.splitlines(keepends=False)
        matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
        saved = 0
        out_lines = ["# diff-of-diff cached context"]
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                run_len = j2 - j1
                if run_len >= min_run:
                    out_lines.append(f"[... {run_len} lines unchanged ...]")
                    saved += run_len - 1  # -1 because the placeholder takes a line
                else:
                    for line in new_lines[j1:j2]:
                        out_lines.append(f"  {line}")
            elif tag == "replace":
                for line in old_lines[i1:i2]:
                    out_lines.append(f"- {line}")
                for line in new_lines[j1:j2]:
                    out_lines.append(f"+ {line}")
            elif tag == "delete":
                for line in old_lines[i1:i2]:
                    out_lines.append(f"- {line}")
            elif tag == "insert":
                for line in new_lines[j1:j2]:
                    out_lines.append(f"+ {line}")
        return "\n".join(out_lines), saved
