from data.parsers.statute_parser import (
    discover_ors_file,
    extract_amendment_history,
    extract_cross_references,
    parse_ors_file,
    parse_ors_line,
    strip_html,
)


def test_strip_html_preserves_plaintext_structure() -> None:
    value = "<p>Alpha</p><p>Beta &amp; Gamma</p>"
    assert strip_html(value) == "Alpha Beta & Gamma"


def test_extract_amendment_history_from_trailing_bracket() -> None:
    text = "Clause text [Amended by 1953 c.557 §4]"
    assert extract_amendment_history(text) == "[Amended by 1953 c.557 §4]"


def test_extract_cross_references_excludes_self_number() -> None:
    text = "See ORS 685.010 and ORS 676.347 and ORS 685.010"
    refs = extract_cross_references(text, "685.010")
    assert refs == ["676.347"]


def test_parse_single_ors_record_contains_expected_fields() -> None:
    line = (
        '{"edition":2023,"chapter_number":"685","kind":"section","text":"<p>Sample [Amended by 2001 c.526 '
        '§1]</p>","number":"685.020","name":"License required under ORS 676.347"}'
    )
    section = parse_ors_line(line)
    assert section.number == "685.020"
    assert section.chapter_number == "685"
    assert section.edition == 2023
    assert "Amended by 2001" in section.amendment_history


def test_parse_ors_file_reads_real_dataset_lines() -> None:
    path = discover_ors_file()
    assert path.exists()

    parsed = []
    for section in parse_ors_file(path):
        parsed.append(section)
        if len(parsed) == 3:
            break

    assert len(parsed) == 3
    assert parsed[0].number == "685.010"
    assert parsed[1].number == "685.020"
    assert "676.347" in parsed[1].cross_references
