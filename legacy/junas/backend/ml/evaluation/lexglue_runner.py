from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence


class TaskType(str, Enum):
    MULTI_CLASS = "multi_class"
    MULTI_LABEL = "multi_label"
    MULTIPLE_CHOICE = "multiple_choice"


@dataclass(frozen=True)
class BenchmarkTask:
    display_name: str
    hf_config: str
    task_type: TaskType
    num_labels: int
    text_key: str = "text"
    label_key: str = "label"
    context_key: str = "context"
    choices_key: str = "endings"


LEXGLUE_TASKS: tuple[BenchmarkTask, ...] = (
    BenchmarkTask("ECtHR-A", "ecthr_a", TaskType.MULTI_LABEL, 10, label_key="labels"),
    BenchmarkTask("ECtHR-B", "ecthr_b", TaskType.MULTI_LABEL, 10, label_key="labels"),
    BenchmarkTask("SCOTUS", "scotus", TaskType.MULTI_CLASS, 14),
    BenchmarkTask("EUR-LEX", "eurlex", TaskType.MULTI_LABEL, 100, label_key="labels"),
    BenchmarkTask("LEDGAR", "ledgar", TaskType.MULTI_CLASS, 100),
    BenchmarkTask("UNFAIR-ToS", "unfair_tos", TaskType.MULTI_LABEL, 8, label_key="labels"),
    BenchmarkTask("CaseHOLD", "case_hold", TaskType.MULTIPLE_CHOICE, 5),
)

LEXGLUE_TASKS_BY_CONFIG: dict[str, BenchmarkTask] = {task.hf_config: task for task in LEXGLUE_TASKS}

PUBLISHED_BASELINES: dict[str, dict[str, dict[str, float | None]]] = {
    "TFIDF+SVM (published)": {
        "ecthr_a": {"micro_f1": 0.647, "macro_f1": 0.517},
        "ecthr_b": {"micro_f1": 0.746, "macro_f1": 0.651},
        "scotus": {"micro_f1": 0.782, "macro_f1": 0.695},
        "eurlex": {"micro_f1": 0.713, "macro_f1": 0.514},
        "ledgar": {"micro_f1": 0.872, "macro_f1": 0.824},
        "unfair_tos": {"micro_f1": 0.954, "macro_f1": 0.788},
        "case_hold": {"micro_f1": 0.729, "macro_f1": None},
    },
    "BERT (published)": {
        "ecthr_a": {"micro_f1": 0.712, "macro_f1": 0.636},
        "ecthr_b": {"micro_f1": 0.797, "macro_f1": 0.734},
        "scotus": {"micro_f1": 0.683, "macro_f1": 0.583},
        "eurlex": {"micro_f1": 0.714, "macro_f1": 0.572},
        "ledgar": {"micro_f1": 0.876, "macro_f1": 0.820},
        "unfair_tos": {"micro_f1": 0.956, "macro_f1": 0.813},
        "case_hold": {"micro_f1": 0.708, "macro_f1": None},
    },
    "Legal-BERT (published)": {
        "ecthr_a": {"micro_f1": 0.714, "macro_f1": 0.640},
        "ecthr_b": {"micro_f1": 0.804, "macro_f1": 0.747},
        "scotus": {"micro_f1": 0.764, "macro_f1": 0.665},
        "eurlex": {"micro_f1": 0.721, "macro_f1": 0.574},
        "ledgar": {"micro_f1": 0.882, "macro_f1": 0.830},
        "unfair_tos": {"micro_f1": 0.960, "macro_f1": 0.830},
        "case_hold": {"micro_f1": 0.753, "macro_f1": None},
    },
    "CaseLaw-BERT (published)": {
        "ecthr_a": {"micro_f1": 0.698, "macro_f1": 0.629},
        "ecthr_b": {"micro_f1": 0.788, "macro_f1": 0.703},
        "scotus": {"micro_f1": 0.766, "macro_f1": 0.659},
        "eurlex": {"micro_f1": 0.707, "macro_f1": 0.562},
        "ledgar": {"micro_f1": 0.883, "macro_f1": 0.830},
        "unfair_tos": {"micro_f1": 0.960, "macro_f1": 0.823},
        "case_hold": {"micro_f1": 0.754, "macro_f1": None},
    },
}


