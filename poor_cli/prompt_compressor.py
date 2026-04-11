"""Prompt compression middleware for poor-cli.

Reduces token count by removing redundant tokens before sending to the main model.
Supports two backends:
  - LLMLingua-2 (optional, ~110MB BERT model, best quality)
  - Heuristic compression (default, zero dependencies, fast)

Integrates with economy modes for compression aggressiveness.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

# content-type compression ratios (target ratio = fraction of tokens to KEEP)
COMPRESSION_RATIOS: Dict[str, float] = {
    "tool_output": 0.3,
    "file_content": 0.5,
    "conversation_history": 0.4,
    "system_prompt": 0.7,
}

# economy mode overrides
ECONOMY_RATIO_OVERRIDES: Dict[str, Dict[str, float]] = {
    "frugal": {
        "tool_output": 0.2,
        "file_content": 0.35,
        "conversation_history": 0.3,
        "system_prompt": 0.5,
    },
    "balanced": {
        "tool_output": 0.3,
        "file_content": 0.5,
        "conversation_history": 0.4,
        "system_prompt": 0.7,
    },
    "quality": {
        "tool_output": 0.6,
        "file_content": 0.8,
        "conversation_history": 0.7,
        "system_prompt": 0.9,
    },
}

LATENCY_BUDGET_MS = 100 # max ms for compression before we skip

# preserve patterns — regex patterns for content that must survive compression
_CODE_FENCE_RE = re.compile(r"(```[\w]*\n.*?```)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"(`[^`\n]+`)")
_FILE_PATH_RE = re.compile(r"(?:^|[\s\"'])((?:[\w.\-]+/)*[\w.\-]+\.\w{1,8})", re.MULTILINE)
_UNIX_PATH_RE = re.compile(r"(?:/[\w.\-]+){2,}")
_ERROR_LINE_RE = re.compile(
    r"^.*(?:Error|Exception|Traceback|FAILED|panic|FATAL|WARNING|error\[).*$",
    re.MULTILINE | re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+")
_VAR_ASSIGN_RE = re.compile(r"^\s*(?:(?:let|const|var|val)\s+)?\w+\s*[:=]", re.MULTILINE)

# heuristic compression patterns
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_FILLER_RE = re.compile(
    r"\b(?:please note that|it is important to note that|as you can see|"
    r"in other words|basically|essentially|actually|obviously|"
    r"as mentioned (?:earlier|above|before|previously)|"
    r"for your reference|for your information|"
    r"it should be noted that|it is worth mentioning that|"
    r"as we discussed|going forward)\b",
    re.IGNORECASE,
)
_REPEATED_PUNCT_RE = re.compile(r"([!?.])\1{2,}")
_LICENSE_HEADER_RE = re.compile(
    r"(?:^|\n)(?:#|//|/\*|\*) (?:Copyright|License|SPDX|MIT|Apache|GNU|BSD).*?(?:\n(?:#|//|\*/).*)*",
    re.IGNORECASE,
)
_IMPORT_BLOCK_RE = re.compile(
    r"(?:^(?:import |from \S+ import |require\(|use |#include ).*\n){4,}",
    re.MULTILINE,
)
_REPEATED_SIMILAR_RE = re.compile(r"((?:^.{20,80}\n))\1{2,}", re.MULTILINE)


@dataclass
class CompressionResult:
    """Result of a compression operation."""
    original_text: str
    compressed_text: str
    original_tokens: int # estimated
    compressed_tokens: int # estimated
    ratio: float # compressed / original
    elapsed_ms: float
    backend: str # "llmlingua" or "heuristic"
    skipped: bool = False # true if compression was skipped (latency/error)
    preserved_count: int = 0 # number of preserved regions


@dataclass
class CompressionStats:
    """Accumulated compression statistics."""
    total_compressions: int = 0
    total_tokens_before: int = 0
    total_tokens_after: int = 0
    total_time_ms: float = 0.0
    skipped_count: int = 0
    backend_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def tokens_saved(self) -> int:
        return max(0, self.total_tokens_before - self.total_tokens_after)

    @property
    def avg_ratio(self) -> float:
        if self.total_tokens_before == 0:
            return 1.0
        return self.total_tokens_after / self.total_tokens_before

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_compressions": self.total_compressions,
            "tokens_saved": self.tokens_saved,
            "avg_ratio": round(self.avg_ratio, 3),
            "total_time_ms": round(self.total_time_ms, 1),
            "skipped": self.skipped_count,
            "backends": dict(self.backend_counts),
        }


class PromptCompressor:
    """Prompt compression middleware.

    Sits between poor-cli and the provider, compressing text to reduce token usage.
    LLMLingua-2 model is lazy-loaded on first use.
    Falls back to heuristic compression if LLMLingua is not installed.
    """

    def __init__(
        self,
        model_name: str = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
        economy_preset: str = "balanced",
        force_heuristic: bool = False,
    ):
        self._model_name = model_name
        self._economy_preset = economy_preset
        self._force_heuristic = force_heuristic
        self._llmlingua = None # lazy loaded
        self._llmlingua_available: Optional[bool] = None
        self._stats = CompressionStats()
        self._chars_per_token = 4

    @property
    def stats(self) -> CompressionStats:
        return self._stats

    def set_economy_preset(self, preset: str) -> None:
        if preset in ECONOMY_RATIO_OVERRIDES:
            self._economy_preset = preset

    def get_ratio(self, content_type: str) -> float:
        """Get compression ratio for a content type under current economy preset."""
        overrides = ECONOMY_RATIO_OVERRIDES.get(self._economy_preset, {})
        return overrides.get(content_type, COMPRESSION_RATIOS.get(content_type, 0.5))

    def compress(
        self,
        text: str,
        content_type: str = "tool_output",
        ratio: Optional[float] = None,
        preserve_patterns: Optional[List[re.Pattern]] = None,
    ) -> CompressionResult:
        """Compress text to target ratio, preserving critical patterns.

        Args:
            text: text to compress
            content_type: type key for ratio lookup
            ratio: override ratio (0-1, fraction to keep). None = use content_type default.
            preserve_patterns: additional regex patterns whose matches must survive

        Returns:
            CompressionResult with compressed text and metrics
        """
        if not text or not text.strip():
            return self._empty_result(text)
        target_ratio = ratio if ratio is not None else self.get_ratio(content_type)
        if target_ratio >= 0.95: # near 1.0 = no compression
            return self._skip_result(text, "ratio >= 0.95")
        start = time.monotonic()
        preserved, stripped = self._extract_preserved(text, preserve_patterns)
        # try llmlingua first, fall back to heuristic
        backend = "heuristic"
        if not self._force_heuristic and self._check_llmlingua():
            try:
                compressed = self._compress_llmlingua(stripped, target_ratio)
                backend = "llmlingua"
            except Exception as exc:
                logger.warning("llmlingua compression failed, falling back to heuristic: %s", exc)
                compressed = self._compress_heuristic(stripped, target_ratio)
        else:
            compressed = self._compress_heuristic(stripped, target_ratio)
        result_text = self._restore_preserved(compressed, preserved)
        elapsed = (time.monotonic() - start) * 1000
        if elapsed > LATENCY_BUDGET_MS:
            logger.warning("compression took %.1fms (budget %dms), returning original", elapsed, LATENCY_BUDGET_MS)
            self._stats.skipped_count += 1
            return self._skip_result(text, f"latency {elapsed:.0f}ms")
        orig_tokens = len(text) // self._chars_per_token
        comp_tokens = len(result_text) // self._chars_per_token
        actual_ratio = comp_tokens / max(orig_tokens, 1)
        self._stats.total_compressions += 1
        self._stats.total_tokens_before += orig_tokens
        self._stats.total_tokens_after += comp_tokens
        self._stats.total_time_ms += elapsed
        self._stats.backend_counts[backend] = self._stats.backend_counts.get(backend, 0) + 1
        return CompressionResult(
            original_text=text,
            compressed_text=result_text,
            original_tokens=orig_tokens,
            compressed_tokens=comp_tokens,
            ratio=actual_ratio,
            elapsed_ms=elapsed,
            backend=backend,
            preserved_count=len(preserved),
        )

    def compress_message_list(
        self,
        messages: List[Dict[str, Any]],
        current_user_index: int = -1,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Compress a list of chat messages, skipping the current user message.

        Args:
            messages: list of {"role": ..., "content": ...} dicts
            current_user_index: index of current user message to skip (-1 = last user)

        Returns:
            (compressed_messages, total_tokens_saved)
        """
        if not messages:
            return messages, 0
        if current_user_index == -1: # find last user message
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    current_user_index = i
                    break
        total_saved = 0
        result = []
        for i, msg in enumerate(messages):
            if i == current_user_index: # never compress current user message
                result.append(msg)
                continue
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not isinstance(content, str) or len(content) < 100: # too short to bother
                result.append(msg)
                continue
            content_type = self._infer_content_type(role, content)
            cr = self.compress(content, content_type=content_type)
            if not cr.skipped:
                total_saved += cr.original_tokens - cr.compressed_tokens
                result.append({**msg, "content": cr.compressed_text})
            else:
                result.append(msg)
        return result, total_saved

    # ── LLMLingua integration ────────────────────────────────────────

    def _check_llmlingua(self) -> bool:
        """Check if llmlingua is available (cached)."""
        if self._llmlingua_available is not None:
            return self._llmlingua_available
        try:
            import llmlingua # noqa: F401
            self._llmlingua_available = True
        except ImportError:
            self._llmlingua_available = False
            logger.debug("llmlingua not installed, using heuristic compression")
        return self._llmlingua_available

    def _load_llmlingua(self) -> Any:
        """Lazy-load the LLMLingua model."""
        if self._llmlingua is not None:
            return self._llmlingua
        from llmlingua import PromptCompressor as LLMCompressor
        self._llmlingua = LLMCompressor(model_name=self._model_name, use_llmlingua2=True)
        logger.info("loaded llmlingua model: %s", self._model_name)
        return self._llmlingua

    def _compress_llmlingua(self, text: str, ratio: float) -> str:
        """Compress using LLMLingua-2."""
        compressor = self._load_llmlingua()
        result = compressor.compress_prompt(text, rate=ratio, force_tokens=["\n", ".", ":", "/"])
        return result.get("compressed_prompt", text)

    # ── Heuristic compression ────────────────────────────────────────

    def _compress_heuristic(self, text: str, ratio: float) -> str:
        """Compress using rule-based heuristics.

        Applies increasingly aggressive transforms until target ratio is met.
        """
        original_len = len(text)
        target_len = int(original_len * ratio)
        result = text
        # stage 1: whitespace normalization (always applied)
        result = _MULTI_BLANK_RE.sub("\n\n", result)
        result = _MULTI_SPACE_RE.sub(" ", result)
        result = _REPEATED_PUNCT_RE.sub(r"\1", result)
        if len(result) <= target_len:
            return result.strip()
        # stage 2: remove filler phrases
        result = _FILLER_RE.sub("", result)
        result = re.sub(r"  +", " ", result) # clean up double spaces left behind
        if len(result) <= target_len:
            return result.strip()
        # stage 3: collapse license headers and large import blocks
        result = _LICENSE_HEADER_RE.sub("\n[license header removed]\n", result)
        result = self._collapse_imports(result)
        if len(result) <= target_len:
            return result.strip()
        # stage 4: collapse repeated similar lines
        result = _REPEATED_SIMILAR_RE.sub(lambda m: m.group(1) + f"[... {m.group(0).count(chr(10))-1} similar lines ...]\n", result)
        if len(result) <= target_len:
            return result.strip()
        # stage 5: aggressive — truncate long lines, remove empty-ish lines
        lines = result.splitlines()
        kept = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if len(stripped) > 200:
                kept.append(stripped[:197] + "...")
            else:
                kept.append(line)
        result = "\n".join(kept)
        if len(result) <= target_len:
            return result.strip()
        # stage 6: hard truncate to target length
        if len(result) > target_len:
            cut = result[:target_len].rsplit("\n", 1)[0] # cut at last newline
            result = cut + f"\n[... truncated, {len(text) - len(cut)} chars removed ...]"
        return result.strip()

    def _collapse_imports(self, text: str) -> str:
        """Collapse large import blocks to summary."""
        def _replacer(m: re.Match) -> str:
            lines = m.group(0).strip().splitlines()
            if len(lines) <= 3:
                return m.group(0)
            first = lines[0].strip()
            return f"{first}\n[... {len(lines)-1} more imports ...]\n"
        return _IMPORT_BLOCK_RE.sub(_replacer, text)

    # ── Preserve/restore ─────────────────────────────────────────────

    def _extract_preserved(
        self,
        text: str,
        extra_patterns: Optional[List[re.Pattern]] = None,
    ) -> Tuple[List[Tuple[str, str]], str]:
        """Extract regions that must be preserved, replacing with placeholders.

        Returns:
            (list of (placeholder, original_text), text with placeholders)
        """
        preserved: List[Tuple[str, str]] = []
        counter = 0
        patterns = [_CODE_FENCE_RE, _ERROR_LINE_RE, _UNIX_PATH_RE, _URL_RE]
        if extra_patterns:
            patterns.extend(extra_patterns)

        def _replace(m: re.Match) -> str:
            nonlocal counter
            placeholder = f"__PRESERVE_{counter}__"
            preserved.append((placeholder, m.group(0)))
            counter += 1
            return placeholder

        result = text
        for pattern in patterns:
            result = pattern.sub(_replace, result)
        return preserved, result

    def _restore_preserved(self, text: str, preserved: List[Tuple[str, str]]) -> str:
        """Restore preserved regions from placeholders."""
        result = text
        for placeholder, original in preserved:
            result = result.replace(placeholder, original, 1)
        return result

    # ── Helpers ───────────────────────────────────────────────────────

    def _infer_content_type(self, role: str, content: str) -> str:
        """Infer content type from message role and content."""
        if role in ("tool", "function"):
            return "tool_output"
        if role == "system":
            return "system_prompt"
        if "```" in content or _FILE_PATH_RE.search(content):
            return "file_content"
        return "conversation_history"

    def _empty_result(self, text: str) -> CompressionResult:
        return CompressionResult(
            original_text=text, compressed_text=text,
            original_tokens=0, compressed_tokens=0,
            ratio=1.0, elapsed_ms=0.0, backend="none", skipped=True,
        )

    def _skip_result(self, text: str, reason: str = "") -> CompressionResult:
        tokens = len(text) // self._chars_per_token
        return CompressionResult(
            original_text=text, compressed_text=text,
            original_tokens=tokens, compressed_tokens=tokens,
            ratio=1.0, elapsed_ms=0.0, backend="skipped",
            skipped=True,
        )
