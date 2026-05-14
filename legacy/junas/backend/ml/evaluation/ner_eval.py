from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from api.config import get_settings
from api.services.entity_extractor import FINE_ENTITY_TYPES
from data.parsers.conll_parser import ID_TO_LABEL, build_dataset
from ml.training.ner_trainer import tokenize_and_align_labels


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    module = importlib.import_module(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


def _database_url_for_asyncpg(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _serialize_metrics(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serialize_metrics(raw) for key, raw in value.items()}
    if isinstance(value, list):
        return [_serialize_metrics(raw) for raw in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


async def _register_metrics_in_models_table(
    model_name: str,
    model_path: str,
    metrics: dict[str, Any],
    database_url: str,
) -> bool:
    try:
        asyncpg = _optional_import("asyncpg")
    except ModuleNotFoundError:
        return False

    connection = None
    try:
        connection = await asyncpg.connect(_database_url_for_asyncpg(database_url))
        await connection.execute(
            """
            INSERT INTO models(name, task, dataset_name, model_path, metrics, status)
            VALUES($1, $2, $3, $4, $5::jsonb, $6)
            """,
            model_name,
            "ner",
            "german-ler",
            model_path,
            json.dumps(_serialize_metrics(metrics)),
            "ready",
        )
        return True
    except Exception:
        return False
    finally:
        if connection is not None:
            await connection.close()


def evaluate_ner_model(
    model_path: str,
    dataset_root: str | None = None,
    batch_size: int = 32,
    max_length: int = 512,
    database_url: str | None = None,
) -> dict[str, Any]:
    np = _optional_import("numpy")
    transformers = _optional_import("transformers")
    seqeval_metrics = _optional_import("seqeval.metrics")

    AutoModelForTokenClassification = getattr(transformers, "AutoModelForTokenClassification")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    Trainer = getattr(transformers, "Trainer")
    TrainingArguments = getattr(transformers, "TrainingArguments")

    classification_report = getattr(seqeval_metrics, "classification_report")
    f1_score = getattr(seqeval_metrics, "f1_score")
    precision_score = getattr(seqeval_metrics, "precision_score")
    recall_score = getattr(seqeval_metrics, "recall_score")

    model_dir = Path(model_path)
    if not model_dir.exists() or not model_dir.is_dir():
        raise FileNotFoundError(f"model path does not exist: {model_dir}")

    dataset = build_dataset(dataset_root)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForTokenClassification.from_pretrained(model_dir)

    tokenized_dataset = dataset.map(
        lambda examples: tokenize_and_align_labels(
            examples=examples,
            tokenizer=tokenizer,
            max_length=max_length,
        ),
        batched=True,
    )

    with TemporaryDirectory(prefix="junas-ner-eval-") as temp_dir:
        trainer = Trainer(
            model=model,
            args=TrainingArguments(
                output_dir=temp_dir,
                per_device_eval_batch_size=batch_size,
                do_train=False,
                do_eval=False,
                report_to=[],
            ),
            tokenizer=tokenizer,
        )

        predictions, labels, _ = trainer.predict(tokenized_dataset["test"])

    prediction_ids = np.argmax(predictions, axis=-1)
    true_predictions: list[list[str]] = []
    true_labels: list[list[str]] = []

    for prediction_row, label_row in zip(prediction_ids, labels):
        prediction_labels: list[str] = []
        reference_labels: list[str] = []
        for prediction_id, label_id in zip(prediction_row, label_row):
            if label_id == -100:
                continue
            prediction_labels.append(ID_TO_LABEL[int(prediction_id)])
            reference_labels.append(ID_TO_LABEL[int(label_id)])
        true_predictions.append(prediction_labels)
        true_labels.append(reference_labels)

    report = classification_report(true_labels, true_predictions, output_dict=True, zero_division=0)
    per_entity_type: list[dict[str, Any]] = []
    total_support = 0

    for entity in FINE_ENTITY_TYPES:
        tag = entity["tag"]
        values = report.get(tag, {})
        support = int(values.get("support", 0))
        total_support += support
        per_entity_type.append(
            {
                "tag": tag,
                "label": entity["label"],
                "precision": float(values.get("precision", 0.0)),
                "recall": float(values.get("recall", 0.0)),
                "f1": float(values.get("f1-score", 0.0)),
                "support": support,
            }
        )

    overall = {
        "precision": float(precision_score(true_labels, true_predictions)),
        "recall": float(recall_score(true_labels, true_predictions)),
        "f1": float(f1_score(true_labels, true_predictions)),
        "support": total_support,
    }

    payload: dict[str, Any] = {
        "model_path": str(model_dir),
        "overall": overall,
        "per_entity_type": per_entity_type,
    }

    output_file = model_dir / "eval_results.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    settings = get_settings()
    db_url = database_url or settings.database_url
    loop = asyncio.new_event_loop()
    try:
        payload["registered_in_db"] = bool(
            loop.run_until_complete(
                _register_metrics_in_models_table(
                    model_name=f"{model_dir.parent.name}-{model_dir.name}",
                    model_path=str(model_dir),
                    metrics=payload,
                    database_url=db_url,
                )
            )
        )
    finally:
        loop.close()
    payload["eval_results_path"] = str(output_file)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained legal NER model")
    parser.add_argument("--model-path", required=True, type=str)
    parser.add_argument("--dataset-root", default=None, type=str)
    parser.add_argument("--batch-size", default=32, type=int)
    parser.add_argument("--max-length", default=512, type=int)
    parser.add_argument("--database-url", default=None, type=str)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = evaluate_ner_model(
        model_path=args.model_path,
        dataset_root=args.dataset_root,
        batch_size=args.batch_size,
        max_length=args.max_length,
        database_url=args.database_url,
    )
    print(json.dumps(_serialize_metrics(results), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
