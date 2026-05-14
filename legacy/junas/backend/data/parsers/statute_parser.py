from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Iterator

ORS_REF_PATTERN = re.compile(r"\bORS\s+(\d+[A-Z]?\.\d+)\b")
AMENDMENT_PATTERN = re.compile(r"\[(?:Amended|Formerly|Repealed|Renumbered).*?\]\s*$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class StatuteSection:
    number: str
    name: str
    chapter_number: str
    edition: int
    kind: str
    text_html: str
    text_plain: str
    amendment_history: str
    cross_references: list[str]

    def to_document(self) -> dict[str, object]:
        return asdict(self)


def strip_html(value: str) -> str:
    if not value:
        return ""
    text = HTML_TAG_RE.sub(" ", value)
    text = unescape(text)
    return WHITESPACE_RE.sub(" ", text).strip()


def extract_cross_references(text_plain: str, section_number: str) -> list[str]:
    refs = sorted(set(ORS_REF_PATTERN.findall(text_plain)))
    return [ref for ref in refs if ref != section_number]


def extract_amendment_history(text_plain: str) -> str:
    match = AMENDMENT_PATTERN.search(text_plain)
    return match.group(0).strip() if match else ""


def parse_ors_line(line: str) -> StatuteSection:
    record = json.loads(line)
    text_html = str(record.get("text", ""))
    text_plain = strip_html(text_html)
    section_number = str(record.get("number", ""))

    return StatuteSection(
        number=section_number,
        name=str(record.get("name", "")),
        chapter_number=str(record.get("chapter_number", "")),
        edition=int(record.get("edition", 0) or 0),
        kind=str(record.get("kind", "")),
        text_html=text_html,
        text_plain=text_plain,
        amendment_history=extract_amendment_history(text_plain),
        cross_references=extract_cross_references(text_plain, section_number),
    )


def parse_ors_file(filepath: str | Path) -> Iterator[StatuteSection]:
    path = Path(filepath)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            yield parse_ors_line(text)


def discover_ors_file() -> Path:
    candidates = [
        Path("datasets/UnitedStates/Oregon/ors.jsonl"),
        Path("vendor-data/datasets/UnitedStates/Oregon/ors.jsonl"),
        Path("../vendor-data/datasets/UnitedStates/Oregon/ors.jsonl"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return Path("vendor-data/datasets/UnitedStates/Oregon/ors.jsonl")
