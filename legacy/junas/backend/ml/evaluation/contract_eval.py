from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from pathlib import Path
from typing import Any

from api.config import get_settings

LEDGAR_BASELINE = {"micro_f1": 0.882, "macro_f1": 0.830}
UNFAIR_TOS_BASELINE = {"micro_f1": 0.960, "macro_f1": 0.830}


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    module = importlib.import_module(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


def _database_url_for_asyncpg(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serialize(raw) for key, raw in value.items()}
    if isinstance(value, list):
        return [_serialize(raw) for raw in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


async def _register_model_metrics(
    name: str,
    task: str,
    dataset_name: str,
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
            name,
            task,
            dataset_name,
            model_path,
            json.dumps(_serialize(metrics), ensure_ascii=False),
            "ready",
        )
        return True
    except Exception:
        return False
    finally:
        if connection is not None:
            await connection.close()


def evaluate_ledgar_model(model_path: str, max_length: int = 512, batch_size: int = 32) -> dict[str, Any]:
    datasets = _optional_import("datasets")
    np = _optional_import("numpy")
    transformers = _optional_import("transformers")
    sklearn_metrics = _optional_import("sklearn.metrics")

    load_dataset = getattr(datasets, "load_dataset")
    f1_score = getattr(sklearn_metrics, "f1_score")

    AutoModelForSequenceClassification = getattr(transformers, "AutoModelForSequenceClassification")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    Trainer = getattr(transformers, "Trainer")
    TrainingArguments = getattr(transformers, "TrainingArguments")

    model_dir = Path(model_path)
    if not model_dir.exists() or not model_dir.is_dir():
        raise FileNotFoundError(f"LEDGAR model path does not exist: {model_dir}")

    dataset = load_dataset("coastalcph/lex_glue", "ledgar")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)

    tokenized = dataset.map(
        lambda examples: tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
        ),
        batched=True,
    )

    trainer = Trainer(
        model=model,
        args=TrainingArguments(output_dir=str(model_dir / "tmp-eval"), per_device_eval_batch_size=batch_size),
        tokenizer=tokenizer,
    )
    predictions, labels, _ = trainer.predict(tokenized["test"])
    prediction_ids = np.argmax(predictions, axis=-1)

    metrics = {
        "micro_f1": float(f1_score(labels, prediction_ids, average="micro")),
        "macro_f1": float(f1_score(labels, prediction_ids, average="macro")),
    }
    return {"baseline": LEDGAR_BASELINE, "metrics": metrics}


def evaluate_unfair_tos_model(
    model_path: str,
    threshold: float = 0.5,
    max_length: int = 512,
    batch_size: int = 32,
) -> dict[str, Any]:
    datasets = _optional_import("datasets")
    np = _optional_import("numpy")
    transformers = _optional_import("transformers")
    sklearn_metrics = _optional_import("sklearn.metrics")

    load_dataset = getattr(datasets, "load_dataset")
    f1_score = getattr(sklearn_metrics, "f1_score")

    AutoModelForSequenceClassification = getattr(transformers, "AutoModelForSequenceClassification")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    Trainer = getattr(transformers, "Trainer")
    TrainingArguments = getattr(transformers, "TrainingArguments")

    model_dir = Path(model_path)
    if not model_dir.exists() or not model_dir.is_dir():
        raise FileNotFoundError(f"UNFAIR-ToS model path does not exist: {model_dir}")

    dataset = load_dataset("coastalcph/lex_glue", "unfair_tos")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)

    def to_multi_hot(example: dict[str, Any]) -> dict[str, Any]:
        values = [0.0] * 8
        for label in example["labels"]:
            if 0 <= label < 8:
                values[label] = 1.0
        return {"labels": values}

    dataset = dataset.map(to_multi_hot)
    tokenized = dataset.map(
        lambda examples: tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
        ),
        batched=True,
    )

    trainer = Trainer(
        model=model,
        args=TrainingArguments(output_dir=str(model_dir / "tmp-eval"), per_device_eval_batch_size=batch_size),
        tokenizer=tokenizer,
    )
    predictions, labels, _ = trainer.predict(tokenized["test"])
    probs = 1.0 / (1.0 + np.exp(-predictions))
    prediction_ids = (probs >= threshold).astype(int)

    metrics = {
        "micro_f1": float(f1_score(labels, prediction_ids, average="micro")),
        "macro_f1": float(f1_score(labels, prediction_ids, average="macro")),
    }
    return {"baseline": UNFAIR_TOS_BASELINE, "metrics": metrics}


def evaluate_contract_models(
    ledgar_model_path: str = "models/ledgar-classifier/best",
    unfair_tos_model_path: str = "models/unfair-tos-classifier/best",
    database_url: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}

    try:
        payload["ledgar"] = evaluate_ledgar_model(ledgar_model_path)
    except Exception as exc:
        payload["ledgar"] = {"error": str(exc), "baseline": LEDGAR_BASELINE}

    try:
        payload["unfair_tos"] = evaluate_unfair_tos_model(unfair_tos_model_path)
    except Exception as exc:
        payload["unfair_tos"] = {"error": str(exc), "baseline": UNFAIR_TOS_BASELINE}

    ledgar_output = Path(ledgar_model_path).parent / "eval_results.json"
    unfair_output = Path(unfair_tos_model_path).parent / "eval_results.json"
    ledgar_output.parent.mkdir(parents=True, exist_ok=True)
    unfair_output.parent.mkdir(parents=True, exist_ok=True)
    ledgar_output.write_text(json.dumps(_serialize(payload["ledgar"]), ensure_ascii=False, indent=2), encoding="utf-8")
    unfair_output.write_text(
        json.dumps(_serialize(payload["unfair_tos"]), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    settings = get_settings()
    db_url = database_url or settings.database_url
    loop = asyncio.new_event_loop()
    try:
        payload["registered_ledgar"] = bool(
            loop.run_until_complete(
                _register_model_metrics(
                    name="ledgar-classifier",
                    task="contract_classification",
                    dataset_name="LEDGAR",
                    model_path=str(Path(ledgar_model_path)),
                    metrics=payload["ledgar"],
                    database_url=db_url,
                )
            )
        )
        payload["registered_unfair_tos"] = bool(
            loop.run_until_complete(
                _register_model_metrics(
                    name="unfair-tos-classifier",
                    task="unfair_tos_detection",
                    dataset_name="UNFAIR-ToS",
                    model_path=str(Path(unfair_tos_model_path)),
                    metrics=payload["unfair_tos"],
                    database_url=db_url,
                )
            )
        )
    finally:
        loop.close()

    payload["ledgar_eval_path"] = str(ledgar_output)
    payload["unfair_tos_eval_path"] = str(unfair_output)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate contract analysis models")
    parser.add_argument("--ledgar-model-path", type=str, default="models/ledgar-classifier/best")
    parser.add_argument("--unfair-tos-model-path", type=str, default="models/unfair-tos-classifier/best")
    parser.add_argument("--database-url", type=str, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = evaluate_contract_models(
        ledgar_model_path=args.ledgar_model_path,
        unfair_tos_model_path=args.unfair_tos_model_path,
        database_url=args.database_url,
    )
    print(json.dumps(_serialize(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
