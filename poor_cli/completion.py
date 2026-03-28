"""
Inline code completion engine for poor-cli.

Provides fill-in-middle (FIM) completions using the configured provider.
Designed for low-latency editor integration via JSON-RPC.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger
from .prompts import (
    FIM_TEMPLATE,
    FIM_TEMPLATE_MINIMAL,
    FIM_CODESTRAL,
    FIM_STARCODER,
    FIM_DEEPSEEK,
)

logger = setup_logger(__name__)

DEBOUNCE_MS = 300
MAX_CONTEXT_CHARS = 4000
MAX_COMPLETION_TOKENS = 256


@dataclass
class CompletionRequest:
    """Request for inline code completion."""
    file_path: str
    line: int
    column: int
    prefix: str # code before cursor
    suffix: str # code after cursor
    language: str = ""
    max_tokens: int = MAX_COMPLETION_TOKENS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filePath": self.file_path,
            "line": self.line,
            "column": self.column,
            "prefix": self.prefix[-MAX_CONTEXT_CHARS:],
            "suffix": self.suffix[:MAX_CONTEXT_CHARS],
            "language": self.language,
            "maxTokens": self.max_tokens,
        }


@dataclass
class CompletionResult:
    """Result of inline completion."""
    text: str
    finish_reason: str = ""
    latency_ms: float = 0
    model: str = ""
    cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "finishReason": self.finish_reason,
            "latencyMs": self.latency_ms,
            "model": self.model,
            "cached": self.cached,
        }


class CompletionEngine:
    """
    Low-latency FIM completion engine.

    Uses the configured provider's cheap/fast model tier for
    inline completions. Includes result caching for repeat requests.
    """

    def __init__(self):
        self._cache: Dict[str, CompletionResult] = {}
        self._cache_max = 100
        self._last_request_time: float = 0

    async def complete(
        self,
        request: CompletionRequest,
        provider: Any = None,
    ) -> CompletionResult:
        """Generate a FIM completion."""
        # debounce: skip if too soon after last request
        now = time.time()
        elapsed_ms = (now - self._last_request_time) * 1000
        if elapsed_ms < DEBOUNCE_MS:
            return CompletionResult(text="", finish_reason="debounced")
        self._last_request_time = now

        # check cache
        cache_key = f"{request.file_path}:{request.line}:{request.column}:{hash(request.prefix[-200:])}"
        if cache_key in self._cache:
            result = self._cache[cache_key]
            result.cached = True
            return result

        if not provider:
            return CompletionResult(text="", finish_reason="no_provider")

        # build prompt
        prompt = self._build_prompt(request, provider)
        start = time.time()

        try:
            # use non-streaming for lowest latency
            response = await provider.send_message(prompt)
            text = (response.content or "").strip()
            # clean up: remove markdown fences if present
            text = _strip_markdown_fences(text)
            latency = (time.time() - start) * 1000

            result = CompletionResult(
                text=text,
                finish_reason=response.finish_reason or "stop",
                latency_ms=round(latency, 1),
                model=getattr(provider, "model_name", ""),
            )

            # cache result
            if len(self._cache) >= self._cache_max:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[cache_key] = result
            return result

        except Exception as exc:
            logger.debug("completion failed: %s", exc)
            return CompletionResult(text="", finish_reason=f"error: {exc}")

    def _build_prompt(self, request: CompletionRequest, provider: Any) -> str:
        """Build FIM prompt based on provider type."""
        prefix = request.prefix[-MAX_CONTEXT_CHARS:]
        suffix = request.suffix[:MAX_CONTEXT_CHARS]
        lang = request.language or _detect_language(request.file_path)
        fname = Path(request.file_path).name

        provider_name = getattr(provider, "provider_name", "")

        if "codestral" in provider_name.lower() or "mistral" in provider_name.lower():
            return FIM_CODESTRAL.format(code_before=prefix, code_after=suffix)
        if "starcoder" in provider_name.lower():
            return FIM_STARCODER.format(code_before=prefix, code_after=suffix)
        if "deepseek" in provider_name.lower():
            return FIM_DEEPSEEK.format(code_before=prefix, code_after=suffix)

        # generic FIM template
        return FIM_TEMPLATE_MINIMAL.format(code_before=prefix, code_after=suffix)

    def clear_cache(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from completion output."""
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text


def _detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".rs": "rust", ".go": "go", ".java": "java", ".c": "c",
        ".cpp": "cpp", ".rb": "ruby", ".php": "php",
    }
    return ext_map.get(Path(file_path).suffix.lower(), "")
