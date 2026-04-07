"""Conversation context compression via extractive summarization."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from .config import ContextCompressionConfig
from .exceptions import setup_logger

logger = setup_logger(__name__)

_TOOL_PATTERNS: List[re.Pattern] = [ # common tool/action indicators
    re.compile(r'\b(read_file|write_file|edit_file|bash|search|grep|glob)\b', re.I),
    re.compile(r'\b(git\s+\w+)\b', re.I),
    re.compile(r'\b(npm|pip|cargo|make)\s+\w+', re.I),
]
_FILE_PATH_RE = re.compile(r'(?:/[\w.\-]+){2,}') # unix-style paths
_DECISION_RE = re.compile( # phrases signalling a decision or outcome
    r'(?:decided|chosen|approved|rejected|confirmed|created|deleted|modified|fixed|resolved)',
    re.I,
)


class ContextCompressor:
    """Compresses conversation history by extractively summarizing old turns."""

    def should_compress(self, history: List[Dict[str, Any]], config: Any) -> bool:
        try:
            if not getattr(config, "enabled", False):
                return False
            threshold = getattr(config, "compress_after_turns", 20)
            return len(history) > threshold
        except (AttributeError, TypeError):
            return False

    def compress(self, history: List[Dict[str, Any]], config: Any) -> List[Dict[str, Any]]:
        if not self.should_compress(history, config):
            return history
        split = len(history) - getattr(config, "preserve_recent_turns", 8)
        if split <= 0: # nothing old enough to compress
            return history
        old_turns = history[:split]
        recent_turns = history[split:]
        summary_text = self._summarize_turns(old_turns)
        summary_msg: Dict[str, Any] = {
            "role": "user", # use "user" role for provider compatibility (Anthropic rejects mid-conversation "system")
            "content": summary_text,
        }
        compressed = [summary_msg] + recent_turns
        logger.info(
            "compressed %d old turns into summary, kept %d recent (ratio %.2f)",
            len(old_turns), len(recent_turns),
            len(summary_text) / max(1, sum(len(t.get("content", "")) for t in old_turns)),
        )
        return compressed

    def _summarize_turns(self, turns: List[Dict[str, Any]]) -> str:
        tools_used: Set[str] = set()
        files_seen: Set[str] = set()
        decisions: List[str] = []
        user_intents: List[str] = []
        for turn in turns:
            content = turn.get("content", "")
            role = turn.get("role", "")
            if not content:
                continue
            for pat in _TOOL_PATTERNS: # extract tool names
                for m in pat.finditer(content):
                    tools_used.add(m.group(0).strip().lower())
            for m in _FILE_PATH_RE.finditer(content): # extract file paths
                files_seen.add(m.group(0))
            for m in _DECISION_RE.finditer(content): # extract decision sentences
                start = max(0, m.start() - 60)
                end = min(len(content), m.end() + 60)
                snippet = content[start:end].replace("\n", " ").strip()
                decisions.append(snippet)
            if role == "user": # capture user intent (first 120 chars)
                user_intents.append(content[:120].replace("\n", " ").strip())
        parts = ["[COMPRESSED CONTEXT]"]
        if user_intents:
            parts.append("user intents: " + "; ".join(dict.fromkeys(user_intents[:10]))) # dedup, cap at 10
        if tools_used:
            parts.append("tools used: " + ", ".join(sorted(tools_used)))
        if files_seen:
            parts.append("files touched: " + ", ".join(sorted(files_seen)[:20])) # cap at 20 paths
        if decisions:
            unique = list(dict.fromkeys(decisions[:15])) # dedup, cap at 15
            parts.append("key decisions/actions: " + "; ".join(unique))
        parts.append(f"({len(turns)} turns compressed)")
        return "\n".join(parts)
