"""selective failure amnesia — extract lessons from failed tool calls, prune traces."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Dict, List, Optional, Tuple

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)

_FAILURE_RE = re.compile(
    r"\b(error|exception|traceback|failed|failure|permission denied|not found|timed out|timeout|exit code [1-9])\b",
    re.IGNORECASE,
)
_EXIT_CODE_RE = re.compile(r"exit code\s+(\d+)", re.IGNORECASE)
_USER_REF_RE = re.compile(
    r"\b(that error|the error|earlier failure|previous error|about that|the traceback)\b",
    re.IGNORECASE,
)
AMNESIA_MARKER = "[failure-amnesia]"
MIN_TRACE_TOKENS = 60  # only amnesia traces >= this size (chars/4)


@dataclass(frozen=True)
class FailureLesson:
    """compressed lesson from a failed tool call."""
    failed_action: str
    error_type: str
    lesson: str
    original_tokens: int
    lesson_tokens: int

    @property
    def tokens_saved(self) -> int:
        return max(0, self.original_tokens - self.lesson_tokens)

    def to_marker(self) -> str:
        parts = [AMNESIA_MARKER]
        if self.failed_action:
            parts.append(self.failed_action)
        if self.error_type:
            parts.append(f"({self.error_type})")
        parts.append(f"— {self.lesson}")
        return " ".join(parts)


@dataclass
class TrackedFailure:
    """a failure being tracked for potential amnesia."""
    index: int
    tool_name: str
    content: str
    token_count: int
    resolved: bool = False
    user_referenced: bool = False
    lesson: Optional[FailureLesson] = None


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _extract_text(message: Dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                parts.append(str(p.get("text", "")))
        return "\n".join(p for p in parts if p)
    return str(content or "")


def _normalized_role(message: Dict[str, Any]) -> str:
    return str(message.get("role", "unknown") or "unknown").strip().lower()


def _tool_name(message: Dict[str, Any]) -> str:
    return str(
        message.get("name")
        or message.get("tool_name")
        or message.get("tool_call_id")
        or "tool"
    ).strip()


class FailureDetector:
    """detects failed tool calls in conversation history."""

    def is_failure(self, message: Dict[str, Any]) -> bool:
        role = _normalized_role(message)
        if role not in {"tool", "function"}:
            return False
        text = _extract_text(message)
        if _EXIT_CODE_RE.search(text):
            match = _EXIT_CODE_RE.search(text)
            if match and int(match.group(1)) != 0:
                return True
        return bool(_FAILURE_RE.search(text))

    def is_large_enough(self, message: Dict[str, Any]) -> bool:
        """only amnesia traces above threshold — extraction cost must be worth it."""
        return _estimate_tokens(_extract_text(message)) >= MIN_TRACE_TOKENS

    def find_failures(
        self, history: List[Dict[str, Any]]
    ) -> List[TrackedFailure]:
        failures: List[TrackedFailure] = []
        for i, msg in enumerate(history):
            if self.is_failure(msg) and self.is_large_enough(msg):
                text = _extract_text(msg)
                failures.append(TrackedFailure(
                    index=i,
                    tool_name=_tool_name(msg),
                    content=text,
                    token_count=_estimate_tokens(text),
                ))
        return failures


ExtractionCallback = Callable[[str], Awaitable[str]]


class LessonExtractor:
    """extracts concise lessons from failure traces via a small model call."""

    EXTRACTION_PROMPT = "Extract a 1-2 sentence lesson from this failure:\n"  # ~14 tokens

    def build_prompt(self, failure_trace: str) -> str:
        """prompt must be < 100 tokens total including summary."""
        truncated = failure_trace[:300]  # keep extraction input small
        return f"{self.EXTRACTION_PROMPT}{truncated}"

    async def extract(
        self,
        failure: TrackedFailure,
        callback: Optional[ExtractionCallback] = None,
    ) -> FailureLesson:
        """extract lesson — uses callback for model call, falls back to heuristic."""
        error_type = self._detect_error_type(failure.content)
        if callback:
            try:
                prompt = self.build_prompt(failure.content)
                lesson_text = await callback(prompt)
                lesson_text = lesson_text.strip()[:200]
            except Exception as exc:
                logger.warning("lesson extraction callback failed: %s", exc)
                lesson_text = self._heuristic_lesson(failure)
        else:
            lesson_text = self._heuristic_lesson(failure)
        lesson = FailureLesson(
            failed_action=f"{failure.tool_name} call",
            error_type=error_type,
            lesson=lesson_text,
            original_tokens=failure.token_count,
            lesson_tokens=_estimate_tokens(lesson_text) + 10,  # marker overhead
        )
        return lesson

    def _detect_error_type(self, text: str) -> str:
        patterns = [
            (r"(\w+Error)", 1),
            (r"(\w+Exception)", 1),
            (r"exit code\s+(\d+)", 0),
            (r"(permission denied)", 0),
            (r"(not found)", 0),
            (r"(timed? ?out)", 0),
        ]
        for pat, group in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(group)
        return "unknown"

    def _heuristic_lesson(self, failure: TrackedFailure) -> str:
        """fast fallback: first meaningful error line."""
        lines = failure.content.strip().splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped and _FAILURE_RE.search(stripped):
                return stripped[:150]
        return lines[0][:150] if lines else "tool call failed"


class FailureAmnesia:
    """meta-controller: detect failures, extract lessons, prune traces."""

    def __init__(self) -> None:
        self._detector = FailureDetector()
        self._extractor = LessonExtractor()
        self._total_tokens_saved: int = 0

    @property
    def tokens_saved(self) -> int:
        return self._total_tokens_saved

    async def process_history(
        self,
        history: List[Dict[str, Any]],
        *,
        extraction_callback: Optional[ExtractionCallback] = None,
        trigger: str = "compact",
    ) -> AmnesiaResult:
        """scan history, extract lessons from resolved failures, prune traces.

        safety:
          - never prune the most-recent failure (last in list)
          - never prune unresolved failures (no success after)
          - never prune failures the user explicitly referenced
        """
        failures = self._detector.find_failures(history)
        if not failures:
            return AmnesiaResult(history=history, lessons=[], tokens_saved=0, failures_pruned=0)
        self._mark_resolved(failures, history)
        self._mark_user_referenced(failures, history)
        prunable = [
            f for f in failures
            if f.resolved and not f.user_referenced
        ]
        # never prune the most-recent failure if it's still potentially active
        last_failure = failures[-1]
        if not last_failure.resolved and prunable and prunable[-1].index == last_failure.index:
            prunable = prunable[:-1]
        lessons: List[FailureLesson] = []
        for fail in prunable:
            lesson = await self._extractor.extract(fail, extraction_callback)
            fail.lesson = lesson
            lessons.append(lesson)
        new_history = list(history)
        tokens_saved = 0
        for fail in sorted(prunable, key=lambda f: f.index, reverse=True):
            if fail.lesson:
                marker = fail.lesson.to_marker()
                new_history[fail.index] = {
                    "role": _normalized_role(history[fail.index]),
                    "content": marker,
                    "parts": [{"text": marker}],
                    "metadata": {"failure_amnesia": True, "original_tokens": fail.token_count},
                }
                tokens_saved += fail.lesson.tokens_saved
        self._total_tokens_saved += tokens_saved
        return AmnesiaResult(
            history=new_history,
            lessons=lessons,
            tokens_saved=tokens_saved,
            failures_pruned=len(prunable),
        )

    def _mark_resolved(
        self,
        failures: List[TrackedFailure],
        history: List[Dict[str, Any]],
    ) -> None:
        """a failure is resolved if a subsequent non-failure tool message from same tool exists,
        or if a subsequent assistant message acknowledges success."""
        for fail in failures:
            for j in range(fail.index + 1, len(history)):
                msg = history[j]
                role = _normalized_role(msg)
                if role in {"tool", "function"}:
                    name = _tool_name(msg)
                    if name == fail.tool_name and not self._detector.is_failure(msg):
                        fail.resolved = True
                        break
                elif role in {"assistant", "model"}:
                    text = _extract_text(msg).lower()
                    if any(w in text for w in ("fixed", "resolved", "succeeded", "works now", "success")):
                        fail.resolved = True
                        break

    def _mark_user_referenced(
        self,
        failures: List[TrackedFailure],
        history: List[Dict[str, Any]],
    ) -> None:
        """check if user explicitly referenced a failure after it occurred."""
        for fail in failures:
            for j in range(fail.index + 1, len(history)):
                msg = history[j]
                if _normalized_role(msg) == "user":
                    if _USER_REF_RE.search(_extract_text(msg)):
                        fail.user_referenced = True
                        break


@dataclass(frozen=True)
class AmnesiaResult:
    """result of a failure amnesia pass."""
    history: List[Dict[str, Any]]
    lessons: List[FailureLesson]
    tokens_saved: int
    failures_pruned: int
