from __future__ import annotations

import asyncio
from typing import Any

from celery import shared_task

from api.config import get_settings
from api.services.benchmarks import BenchmarkService
from ml.evaluation.lexglue_runner import LEXGLUE_TASKS_BY_CONFIG, evaluate_model_on_task, normalize_task_ids


def _aggregate_task_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    micro_values = [float(payload["micro_f1"]) for payload in results.values() if "micro_f1" in payload]
    macro_values = [float(payload["macro_f1"]) for payload in results.values() if "macro_f1" in payload]
    return {
        "avg_micro_f1": (sum(micro_values) / len(micro_values)) if micro_values else 0.0,
        "avg_macro_f1": (sum(macro_values) / len(macro_values)) if macro_values else 0.0,
        "tasks_completed": len(micro_values),
        "tasks_total": len(results),
    }


@shared_task(bind=True, max_retries=0, time_limit=7200, name="api.tasks.benchmarks.run_benchmark_task")
def run_benchmark_task(
    self: Any,
    run_id: str,
    model_name: str,
    tasks: list[str] | None = None,
    max_length: int = 512,
    batch_size: int = 8,
    threshold: float = 0.5,
    max_examples: int | None = None,
) -> dict[str, Any]:
    del self

    settings = get_settings()
    service = BenchmarkService(database_url=settings.database_url)
    task_ids = normalize_task_ids(tasks)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(service.mark_run_running(run_id))

        results: dict[str, dict[str, Any]] = {}
        completed = 0

        for task_id in task_ids:
            task = LEXGLUE_TASKS_BY_CONFIG[task_id]
            try:
                score = evaluate_model_on_task(
                    model_name_or_path=model_name,
                    task=task,
                    max_length=max_length,
                    batch_size=batch_size,
                    threshold=threshold,
                    max_examples=max_examples,
                )
                row = {
                    "task": task_id,
                    "task_name": task.display_name,
                    "task_type": task.task_type.value,
                    **score,
                }
                results[task_id] = row

                loop.run_until_complete(
                    service.upsert_task_score(
                        run_id=run_id,
                        task_name=task.display_name,
                        task_config=task_id,
                        micro_f1=float(score.get("micro_f1", 0.0)),
                        macro_f1=float(score.get("macro_f1", 0.0)),
                        error=None,
                    )
                )
            except Exception as exc:
                results[task_id] = {
                    "task": task_id,
                    "task_name": task.display_name,
                    "task_type": task.task_type.value,
                    "error": str(exc),
                }
                loop.run_until_complete(
                    service.upsert_task_score(
                        run_id=run_id,
                        task_name=task.display_name,
                        task_config=task_id,
                        micro_f1=None,
                        macro_f1=None,
                        error=str(exc),
                    )
                )

            completed += 1
            loop.run_until_complete(service.update_progress(run_id, completed))

        aggregate = _aggregate_task_results(results)
        payload = {
            "run_id": run_id,
            "model_name": model_name,
            "tasks": results,
            "aggregate": aggregate,
        }
        loop.run_until_complete(service.complete_run(run_id, payload))
        return payload
    except Exception as exc:
        try:
            loop.run_until_complete(service.fail_run(run_id, str(exc)))
        except Exception:
            pass
        raise
    finally:
        asyncio.set_event_loop(None)
        loop.close()
