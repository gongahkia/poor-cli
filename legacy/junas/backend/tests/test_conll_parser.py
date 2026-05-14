from pathlib import Path

from data.parsers.conll_parser import (
    LABEL_LIST,
    collect_label_set,
    discover_ler_dataset_root,
    parse_conll_file,
    sentence_count,
    split_paths,
)


def test_discover_ler_dataset_root_finds_reference_repo_data() -> None:
    root = discover_ler_dataset_root()
    assert root.exists()
    assert root.is_dir()
    assert (root / "ler_train.conll").exists()


def test_sentence_counts_match_phase_requirements() -> None:
    paths = split_paths()
    assert sentence_count(paths["train"]) == 53384
    assert sentence_count(paths["validation"]) == 6666
    assert sentence_count(paths["test"]) == 6673


def test_all_39_labels_present_across_dataset_splits() -> None:
    paths = split_paths()
    labels: set[str] = set()

    for split_name in ("train", "validation", "test"):
        parsed = parse_conll_file(paths[split_name])
        labels.update(collect_label_set(parsed))

    assert labels == set(LABEL_LIST)


def test_parser_handles_last_sentence_without_trailing_newline(tmp_path: Path) -> None:
    sample = "BGH B-ORG\nentschied O\n"
    filepath = tmp_path / "sample.conll"
    filepath.write_text(sample, encoding="utf-8")

    parsed = parse_conll_file(filepath)
    assert parsed["tokens"] == [["BGH", "entschied"]]
    assert parsed["ner_tags"] == [["B-ORG", "O"]]
