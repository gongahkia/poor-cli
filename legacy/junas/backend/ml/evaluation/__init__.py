"""Model evaluation modules."""

from ml.evaluation.contract_eval import evaluate_contract_models
from ml.evaluation.lecard_eval import evaluate_lecard
from ml.evaluation.lexglue_runner import (
    LEXGLUE_TASKS,
    PUBLISHED_BASELINES,
    evaluate_model_on_task,
    list_available_tasks,
    run_full_benchmark,
)
from ml.evaluation.ner_eval import evaluate_ner_model

__all__ = [
    "evaluate_ner_model",
    "evaluate_lecard",
    "evaluate_contract_models",
    "LEXGLUE_TASKS",
    "PUBLISHED_BASELINES",
    "evaluate_model_on_task",
    "list_available_tasks",
    "run_full_benchmark",
]
