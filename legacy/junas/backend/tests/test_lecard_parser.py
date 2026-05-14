from __future__ import annotations

import json
import zipfile
from pathlib import Path

from data.parsers.lecard_parser import (
    build_corpus,
    discover_lecard_data_root,
    load_baseline_predictions,
    load_labels,
    load_queries,
    load_stopwords,
    unzip_candidates,
)


def test_discover_lecard_data_root_exists() -> None:
    root = discover_lecard_data_root()
    assert root.exists()
    assert (root / "query" / "query.json").exists()


def test_load_queries_parses_107_jsonl_rows() -> None:
    queries = load_queries()
    assert len(queries) == 107
    assert all("ridx" in row and "q" in row and "crime" in row for row in queries)


def test_load_labels_parses_107_query_entries() -> None:
    labels = load_labels()
    assert len(labels) == 107
    first_key = next(iter(labels))
    assert isinstance(labels[first_key], dict)


def test_load_stopwords_and_baseline_predictions() -> None:
    stopwords = load_stopwords()
    baselines = load_baseline_predictions()

    assert "的" in stopwords
    assert "bm25" in baselines
    assert len(baselines["bm25"]) == 107


def test_build_corpus_deduplicates_case_ids() -> None:
    all_candidates = {
        "1": [{"case_id": "100", "ajName": "A"}, {"case_id": "101", "ajName": "B"}],
        "2": [{"case_id": "101", "ajName": "B2"}, {"case_id": "102", "ajName": "C"}],
    }
    corpus = build_corpus(all_candidates)
    assert set(corpus.keys()) == {"100", "101", "102"}
    assert corpus["101"]["ajName"] == "B"


def test_unzip_candidates_extracts_test_archive(tmp_path: Path) -> None:
    data_root = tmp_path / "LeCaRD" / "data"
    candidates_dir = data_root / "candidates"
    candidates_dir.mkdir(parents=True)

    archive_path = candidates_dir / "candidates1.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("candidates1/123/9001.json", json.dumps({"ajName": "Sample"}))

    summary = unzip_candidates(data_root=data_root, force=True)
    extracted_file = candidates_dir / "candidates1" / "123" / "9001.json"

    assert summary["extracted"] == 1
    assert extracted_file.exists()
