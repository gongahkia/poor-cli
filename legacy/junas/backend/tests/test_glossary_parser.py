from pathlib import Path

from data.parsers.glossary_parser import (
    discover_dataset_root,
    discover_glossary_files,
    infer_domain,
    parse_glossary_file,
    strip_html,
)


def test_strip_html_removes_tags_and_decodes_entities() -> None:
    value = "<p>A &amp; B <em>term</em></p>"
    assert strip_html(value) == "A & B term"


def test_discover_glossary_files_finds_phase_two_sources() -> None:
    root = discover_dataset_root()
    files = discover_glossary_files(root)
    names = {path.name for path in files}
    assert "doj-glossaries.json" in names
    assert "uscis-glossary.json" in names
    assert "ors.jsonl" not in names


def test_parse_canadian_doj_multi_object_file() -> None:
    path = Path("../vendor-data/datasets/Canada/doj-glossaries.json")
    if not path.exists():
        path = Path("vendor-data/datasets/Canada/doj-glossaries.json")

    entries = parse_glossary_file(path)
    assert len(entries) > 100
    assert any(entry.domain == "family" for entry in entries)
    assert any(entry.domain == "general" for entry in entries)


def test_parse_california_glossary_uses_state_jurisdiction_override() -> None:
    path = Path("../vendor-data/datasets/UnitedStates/California/usa_ca_criminal_glossary.json")
    if not path.exists():
        path = Path("vendor-data/datasets/UnitedStates/California/usa_ca_criminal_glossary.json")

    entries = parse_glossary_file(path)
    assert entries
    assert all(entry.jurisdiction == "USA-CA" for entry in entries)


def test_infer_domain_defaults_to_mapping() -> None:
    domain = infer_domain("uscis-glossary.json", {})
    assert domain == "immigration"
