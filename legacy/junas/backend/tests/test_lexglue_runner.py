from __future__ import annotations

from typing import Any

from ml.evaluation import lexglue_runner


def test_list_available_tasks_includes_all_lexglue_tasks() -> None:
    tasks = lexglue_runner.list_available_tasks()
    task_ids = {task["task"] for task in tasks}

    assert len(tasks) == 7
    assert {"scotus", "ledgar", "unfair_tos", "case_hold"}.issubset(task_ids)


def test_normalize_task_ids_validates_and_deduplicates() -> None:
    normalized = lexglue_runner.normalize_task_ids(["ledgar", "ledgar", "scotus"])
    assert normalized == ["ledgar", "scotus"]

    try:
        lexglue_runner.normalize_task_ids(["unknown_task"])
    except ValueError as exc:
        assert "Unknown task(s)" in str(exc)
    else:
        raise AssertionError("normalize_task_ids should fail for unknown task ids")


def test_run_full_benchmark_aggregates_task_scores(monkeypatch: Any) -> None:
    def _fake_eval(
        model_name_or_path: str,
        task: lexglue_runner.BenchmarkTask,
        max_length: int = 512,
        batch_size: int = 8,
        threshold: float = 0.5,
        max_examples: int | None = None,
    ) -> dict[str, Any]:
        del model_name_or_path, max_length, batch_size, threshold, max_examples
        if task.hf_config == "ledgar":
            return {"micro_f1": 0.88, "macro_f1": 0.83, "samples": 10}
        return {"micro_f1": 0.76, "macro_f1": 0.66, "samples": 12}

    monkeypatch.setattr(lexglue_runner, "evaluate_model_on_task", _fake_eval)

    payload = lexglue_runner.run_full_benchmark(
        model_name_or_path="nlpaueb/legal-bert-base-uncased",
        run_name="unit-test",
        tasks=["ledgar", "scotus"],
    )

    assert payload["run_name"] == "unit-test"
    assert set(payload["tasks"]) == {"ledgar", "scotus"}
    assert payload["aggregate"]["tasks_completed"] == 2
    assert payload["aggregate"]["avg_micro_f1"] == (0.88 + 0.76) / 2
