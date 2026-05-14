from __future__ import annotations

from pathlib import Path
from typing import Any

LABEL_LIST = [
    "O",
    "B-PER",
    "I-PER",
    "B-RR",
    "I-RR",
    "B-AN",
    "I-AN",
    "B-LD",
    "I-LD",
    "B-ST",
    "I-ST",
    "B-STR",
    "I-STR",
    "B-LDS",
    "I-LDS",
    "B-ORG",
    "I-ORG",
    "B-UN",
    "I-UN",
    "B-INN",
    "I-INN",
    "B-GRT",
    "I-GRT",
    "B-MRK",
    "I-MRK",
    "B-GS",
    "I-GS",
    "B-VO",
    "I-VO",
    "B-EUN",
    "I-EUN",
    "B-VS",
    "I-VS",
    "B-VT",
    "I-VT",
    "B-RS",
    "I-RS",
    "B-LIT",
    "I-LIT",
]

LABEL_TO_ID = {label: index for index, label in enumerate(LABEL_LIST)}
ID_TO_LABEL = {index: label for label, index in LABEL_TO_ID.items()}


def parse_conll_file(filepath: str | Path) -> dict[str, list[list[str]]]:
    """Parse one CoNLL-2002 file into sentence-level token/tag lists."""
    path = Path(filepath)
    sentences_tokens: list[list[str]] = []
    sentences_tags: list[list[str]] = []
    current_tokens: list[str] = []
    current_tags: list[str] = []

    with path.open(encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                if current_tokens:
                    sentences_tokens.append(current_tokens)
                    sentences_tags.append(current_tags)
                    current_tokens = []
                    current_tags = []
                continue

            token_tag = line.rsplit(" ", 1)
            if len(token_tag) != 2:
                continue
            token, tag = token_tag
            token = token.strip()
            tag = tag.strip()
            if not token or not tag:
                continue

            current_tokens.append(token)
            current_tags.append(tag)

    if current_tokens:
        sentences_tokens.append(current_tokens)
        sentences_tags.append(current_tags)

    return {"tokens": sentences_tokens, "ner_tags": sentences_tags}


def discover_ler_dataset_root() -> Path:
    candidates = [
        Path("Legal-Entity-Recognition/data"),
        Path("vendor-data/Legal-Entity-Recognition/data"),
        Path("../vendor-data/Legal-Entity-Recognition/data"),
        Path("../../vendor-data/Legal-Entity-Recognition/data"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return Path("vendor-data/Legal-Entity-Recognition/data")


def split_paths(dataset_root: str | Path | None = None) -> dict[str, Path]:
    root = Path(dataset_root) if dataset_root is not None else discover_ler_dataset_root()
    return {
        "train": root / "ler_train.conll",
        "validation": root / "ler_dev.conll",
        "test": root / "ler_test.conll",
    }


def _require_datasets() -> Any:
    try:
        import datasets
    except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("datasets is not installed") from exc
    return datasets


def _convert_tags_to_ids(batch: dict[str, list[list[str]]]) -> dict[str, list[list[int]]]:
    converted: list[list[int]] = []
    for tags in batch["ner_tags"]:
        converted.append([LABEL_TO_ID[tag] for tag in tags])
    return {"ner_tags": converted}


def build_dataset(dataset_root: str | Path | None = None) -> Any:
    """Build a HuggingFace DatasetDict with label ids and ClassLabel metadata."""
    datasets = _require_datasets()
    paths = split_paths(dataset_root)

    features = datasets.Features(
        {
            "tokens": datasets.Sequence(datasets.Value("string")),
            "ner_tags": datasets.Sequence(datasets.ClassLabel(names=LABEL_LIST)),
        }
    )

    parsed_by_split = {
        split_name: parse_conll_file(filepath)
        for split_name, filepath in paths.items()
    }

    dataset_dict = datasets.DatasetDict(
        {
            split_name: datasets.Dataset.from_dict(split_rows)
            .map(_convert_tags_to_ids, batched=True)
            .cast(features)
            for split_name, split_rows in parsed_by_split.items()
        }
    )
    return dataset_dict


def collect_label_set(dataset: dict[str, list[list[str]]]) -> set[str]:
    labels: set[str] = set()
    for sentence_tags in dataset["ner_tags"]:
        labels.update(sentence_tags)
    return labels


def sentence_count(filepath: str | Path) -> int:
    parsed = parse_conll_file(filepath)
    return len(parsed["tokens"])
