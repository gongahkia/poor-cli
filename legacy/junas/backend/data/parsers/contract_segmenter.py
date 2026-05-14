from __future__ import annotations

import re
from typing import Any

SECTION_PATTERN = re.compile(
    r"(?:^|\n\n)(?=(?:"
    r"(?:Section|SECTION|Article|ARTICLE)\s+\w+"
    r"|\d+\.\d*\s"
    r"|[A-Z][A-Z\s]{3,}(?:\.|:)"
    r"))",
    re.MULTILINE,
)

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s*")


def _trimmed_span(text: str, start: int, end: int) -> tuple[str, int, int]:
    raw = text[start:end]
    if not raw:
        return "", start, start
    left_trim = len(raw) - len(raw.lstrip())
    right_trim = len(raw) - len(raw.rstrip())
    trimmed = raw.strip()
    return trimmed, start + left_trim, end - right_trim


def segment_contract(text: str) -> list[dict[str, Any]]:
    """Split raw contract text into clause-like segments."""
    value = str(text or "")
    if not value.strip():
        return []

    boundaries = [match.start() for match in SECTION_PATTERN.finditer(value)]
    if not boundaries:
        return _fallback_split(value)

    if boundaries[0] != 0:
        boundaries.insert(0, 0)
    boundaries = sorted(set(boundaries))
    boundaries.append(len(value))

    segments: list[dict[str, Any]] = []
    for index in range(len(boundaries) - 1):
        start = boundaries[index]
        end = boundaries[index + 1]
        segment_text, segment_start, segment_end = _trimmed_span(value, start, end)
        if not segment_text or len(segment_text) <= 20:
            continue
        segments.append(
            {
                "index": len(segments),
                "text": segment_text,
                "start": segment_start,
                "end": segment_end,
            }
        )

    if not segments:
        return _fallback_split(value)
    return segments


def _fallback_split(text: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    cursor = 0
    for chunk in text.split("\n\n"):
        start = text.find(chunk, cursor)
        if start < 0:
            start = cursor
        end = start + len(chunk)
        cursor = end + 2
        segment_text, segment_start, segment_end = _trimmed_span(text, start, end)
        if not segment_text:
            continue
        segments.append(
            {
                "index": len(segments),
                "text": segment_text,
                "start": segment_start,
                "end": segment_end,
            }
        )
    return segments


def split_sentences(text: str, min_length: int = 10) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    sentences = SENTENCE_SPLIT_PATTERN.split(value)
    return [sentence.strip() for sentence in sentences if sentence.strip() and len(sentence.strip()) >= min_length]
