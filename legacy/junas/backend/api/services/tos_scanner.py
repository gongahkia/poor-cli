from __future__ import annotations

import importlib
from collections import Counter
from pathlib import Path
from typing import Any

from data.parsers.contract_segmenter import split_sentences

UNFAIR_CATEGORIES = [
    "Jurisdiction",
    "Choice of Law",
    "Limitation of Liability",
    "Unilateral Termination",
    "Unilateral Amendment",
    "Content Removal",
    "Arbitration",
    "Contract by Using",
]


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    module = importlib.import_module(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


def _parse_label_index(label: str) -> int | None:
    value = str(label).strip()
    if value.startswith("LABEL_"):
        value = value.split("_")[-1]
    try:
        return int(value)
    except ValueError:
        return None


class ToSScanner:
    def __init__(self, model_path: str | Path):
        model_dir = Path(model_path)
        if not model_dir.exists() or not model_dir.is_dir():
            raise RuntimeError(f"unfair-tos model path is missing: {model_dir}")

        pipeline = _optional_import("transformers", "pipeline")
        self.model_path = str(model_dir)
        self.pipeline = pipeline(
            "text-classification",
            model=self.model_path,
            tokenizer=self.model_path,
            truncation=True,
            max_length=512,
        )

    def scan_tos(self, text: str, threshold: float = 0.5) -> dict[str, Any]:
        sentences = split_sentences(text)
        sentence_results: list[dict[str, Any]] = []
        summary_counter: Counter[str] = Counter()

        for index, sentence in enumerate(sentences):
            predictions = self.pipeline(sentence, top_k=None)
            normalized = predictions[0] if predictions and isinstance(predictions[0], list) else predictions
            if not isinstance(normalized, list):
                normalized = []

            flagged: list[dict[str, Any]] = []
            for prediction in normalized:
                label_idx = _parse_label_index(str(prediction.get("label", "")))
                score = float(prediction.get("score", 0.0))
                if label_idx is None or label_idx >= len(UNFAIR_CATEGORIES):
                    continue
                if score < threshold:
                    continue
                category = UNFAIR_CATEGORIES[label_idx]
                flagged.append({"category": category, "confidence": round(score, 4)})
                summary_counter[category] += 1

            sentence_results.append(
                {
                    "index": index,
                    "text": sentence,
                    "is_unfair": len(flagged) > 0,
                    "unfair_categories": flagged,
                }
            )

        unfair_count = sum(1 for row in sentence_results if row["is_unfair"])
        total_sentences = len(sentence_results)

        return {
            "total_sentences": total_sentences,
            "unfair_count": unfair_count,
            "fair_count": max(total_sentences - unfair_count, 0),
            "severity_score": round(unfair_count / total_sentences, 4) if total_sentences else 0.0,
            "sentences": sentence_results,
            "summary": dict(summary_counter),
        }


def create_tos_scanner(model_path: str | Path | None) -> ToSScanner | None:
    if model_path is None:
        return None
    path = Path(model_path)
    if not path.exists() or not path.is_dir():
        return None
    return ToSScanner(path)
