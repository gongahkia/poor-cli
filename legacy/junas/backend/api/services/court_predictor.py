from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

SCOTUS_ISSUE_AREAS = {
    0: "Criminal Procedure",
    1: "Civil Rights",
    2: "First Amendment",
    3: "Due Process",
    4: "Privacy",
    5: "Attorneys",
    6: "Unions",
    7: "Economic Activity",
    8: "Judicial Power",
    9: "Federalism",
    10: "Interstate Relations",
    11: "Federal Taxation",
    12: "Miscellaneous",
    13: "Private Action",
}

ECTHR_ARTICLES = {
    0: ("Article 2", "Right to life"),
    1: ("Article 3", "Prohibition of torture"),
    2: ("Article 5", "Right to liberty and security"),
    3: ("Article 6", "Right to a fair trial"),
    4: ("Article 8", "Right to private life"),
    5: ("Article 9", "Freedom of thought and religion"),
    6: ("Article 10", "Freedom of expression"),
    7: ("Article 11", "Freedom of assembly"),
    8: ("Article 14", "Prohibition of discrimination"),
    9: ("Article 1 Protocol 1", "Protection of property"),
}


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
        value = value.split("_", maxsplit=1)[1]
    try:
        return int(value)
    except ValueError:
        return None


def _flatten_pipeline_result(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        nested = raw[0]
        return [item for item in nested if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


class CourtPredictor:
    def __init__(
        self,
        scotus_model_path: str,
        ecthr_violation_model_path: str,
        ecthr_alleged_model_path: str,
        casehold_model_path: str,
        eurlex_model_path: str,
    ):
        self.scotus_model_path = Path(scotus_model_path)
        self.ecthr_violation_model_path = Path(ecthr_violation_model_path)
        self.ecthr_alleged_model_path = Path(ecthr_alleged_model_path)
        self.casehold_model_path = Path(casehold_model_path)
        self.eurlex_model_path = Path(eurlex_model_path)

        self.scotus_pipeline: Any = None
        self.ecthr_violation_pipeline: Any = None
        self.ecthr_alleged_pipeline: Any = None
        self.eurlex_pipeline: Any = None

        self.casehold_model: Any = None
        self.casehold_tokenizer: Any = None

        self.scotus_label_names: dict[int, str] = {}
        self.eurlex_label_names: dict[int, str] = {}

        self._load_models()

    @property
    def available_models(self) -> dict[str, bool]:
        return {
            "scotus": self.scotus_pipeline is not None,
            "ecthr_violation": self.ecthr_violation_pipeline is not None,
            "ecthr_alleged": self.ecthr_alleged_pipeline is not None,
            "casehold": self.casehold_model is not None and self.casehold_tokenizer is not None,
            "eurlex": self.eurlex_pipeline is not None,
        }

    @staticmethod
    def _load_label_names(model_path: Path) -> dict[int, str]:
        if not model_path.exists() or not model_path.is_dir():
            return {}

        try:
            AutoConfig = _optional_import("transformers", "AutoConfig")
            config = AutoConfig.from_pretrained(str(model_path))
        except Exception:
            return {}

        id2label = getattr(config, "id2label", {}) or {}
        output: dict[int, str] = {}
        for key, value in id2label.items():
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            name = str(value).strip()
            if not name:
                continue
            output[index] = name
        return output

    def _load_text_pipeline(self, model_path: Path, top_k: int) -> Any:
        if not model_path.exists() or not model_path.is_dir():
            return None

        pipeline = _optional_import("transformers", "pipeline")
        return pipeline(
            "text-classification",
            model=str(model_path),
            tokenizer=str(model_path),
            top_k=top_k,
            truncation=True,
        )

    def _load_casehold(self) -> None:
        if not self.casehold_model_path.exists() or not self.casehold_model_path.is_dir():
            return

        AutoModelForMultipleChoice = _optional_import("transformers", "AutoModelForMultipleChoice")
        AutoTokenizer = _optional_import("transformers", "AutoTokenizer")

        self.casehold_tokenizer = AutoTokenizer.from_pretrained(str(self.casehold_model_path))
        self.casehold_model = AutoModelForMultipleChoice.from_pretrained(str(self.casehold_model_path))
        self.casehold_model.eval()

    def _load_models(self) -> None:
        self.scotus_label_names = self._load_label_names(self.scotus_model_path)
        self.eurlex_label_names = self._load_label_names(self.eurlex_model_path)

        try:
            self.scotus_pipeline = self._load_text_pipeline(self.scotus_model_path, top_k=14)
        except Exception:
            self.scotus_pipeline = None

        try:
            self.ecthr_violation_pipeline = self._load_text_pipeline(self.ecthr_violation_model_path, top_k=10)
        except Exception:
            self.ecthr_violation_pipeline = None

        try:
            self.ecthr_alleged_pipeline = self._load_text_pipeline(self.ecthr_alleged_model_path, top_k=10)
        except Exception:
            self.ecthr_alleged_pipeline = None

        try:
            self.eurlex_pipeline = self._load_text_pipeline(self.eurlex_model_path, top_k=100)
        except Exception:
            self.eurlex_pipeline = None

        try:
            self._load_casehold()
        except Exception:
            self.casehold_model = None
            self.casehold_tokenizer = None

    @staticmethod
    def _validate_text(text: str) -> str:
        value = text.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    def predict_scotus(self, text: str, top_k: int = 3) -> dict[str, Any]:
        if self.scotus_pipeline is None:
            raise RuntimeError("SCOTUS model not loaded")

        normalized = self._validate_text(text)
        raw = self.scotus_pipeline(normalized[:9000], top_k=max(1, min(14, top_k)))
        rows = _flatten_pipeline_result(raw)
        rows.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)

        selected = rows[0] if rows else {"label": "LABEL_12", "score": 0.0}
        selected_id = _parse_label_index(str(selected.get("label", "")))
        selected_name = (
            SCOTUS_ISSUE_AREAS.get(selected_id)
            if selected_id is not None
            else None
        ) or self.scotus_label_names.get(selected_id or -1, "Unknown")

        alternatives: list[dict[str, Any]] = []
        for item in rows[1:top_k]:
            issue_id = _parse_label_index(str(item.get("label", "")))
            issue_name = (
                SCOTUS_ISSUE_AREAS.get(issue_id)
                if issue_id is not None
                else None
            ) or self.scotus_label_names.get(issue_id or -1, "Unknown")

            alternatives.append(
                {
                    "issue_area": issue_name,
                    "issue_area_id": issue_id,
                    "confidence": float(item.get("score", 0.0)),
                }
            )

        return {
            "prediction": {
                "issue_area": selected_name,
                "issue_area_id": selected_id,
                "confidence": float(selected.get("score", 0.0)),
            },
            "alternatives": alternatives,
            "model_info": {"model": "scotus-classifier", "input_length": len(normalized)},
        }

    def predict_ecthr(self, text: str, task: str = "violation", threshold: float = 0.5) -> dict[str, Any]:
        normalized = self._validate_text(text)
        normalized_task = task.strip().lower()
        if normalized_task not in {"violation", "alleged"}:
            raise ValueError("task must be either 'violation' or 'alleged'")

        model_pipeline = (
            self.ecthr_violation_pipeline
            if normalized_task == "violation"
            else self.ecthr_alleged_pipeline
        )
        if model_pipeline is None:
            raise RuntimeError(f"ECtHR {normalized_task} model not loaded")

        raw = model_pipeline(normalized[:9000])
        rows = _flatten_pipeline_result(raw)
        rows.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)

        predictions: list[dict[str, Any]] = []
        for row in rows:
            article_id = _parse_label_index(str(row.get("label", "")))
            if article_id is None or article_id not in ECTHR_ARTICLES:
                continue
            confidence = float(row.get("score", 0.0))
            if confidence < threshold:
                continue
            article, right = ECTHR_ARTICLES[article_id]
            predictions.append(
                {
                    "article": article,
                    "article_id": article_id,
                    "right": right,
                    "confidence": confidence,
                }
            )

        max_confidence = max((float(row.get("score", 0.0)) for row in rows), default=0.0)
        no_violation_probability = max(0.0, min(1.0, 1.0 - max_confidence))

        return {
            "predictions": predictions,
            "no_violation_probability": no_violation_probability,
            "task": normalized_task,
        }

    def predict_casehold(self, context: str, options: list[str]) -> dict[str, Any]:
        if self.casehold_model is None or self.casehold_tokenizer is None:
            raise RuntimeError("CaseHOLD model not loaded")

        normalized_context = context.strip()
        if not normalized_context:
            raise ValueError("context must not be blank")
        if len(options) != 5:
            raise ValueError("CaseHOLD requires exactly 5 options")

        normalized_options = [option.strip() for option in options]
        if any(not option for option in normalized_options):
            raise ValueError("all CaseHOLD options must be non-empty")

        torch = _optional_import("torch")

        encoded = self.casehold_tokenizer(
            [normalized_context] * 5,
            normalized_options,
            truncation=True,
            padding=True,
            max_length=256,
            return_tensors="pt",
        )

        model_inputs = {key: value.unsqueeze(0) for key, value in encoded.items()}

        with torch.no_grad():
            logits = self.casehold_model(**model_inputs).logits
            probabilities = torch.softmax(logits, dim=1).squeeze(0)

        scores = [float(value) for value in probabilities.tolist()]
        selected_option = max(range(len(scores)), key=lambda idx: scores[idx])

        return {
            "selected_option": selected_option,
            "selected_text": normalized_options[selected_option],
            "confidence": scores[selected_option],
            "option_scores": scores,
        }

    def predict_eurlex(self, text: str, threshold: float = 0.3, max_labels: int = 10) -> dict[str, Any]:
        if self.eurlex_pipeline is None:
            raise RuntimeError("EUR-LEX model not loaded")

        normalized = self._validate_text(text)
        raw = self.eurlex_pipeline(normalized[:9000])
        rows = _flatten_pipeline_result(raw)
        rows.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)

        labels: list[dict[str, Any]] = []
        for row in rows:
            confidence = float(row.get("score", 0.0))
            if confidence < threshold:
                continue

            label_id = _parse_label_index(str(row.get("label", "")))
            if label_id is None:
                continue

            concept = self.eurlex_label_names.get(label_id, f"EuroVoc concept {label_id}")
            labels.append(
                {
                    "eurovoc_id": label_id,
                    "concept": concept,
                    "confidence": confidence,
                }
            )
            if len(labels) >= max_labels:
                break

        return {
            "labels": labels,
            "total_labels": len(labels),
        }


def create_court_predictor(
    scotus_model_path: str,
    ecthr_violation_model_path: str,
    ecthr_alleged_model_path: str,
    casehold_model_path: str,
    eurlex_model_path: str,
) -> CourtPredictor:
    return CourtPredictor(
        scotus_model_path=scotus_model_path,
        ecthr_violation_model_path=ecthr_violation_model_path,
        ecthr_alleged_model_path=ecthr_alleged_model_path,
        casehold_model_path=casehold_model_path,
        eurlex_model_path=eurlex_model_path,
    )