def _optional_import(module_name: str, attr_name: str | None = None) -> Any:
    module = importlib.import_module(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


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


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip())
    return str(value)


def _iter_batches(items: Sequence[Any], batch_size: int) -> Iterable[Sequence[Any]]:
    if batch_size <= 0:
        yield items
        return
    for offset in range(0, len(items), batch_size):
        yield items[offset : offset + batch_size]


def _resolve_torch_device(torch: Any) -> Any:
    return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")


def _extract_multilabel_row(row: dict[str, Any], num_labels: int, label_key: str) -> list[int]:
    raw = row.get(label_key, row.get("labels", []))
    if isinstance(raw, list):
        values = [0] * num_labels
        for label in raw:
            try:
                index = int(label)
            except (TypeError, ValueError):
                continue
            if 0 <= index < num_labels:
                values[index] = 1
        return values
    return [0] * num_labels


def _extract_choice_list(row: dict[str, Any], task: BenchmarkTask) -> list[str]:
    raw = row.get(task.choices_key)
    if isinstance(raw, list) and raw:
        return [str(item) for item in raw]

    alternatives: list[str] = []
    for index in range(5):
        for key in (f"ending_{index}", f"choice_{index}", f"option_{index}"):
            value = row.get(key)
            if value is not None:
                alternatives.append(str(value))
                break
    return alternatives


def list_available_tasks() -> list[dict[str, Any]]:
    return [
        {
            "name": task.display_name,
            "task": task.hf_config,
            "task_type": task.task_type.value,
            "num_labels": task.num_labels,
            "metrics": ["micro_f1", "macro_f1"],
        }
        for task in LEXGLUE_TASKS
    ]


def normalize_task_ids(tasks: Sequence[str] | None = None) -> list[str]:
    if tasks is None:
        return [task.hf_config for task in LEXGLUE_TASKS]

    cleaned = [str(task).strip() for task in tasks if str(task).strip()]
    if not cleaned:
        return [task.hf_config for task in LEXGLUE_TASKS]

    missing = [task for task in cleaned if task not in LEXGLUE_TASKS_BY_CONFIG]
    if missing:
        available = ", ".join(sorted(LEXGLUE_TASKS_BY_CONFIG))
        unknown = ", ".join(sorted(missing))
        raise ValueError(f"Unknown task(s): {unknown}. Available tasks: {available}")

    ordered: list[str] = []
    seen: set[str] = set()
    for task in cleaned:
        if task in seen:
            continue
        seen.add(task)
        ordered.append(task)
    return ordered


def _load_test_split(task: BenchmarkTask, max_examples: int | None = None) -> list[dict[str, Any]]:
    datasets = _optional_import("datasets")
    load_dataset = getattr(datasets, "load_dataset")

    dataset = load_dataset("coastalcph/lex_glue", task.hf_config)
    split_name = "test" if "test" in dataset else "validation"
    split = dataset[split_name]

    if max_examples is not None and max_examples > 0:
        split = split.select(range(min(max_examples, len(split))))

    return [dict(example) for example in split]


