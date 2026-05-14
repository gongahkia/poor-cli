from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RomeStatuteArticle:
    article_number: str
    article_title: str
    text: str
    part_number: str
    part_title: str


def discover_rome_statute_file() -> Path:
    candidates = [
        Path("../vendor-data/datasets/Intergovernmental/RomeStatute/RomeStatute.json"),
        Path("vendor-data/datasets/Intergovernmental/RomeStatute/RomeStatute.json"),
        Path("../../vendor-data/datasets/Intergovernmental/RomeStatute/RomeStatute.json"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return candidates[0]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())


def parse_rome_statute_records(filepath: str | Path) -> list[RomeStatuteArticle]:
    path = Path(filepath)
    with path.open(encoding="utf-8", errors="replace") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        raise ValueError("Rome Statute dataset must be a list")

    part_names: dict[str, str] = {}
    articles: list[RomeStatuteArticle] = []

    for entry in payload:
        if not isinstance(entry, dict):
            continue

        part = entry.get("part")
        if isinstance(part, dict):
            part_number = _normalize_text(part.get("number"))
            part_title = _normalize_text(part.get("name"))
            if part_number:
                part_names[part_number] = part_title
            continue

        article = entry.get("article")
        if not isinstance(article, dict):
            continue

        part_number = _normalize_text(article.get("part_number"))
        part_title = part_names.get(part_number, "")
        articles.append(
            RomeStatuteArticle(
                article_number=_normalize_text(article.get("number")),
                article_title=_normalize_text(article.get("name")),
                text=_normalize_text(article.get("text")),
                part_number=part_number,
                part_title=part_title,
            )
        )

    return [
        article
        for article in articles
        if article.article_number and article.article_title and article.text
    ]


def parse_rome_statute(filepath: str | Path) -> list[dict[str, str]]:
    return [
        {
            "article_number": row.article_number,
            "article_title": row.article_title,
            "text": row.text,
            "part_number": row.part_number,
            "part_title": row.part_title,
        }
        for row in parse_rome_statute_records(filepath)
    ]
