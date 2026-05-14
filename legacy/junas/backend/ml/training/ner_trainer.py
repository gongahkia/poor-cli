from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from data.parsers.conll_parser import ID_TO_LABEL, LABEL_LIST, LABEL_TO_ID, build_dataset

MODEL_NAME = "bert-base-german-cased"
NUM_LABELS = len(LABEL_LIST)


@dataclass(slots=True)
class NerTrainingConfig:
    dataset_root: str | None = None
    model_name: str = MODEL_NAME
    output_dir: str = "models/ner-german-legal"
    num_train_epochs: int = 5
    train_batch_size: int = 16
    eval_batch_size: int = 32
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    logging_steps: int = 100
    max_length: int = 512
    fp16: bool | None = None
    seed: int = 42


def _inside_label_id(label_id: int) -> int:
    label = ID_TO_LABEL[label_id]
    if not label.startswith("B-"):
        return label_id
    return LABEL_TO_ID.get(f"I-{label[2:]}", label_id)


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(f"{module_name} is not installed") from exc
    if attr_name is None:
        return module
    return getattr(module, attr_name)


def tokenize_and_align_labels(
    examples: dict[str, list[Any]],
    tokenizer: Any,
    max_length: int,
) -> dict[str, Any]:
    tokenized = tokenizer(
        examples["tokens"],
        truncation=True,
        is_split_into_words=True,
        max_length=max_length,
    )
    labels: list[list[int]] = []

    for index, label_ids in enumerate(examples["ner_tags"]):
        word_ids = tokenized.word_ids(batch_index=index)
        previous_word_idx: int | None = None
        aligned: list[int] = []

        for word_idx in word_ids:
            if word_idx is None:
                aligned.append(-100)
            elif word_idx != previous_word_idx:
                aligned.append(label_ids[word_idx])
            else:
                aligned.append(_inside_label_id(label_ids[word_idx]))
            previous_word_idx = word_idx

        labels.append(aligned)

    tokenized["labels"] = labels
    return tokenized


def build_compute_metrics() -> Any:
    np = _optional_import("numpy")
    metrics = _optional_import("seqeval.metrics")

    accuracy_score = getattr(metrics, "accuracy_score")
    f1_score = getattr(metrics, "f1_score")
    precision_score = getattr(metrics, "precision_score")
    recall_score = getattr(metrics, "recall_score")

    def compute_metrics(eval_pred: tuple[Any, Any]) -> dict[str, float]:
        predictions, labels = eval_pred
        prediction_ids = np.argmax(predictions, axis=-1)

        true_predictions: list[list[str]] = []
        true_labels: list[list[str]] = []

        for predicted_row, label_row in zip(prediction_ids, labels):
            row_predictions: list[str] = []
            row_labels: list[str] = []
            for prediction_id, label_id in zip(predicted_row, label_row):
                if label_id == -100:
                    continue
                row_predictions.append(ID_TO_LABEL[int(prediction_id)])
                row_labels.append(ID_TO_LABEL[int(label_id)])
            true_predictions.append(row_predictions)
            true_labels.append(row_labels)

        return {
            "precision": float(precision_score(true_labels, true_predictions)),
            "recall": float(recall_score(true_labels, true_predictions)),
            "overall_f1": float(f1_score(true_labels, true_predictions)),
            "accuracy": float(accuracy_score(true_labels, true_predictions)),
        }

    return compute_metrics


def train_model(config: NerTrainingConfig) -> dict[str, Any]:
    torch = _optional_import("torch")
    transformers = _optional_import("transformers")

    AutoModelForTokenClassification = getattr(transformers, "AutoModelForTokenClassification")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    DataCollatorForTokenClassification = getattr(transformers, "DataCollatorForTokenClassification")
    Trainer = getattr(transformers, "Trainer")
    TrainingArguments = getattr(transformers, "TrainingArguments")

    dataset = build_dataset(config.dataset_root)
    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    model = AutoModelForTokenClassification.from_pretrained(
        config.model_name,
        num_labels=NUM_LABELS,
        id2label={index: label for index, label in enumerate(LABEL_LIST)},
        label2id=LABEL_TO_ID,
    )

    tokenized_dataset = dataset.map(
        lambda examples: tokenize_and_align_labels(
            examples=examples,
            tokenizer=tokenizer,
            max_length=config.max_length,
        ),
        batched=True,
    )

    use_fp16 = config.fp16 if config.fp16 is not None else bool(torch.cuda.is_available())
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=config.num_train_epochs,
        per_device_train_batch_size=config.train_batch_size,
        per_device_eval_batch_size=config.eval_batch_size,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        warmup_ratio=config.warmup_ratio,
        logging_steps=config.logging_steps,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="overall_f1",
        fp16=use_fp16,
        seed=config.seed,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["validation"],
        tokenizer=tokenizer,
        data_collator=DataCollatorForTokenClassification(tokenizer=tokenizer),
        compute_metrics=build_compute_metrics(),
    )

    trainer.train()
    test_results = trainer.evaluate(tokenized_dataset["test"])

    best_dir = output_dir / "best"
    trainer.save_model(str(best_dir))
    tokenizer.save_pretrained(str(best_dir))

    return {
        "model_path": str(best_dir),
        "metrics": {key: float(value) for key, value in test_results.items()},
    }


def parse_args() -> NerTrainingConfig:
    parser = argparse.ArgumentParser(description="Train German legal NER model")
    parser.add_argument("--dataset-root", type=str, default=None)
    parser.add_argument("--model-name", type=str, default=MODEL_NAME)
    parser.add_argument("--output-dir", type=str, default="models/ner-german-legal")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--no-fp16", action="store_true")

    args = parser.parse_args()
    fp16: bool | None = None
    if args.fp16:
        fp16 = True
    if args.no_fp16:
        fp16 = False

    return NerTrainingConfig(
        dataset_root=args.dataset_root,
        model_name=args.model_name,
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        fp16=fp16,
    )


def main() -> int:
    config = parse_args()
    result = train_model(config)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