def _eval_multi_class(
    model_name_or_path: str,
    task: BenchmarkTask,
    rows: list[dict[str, Any]],
    max_length: int,
    batch_size: int,
) -> dict[str, float | int]:
    np = _optional_import("numpy")
    torch = _optional_import("torch")
    transformers = _optional_import("transformers")
    metrics = _optional_import("sklearn.metrics")

    AutoModelForSequenceClassification = getattr(transformers, "AutoModelForSequenceClassification")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    f1_score = getattr(metrics, "f1_score")

    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name_or_path,
        num_labels=task.num_labels,
    )
    device = _resolve_torch_device(torch)
    model.to(device)
    model.eval()

    texts = [_normalize_text(row.get(task.text_key, row.get("text", ""))) for row in rows]
    labels: list[int] = []
    for row in rows:
        raw = row.get(task.label_key, row.get("label", 0))
        try:
            labels.append(int(raw))
        except (TypeError, ValueError):
            labels.append(0)

    prediction_values: list[int] = []
    for batch_rows in _iter_batches(texts, batch_size):
        inputs = tokenizer(
            list(batch_rows),
            max_length=max_length,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        batch_inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            logits = model(**batch_inputs).logits
        preds = np.argmax(logits.detach().cpu().numpy(), axis=-1)
        prediction_values.extend(int(value) for value in preds.tolist())

    return {
        "micro_f1": float(f1_score(labels, prediction_values, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(labels, prediction_values, average="macro", zero_division=0)),
        "samples": len(rows),
    }


def _eval_multi_label(
    model_name_or_path: str,
    task: BenchmarkTask,
    rows: list[dict[str, Any]],
    max_length: int,
    batch_size: int,
    threshold: float,
) -> dict[str, float | int]:
    np = _optional_import("numpy")
    torch = _optional_import("torch")
    transformers = _optional_import("transformers")
    metrics = _optional_import("sklearn.metrics")

    AutoModelForSequenceClassification = getattr(transformers, "AutoModelForSequenceClassification")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    f1_score = getattr(metrics, "f1_score")

    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name_or_path,
        num_labels=task.num_labels,
        problem_type="multi_label_classification",
    )
    device = _resolve_torch_device(torch)
    model.to(device)
    model.eval()

    texts = [_normalize_text(row.get(task.text_key, row.get("text", ""))) for row in rows]
    labels = [_extract_multilabel_row(row, task.num_labels, task.label_key) for row in rows]

    prediction_rows: list[list[int]] = []
    for batch_indices in _iter_batches(list(range(len(texts))), batch_size):
        batch_texts = [texts[index] for index in batch_indices]
        inputs = tokenizer(
            batch_texts,
            max_length=max_length,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        batch_inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            logits = model(**batch_inputs).logits

        probs = torch.sigmoid(logits).detach().cpu().numpy()
        for row in probs.tolist():
            prediction_rows.append([1 if float(value) >= threshold else 0 for value in row])

    y_true = np.array(labels)
    y_pred = np.array(prediction_rows)

    return {
        "micro_f1": float(f1_score(y_true, y_pred, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "samples": len(rows),
    }


def _eval_multiple_choice(
    model_name_or_path: str,
    task: BenchmarkTask,
    rows: list[dict[str, Any]],
    max_length: int,
) -> dict[str, float | int]:
    np = _optional_import("numpy")
    torch = _optional_import("torch")
    transformers = _optional_import("transformers")
    metrics = _optional_import("sklearn.metrics")

    AutoModelForMultipleChoice = getattr(transformers, "AutoModelForMultipleChoice")
    AutoTokenizer = getattr(transformers, "AutoTokenizer")
    f1_score = getattr(metrics, "f1_score")

    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
    model = AutoModelForMultipleChoice.from_pretrained(model_name_or_path)
    device = _resolve_torch_device(torch)
    model.to(device)
    model.eval()

    labels: list[int] = []
    predictions: list[int] = []

    for row in rows:
        context = _normalize_text(row.get(task.context_key, row.get("context", "")))
        choices = _extract_choice_list(row, task)
        if len(choices) < 2:
            continue

        first_sentences = [context] * len(choices)
        second_sentences = choices

        inputs = tokenizer(
            first_sentences,
            second_sentences,
            max_length=max_length,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        model_inputs = {key: value.unsqueeze(0).to(device) for key, value in inputs.items()}

        with torch.no_grad():
            logits = model(**model_inputs).logits
        prediction = int(np.argmax(logits.detach().cpu().numpy(), axis=1)[0])

        try:
            label = int(row.get(task.label_key, row.get("label", 0)))
        except (TypeError, ValueError):
            label = 0

        labels.append(label)
        predictions.append(prediction)

    if not labels:
        return {"micro_f1": 0.0, "macro_f1": 0.0, "samples": 0}

    return {
        "micro_f1": float(f1_score(labels, predictions, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(labels, predictions, average="macro", zero_division=0)),
        "samples": len(labels),
    }


def evaluate_model_on_task(
    model_name_or_path: str,
    task: BenchmarkTask,
    max_length: int = 512,
    batch_size: int = 8,
    threshold: float = 0.5,
    max_examples: int | None = None,
) -> dict[str, Any]:
    rows = _load_test_split(task, max_examples=max_examples)

    if task.task_type == TaskType.MULTI_CLASS:
        return _eval_multi_class(model_name_or_path, task, rows, max_length=max_length, batch_size=batch_size)
    if task.task_type == TaskType.MULTI_LABEL:
        return _eval_multi_label(
            model_name_or_path,
            task,
            rows,
            max_length=max_length,
            batch_size=batch_size,
            threshold=threshold,
        )
    if task.task_type == TaskType.MULTIPLE_CHOICE:
        return _eval_multiple_choice(model_name_or_path, task, rows, max_length=max_length)
    raise ValueError(f"Unsupported task type: {task.task_type}")


def _calculate_aggregate(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    micro_scores = [float(row["micro_f1"]) for row in results.values() if "micro_f1" in row]
    macro_scores = [float(row["macro_f1"]) for row in results.values() if "macro_f1" in row]

    avg_micro = sum(micro_scores) / len(micro_scores) if micro_scores else 0.0
    avg_macro = sum(macro_scores) / len(macro_scores) if macro_scores else 0.0

    return {
        "avg_micro_f1": avg_micro,
        "avg_macro_f1": avg_macro,
        "tasks_completed": len(micro_scores),
        "tasks_total": len(results),
    }


def run_full_benchmark(
    model_name_or_path: str,
    run_name: str,
    tasks: Sequence[str] | None = None,
    max_length: int = 512,
    batch_size: int = 8,
    threshold: float = 0.5,
    max_examples: int | None = None,
) -> dict[str, Any]:
    selected_ids = normalize_task_ids(tasks)
    selected_tasks = [LEXGLUE_TASKS_BY_CONFIG[task_id] for task_id in selected_ids]

    results: dict[str, dict[str, Any]] = {}
    for task in selected_tasks:
        try:
            score = evaluate_model_on_task(
                model_name_or_path=model_name_or_path,
                task=task,
                max_length=max_length,
                batch_size=batch_size,
                threshold=threshold,
                max_examples=max_examples,
            )
            results[task.hf_config] = {
                "task_name": task.display_name,
                "task": task.hf_config,
                "task_type": task.task_type.value,
                **score,
            }
        except Exception as exc:
            results[task.hf_config] = {
                "task_name": task.display_name,
                "task": task.hf_config,
                "task_type": task.task_type.value,
                "error": str(exc),
            }

    aggregate = _calculate_aggregate(results)

    return {
        "run_name": run_name,
        "model_name": model_name_or_path,
        "tasks": results,
        "aggregate": aggregate,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LexGLUE benchmark evaluation")
    parser.add_argument("--model", required=True, type=str, help="HF model id or local path")
    parser.add_argument("--run-name", default="manual-lexglue-run", type=str)
    parser.add_argument("--tasks", default="", type=str, help="Comma-separated task ids")
    parser.add_argument("--max-length", default=512, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    parser.add_argument("--threshold", default=0.5, type=float)
    parser.add_argument("--max-examples", default=None, type=int)
    parser.add_argument("--output", default="", type=str, help="Optional JSON output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()] if args.tasks else None
    payload = run_full_benchmark(
        model_name_or_path=args.model,
        run_name=args.run_name,
        tasks=tasks,
        max_length=args.max_length,
        batch_size=args.batch_size,
        threshold=args.threshold,
        max_examples=args.max_examples,
    )

    serialized = _serialize(payload)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(serialized, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
