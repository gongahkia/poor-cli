from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ml.training.benchmark_registration import register_lexglue_score

MODEL_NAME = "nlpaueb/legal-bert-base-uncased"
DATASET_NAME = "coastalcph/lex_glue"
SUPPORTED_TASKS = ("ecthr_a", "ecthr_b")
NUM_LABELS = 10


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    module = importlib.import_module(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


def _to_multi_hot(labels: list[int], num_labels: int) -> list[float]:
    values = [0.0] * num_labels
    for label in labels:
        if 0 <= label < num_labels:
            values[label] = 1.0
    return values


@dataclass(slots=True)
class EcthrTrainingConfig:
    model_name: str = MODEL_NAME
    output_dir: str = "models"
    tasks: tuple[str, ...] = SUPPORTED_TASKS
    num_train_epochs: int = 8
    train_batch_size: int = 8
    eval_batch_size: int = 16
    learning_rate: float = 3e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    logging_steps: int = 100
    max_length: int = 512
    threshold: float = 0.5
    fp16: bool | None = None
    early_stopping_patience: int = 2
    seed: int = 42
    run_name: str = "ecthr-legal-bert"
    register_to_benchmarks: bool = False
    benchmark_api_base_url: str = "http://localhost:8000"


def _normalize_tasks(tasks: tuple[str, ...]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for task in tasks:
        item = str(task).strip().lower()
        if not item:
            continue
        if item not in SUPPORTED_TASKS:
            allowed = ", ".join(SUPPORTED_TASKS)
            raise ValueError(f"Unsupported ECtHR task '{item}'. Allowed: {allowed}")
        if item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    if not cleaned:
        return SUPPORTED_TASKS
    return tuple(cleaned)


def train_ecthr_models(config: EcthrTrainingConfig) -> dict[str, Any]:
    datasets = _optional_import("datasets")
    np = _optional_import("numpy")
    torch = _optional_import("torch")
    transformers = _optional_import("transformers")
    sklearn_metrics = _optional_import("sklearn.metrics")

    load_dataset = getattr(datasets, "load_dataset")
    f1_score = getattr(sklearn_metrics, "f1_score")

    AutoModelForSequenceClassification = getattr(transformers, "AutoModelForSequenceClassification")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    EarlyStoppingCallback = getattr(transformers, "EarlyStoppingCallback")
    Trainer = getattr(transformers, "Trainer")
    TrainingArguments = getattr(transformers, "TrainingArguments")

    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    use_fp16 = config.fp16 if config.fp16 is not None else bool(torch.cuda.is_available())

    tasks = _normalize_tasks(config.tasks)
    output_root = Path(config.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}

    for task_name in tasks:
        dataset = load_dataset(DATASET_NAME, task_name)
        dataset = dataset.map(
            lambda example: {"labels": _to_multi_hot(example["labels"], NUM_LABELS)}
        )
        tokenized = dataset.map(
            lambda examples: tokenizer(
                examples["text"],
                truncation=True,
                max_length=config.max_length,
                padding="max_length",
            ),
            batched=True,
        )

        model = AutoModelForSequenceClassification.from_pretrained(
            config.model_name,
            num_labels=NUM_LABELS,
            problem_type="multi_label_classification",
        )

        def compute_metrics(eval_pred: tuple[Any, Any]) -> dict[str, float]:
            predictions, labels = eval_pred
            probabilities = 1.0 / (1.0 + np.exp(-predictions))
            predicted = (probabilities >= config.threshold).astype(int)
            return {
                "micro_f1": float(f1_score(labels, predicted, average="micro", zero_division=0)),
                "macro_f1": float(f1_score(labels, predicted, average="macro", zero_division=0)),
            }

        task_output_dir = output_root / ("ecthr-classifier-a" if task_name == "ecthr_a" else "ecthr-classifier-b")
        task_output_dir.mkdir(parents=True, exist_ok=True)

        training_args = TrainingArguments(
            output_dir=str(task_output_dir),
            num_train_epochs=config.num_train_epochs,
            per_device_train_batch_size=config.train_batch_size,
            per_device_eval_batch_size=config.eval_batch_size,
            learning_rate=config.learning_rate,
            weight_decay=config.weight_decay,
            warmup_ratio=config.warmup_ratio,
            eval_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="micro_f1",
            greater_is_better=True,
            fp16=use_fp16,
            logging_steps=config.logging_steps,
            seed=config.seed,
        )

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized["train"],
            eval_dataset=tokenized["validation"],
            tokenizer=tokenizer,
            compute_metrics=compute_metrics,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=config.early_stopping_patience)],
        )

        trainer.train()
        test_metrics = trainer.evaluate(tokenized["test"])

        best_dir = task_output_dir / "best"
        trainer.save_model(str(best_dir))
        tokenizer.save_pretrained(str(best_dir))

        metrics = {key: float(value) for key, value in test_metrics.items()}
        task_payload: dict[str, Any] = {
            "task": task_name,
            "model_path": str(best_dir),
            "metrics": metrics,
        }

        if config.register_to_benchmarks:
            micro = float(metrics.get("eval_micro_f1", 0.0))
            macro = float(metrics.get("eval_macro_f1", 0.0))
            try:
                task_payload["benchmark_registration"] = register_lexglue_score(
                    api_base_url=config.benchmark_api_base_url,
                    model_name=config.model_name,
                    run_name=config.run_name,
                    task=task_name,
                    micro_f1=micro,
                    macro_f1=macro,
                    metadata={"model_path": str(best_dir)},
                )
            except Exception as exc:
                task_payload["benchmark_registration_error"] = str(exc)

        results[task_name] = task_payload

    return {
        "model_name": config.model_name,
        "tasks": list(tasks),
        "results": results,
    }


def parse_args() -> EcthrTrainingConfig:
    parser = argparse.ArgumentParser(description="Train ECtHR violation/alleged-violation predictors")
    parser.add_argument("--model-name", type=str, default=MODEL_NAME)
    parser.add_argument("--output-dir", type=str, default="models")
    parser.add_argument("--tasks", type=str, default="ecthr_a,ecthr_b")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--run-name", type=str, default="ecthr-legal-bert")
    parser.add_argument("--register-benchmarks", action="store_true")
    parser.add_argument("--benchmark-api-base-url", type=str, default="http://localhost:8000")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--no-fp16", action="store_true")
    args = parser.parse_args()

    task_values = tuple(item.strip() for item in args.tasks.split(",") if item.strip())

    fp16: bool | None = None
    if args.fp16:
        fp16 = True
    if args.no_fp16:
        fp16 = False

    return EcthrTrainingConfig(
        model_name=args.model_name,
        output_dir=args.output_dir,
        tasks=task_values or SUPPORTED_TASKS,
        num_train_epochs=args.epochs,
        max_length=args.max_length,
        threshold=args.threshold,
        run_name=args.run_name,
        register_to_benchmarks=args.register_benchmarks,
        benchmark_api_base_url=args.benchmark_api_base_url,
        fp16=fp16,
    )


def main() -> int:
    config = parse_args()
    result = train_ecthr_models(config)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
