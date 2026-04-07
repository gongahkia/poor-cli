"""Conversation context compression via extractive and LLM-based summarization."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

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
_LLM_SUMMARIZE_PROMPT = (
    "Summarize the following conversation history into a concise context block. "
    "Preserve: (1) user intents and goals, (2) key decisions made, (3) files modified, "
    "(4) tools used, (5) any unresolved issues. Be factual and terse. "
    "Output only the summary, no preamble.\n\n"
)
_LLM_SUMMARY_MAX_INPUT_CHARS = 60000 # cap input to avoid blowing context on the summarizer call


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

    async def compress_with_llm(
        self,
        history: List[Dict[str, Any]],
        config: Any,
        provider: Any,
    ) -> List[Dict[str, Any]]:
        """Compress using LLM summarization, falling back to extractive on failure."""
        if not self.should_compress(history, config):
            return history
        split = len(history) - getattr(config, "preserve_recent_turns", 8)
        if split <= 0:
            return history
        old_turns = history[:split]
        recent_turns = history[split:]
        try:
            summary_text = await self._llm_summarize(old_turns, provider)
        except Exception as e:
            logger.warning("LLM compression failed, falling back to extractive: %s", e)
            summary_text = self._summarize_turns(old_turns)
        summary_msg: Dict[str, Any] = {
            "role": "user",
            "content": f"[COMPRESSED CONTEXT]\n{summary_text}\n({len(old_turns)} turns compressed via LLM)",
        }
        compressed = [summary_msg] + recent_turns
        logger.info(
            "LLM-compressed %d old turns, kept %d recent (ratio %.2f)",
            len(old_turns), len(recent_turns),
            len(summary_text) / max(1, sum(len(t.get("content", "")) for t in old_turns)),
        )
        return compressed

    async def _llm_summarize(self, turns: List[Dict[str, Any]], provider: Any) -> str:
        """Send old turns to LLM for summarization."""
        conversation_text = []
        total_chars = 0
        for turn in turns:
            content = str(turn.get("content", ""))
            role = turn.get("role", "unknown")
            entry = f"[{role}]: {content}"
            if total_chars + len(entry) > _LLM_SUMMARY_MAX_INPUT_CHARS:
                conversation_text.append(f"... ({len(turns) - len(conversation_text)} more turns omitted)")
                break
            conversation_text.append(entry)
            total_chars += len(entry)
        full_prompt = _LLM_SUMMARIZE_PROMPT + "\n".join(conversation_text)
        response = await provider.send_message(full_prompt)
        return response.content.strip() if response.content else self._summarize_turns(turns)

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
