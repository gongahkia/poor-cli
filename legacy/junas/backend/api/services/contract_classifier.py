from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from data.parsers.contract_segmenter import segment_contract


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    module = importlib.import_module(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


def _parse_label_index(label: str) -> int | None:
    value = str(label).strip()
    if not value:
        return None
    if value.startswith("LABEL_"):
        value = value.split("_")[-1]
    try:
        return int(value)
    except ValueError:
        return None


class ContractClassifier:
    def __init__(self, model_path: str | Path):
        model_dir = Path(model_path)
        if not model_dir.exists() or not model_dir.is_dir():
            raise RuntimeError(f"contract classifier model path is missing: {model_dir}")

        pipeline = _optional_import("transformers", "pipeline")
        AutoConfig = _optional_import("transformers", "AutoConfig")

        self.model_path = str(model_dir)
        self.pipeline = pipeline(
            "text-classification",
            model=self.model_path,
            tokenizer=self.model_path,
            truncation=True,
            max_length=512,
        )

        self.label_names: dict[int, str] = {}
        try:
            config = AutoConfig.from_pretrained(self.model_path)
            id2label = getattr(config, "id2label", {}) or {}
            self.label_names = {int(key): str(value) for key, value in id2label.items()}
        except Exception:
            self.label_names = {}

    def clause_type(self, label: str) -> str:
        label_idx = _parse_label_index(label)
        if label_idx is None:
            return label
        return self.label_names.get(label_idx, f"ClauseType-{label_idx}")

    def classify_contract(self, text: str, top_k_types: int = 3) -> list[dict[str, Any]]:
        segments = segment_contract(text)
        results: list[dict[str, Any]] = []

        for segment in segments:
            predictions = self.pipeline(segment["text"], top_k=top_k_types)
            normalized = predictions[0] if predictions and isinstance(predictions[0], list) else predictions
            if not isinstance(normalized, list) or not normalized:
                continue

            top_prediction = normalized[0]
            top_label = str(top_prediction.get("label", ""))
            result = {
                "segment_index": segment["index"],
                "text": segment["text"],
                "start": segment["start"],
                "end": segment["end"],
                "clause_type": self.clause_type(top_label),
                "confidence": round(float(top_prediction.get("score", 0.0)), 4),
                "alternatives": [
                    {
                        "type": self.clause_type(str(item.get("label", ""))),
                        "confidence": round(float(item.get("score", 0.0)), 4),
                    }
                    for item in normalized[1:]
                ],
            }
            results.append(result)

        return results


def create_contract_classifier(model_path: str | Path | None) -> ContractClassifier | None:
    if model_path is None:
        return None
    path = Path(model_path)
    if not path.exists() or not path.is_dir():
        return None
    return ContractClassifier(path)
