from __future__ import annotations

from data.parsers.rome_statute_parser import (
    discover_rome_statute_file,
    parse_rome_statute,
    parse_rome_statute_records,
)


def test_discover_rome_statute_file_points_to_json() -> None:
    path = discover_rome_statute_file()
    assert path.exists()
    assert path.name == "RomeStatute.json"


def test_parse_rome_statute_records_extracts_articles_with_parts() -> None:
    path = discover_rome_statute_file()
    records = parse_rome_statute_records(path)

    assert len(records) >= 120
    assert records[0].article_number == "1"
    assert records[0].part_number == "1"
    assert "Court" in records[0].article_title
    assert records[0].part_title != ""


def test_parse_rome_statute_returns_serializable_dict_rows() -> None:
    path = discover_rome_statute_file()
    rows = parse_rome_statute(path)

    assert len(rows) >= 120
    first = rows[0]
    assert set(first.keys()) == {
        "article_number",
        "article_title",
        "text",
        "part_number",
        "part_title",
    }
    assert first["article_number"] == "1"
