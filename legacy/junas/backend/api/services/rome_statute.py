from __future__ import annotations

from pathlib import Path
from typing import Any

from data.parsers.rome_statute_parser import parse_rome_statute


class RomeStatuteService:
    def __init__(self, data_path: str | Path):
        self.data_path = Path(data_path)
        self.articles: list[dict[str, str]] = []
        self.by_article_number: dict[str, dict[str, str]] = {}
        self.by_part_number: dict[str, list[dict[str, str]]] = {}
        self.part_titles: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.data_path.exists() or not self.data_path.is_file():
            return

        rows = parse_rome_statute(self.data_path)
        self.articles = rows

        for row in rows:
            article_number = str(row.get("article_number", "")).strip()
            part_number = str(row.get("part_number", "")).strip()
            part_title = str(row.get("part_title", "")).strip()
            if not article_number or not part_number:
                continue

            self.by_article_number[article_number] = row
            self.by_part_number.setdefault(part_number, []).append(row)
            if part_title:
                self.part_titles[part_number] = part_title

        for part_number in self.by_part_number:
            self.by_part_number[part_number].sort(key=lambda row: self._article_sort_key(row["article_number"]))

    @staticmethod
    def _article_sort_key(article_number: str) -> tuple[int, str]:
        value = str(article_number).strip()
        if value.isdigit():
            return (int(value), value)
        prefix = ""
        suffix = ""
        for char in value:
            if char.isdigit() and not suffix:
                prefix += char
            else:
                suffix += char
        if prefix.isdigit():
            return (int(prefix), value)
        return (10_000, value)

    @property
    def is_loaded(self) -> bool:
        return bool(self.articles)

    def list_parts(self) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        for part_number, rows in self.by_part_number.items():
            parts.append(
                {
                    "part_number": part_number,
                    "part_title": self.part_titles.get(part_number, ""),
                    "article_count": len(rows),
                }
            )
        parts.sort(key=lambda row: self._article_sort_key(str(row["part_number"])))
        return parts

    def get_part(self, part_number: str) -> dict[str, Any] | None:
        part_key = str(part_number).strip()
        rows = self.by_part_number.get(part_key)
        if not rows:
            return None

        return {
            "part_number": part_key,
            "part_title": self.part_titles.get(part_key, ""),
            "articles": [
                {
                    "article_number": row["article_number"],
                    "article_title": row["article_title"],
                }
                for row in rows
            ],
        }

    def get_article(self, article_number: str) -> dict[str, str] | None:
        return self.by_article_number.get(str(article_number).strip())

    def search(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        normalized = " ".join(query.strip().lower().split())
        if not normalized:
            return []

        terms = [term for term in normalized.split(" ") if term]
        results: list[dict[str, Any]] = []

        for row in self.articles:
            title = row["article_title"]
            text = row["text"]
            combined = f"{title} {text}".lower()

            score = 0.0
            for term in terms:
                if term in title.lower():
                    score += 2.0
                if term in combined:
                    score += 1.0

            if score <= 0:
                continue

            results.append(
                {
                    "article_number": row["article_number"],
                    "article_title": title,
                    "part_number": row["part_number"],
                    "part_title": row["part_title"],
                    "text_snippet": text[:500],
                    "score": score,
                }
            )

        results.sort(
            key=lambda row: (
                float(row["score"]),
                -self._article_sort_key(row["article_number"])[0],
            ),
            reverse=True,
        )
        return results[:top_k]


def create_rome_statute_service(data_path: str | Path | None) -> RomeStatuteService | None:
    if data_path is None:
        return None
    service = RomeStatuteService(data_path=data_path)
    if not service.is_loaded:
        return None
    return service
