from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator, Sequence

from ml.evaluation.lexglue_runner import (
    LEXGLUE_TASKS_BY_CONFIG,
    PUBLISHED_BASELINES,
    list_available_tasks,
    normalize_task_ids,
)


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


def _parse_json_like(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def _task_display_name(task_config: str) -> str:
    task = LEXGLUE_TASKS_BY_CONFIG.get(task_config)
    if task is None:
        return task_config
    return task.display_name


def _aggregate_from_task_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    micro_values = [float(item["micro_f1"]) for item in results.values() if "micro_f1" in item]
    macro_values = [float(item["macro_f1"]) for item in results.values() if "macro_f1" in item]

    return {
        "avg_micro_f1": (sum(micro_values) / len(micro_values)) if micro_values else 0.0,
        "avg_macro_f1": (sum(macro_values) / len(macro_values)) if macro_values else 0.0,
        "tasks_completed": len(micro_values),
        "tasks_total": len(results),
    }


def _baseline_results_payload(scores: dict[str, dict[str, float | None]]) -> dict[str, Any]:
    tasks: dict[str, dict[str, Any]] = {}
    for task_config, metrics in scores.items():
        task = LEXGLUE_TASKS_BY_CONFIG.get(task_config)
        payload: dict[str, Any] = {
            "task": task_config,
            "task_name": task.display_name if task else task_config,
            "task_type": task.task_type.value if task else "unknown",
        }
        if metrics.get("micro_f1") is not None:
            payload["micro_f1"] = float(metrics["micro_f1"])  # type: ignore[arg-type]
        if metrics.get("macro_f1") is not None:
            payload["macro_f1"] = float(metrics["macro_f1"])  # type: ignore[arg-type]
        tasks[task_config] = payload

    aggregate = _aggregate_from_task_results(tasks)
    return {"tasks": tasks, "aggregate": aggregate}


class BenchmarkService:
    def __init__(
        self,
        database_url: str,
        pg_pool: Any | None = None,
        celery_app: Any | None = None,
        celery_task_name: str = "api.tasks.benchmarks.run_benchmark_task",
        celery_queue: str = "junas",
    ):
        self.database_url = database_url
        self.pg_pool = pg_pool
        self.celery_app = celery_app
        self.celery_task_name = celery_task_name
        self.celery_queue = celery_queue

    async def _connect(self) -> Any:
        if self.pg_pool is not None:
            return None

        import asyncpg

        return await asyncpg.connect(_database_url_for_asyncpg(self.database_url))

    @asynccontextmanager
    async def _acquire(self) -> AsyncIterator[Any]:
        if self.pg_pool is not None:
            async with self.pg_pool.acquire() as connection:
                yield connection
            return

        connection = await self._connect()
        try:
            yield connection
        finally:
            if connection is not None:
                await connection.close()

    async def list_tasks(self) -> list[dict[str, Any]]:
        return list_available_tasks()

    async def seed_published_baselines(self) -> None:
        try:
            async with self._acquire() as connection:
                for run_name, score_map in PUBLISHED_BASELINES.items():
                    existing = await connection.fetchval(
                        """
                        SELECT id FROM benchmark_runs
                        WHERE run_name = $1 AND is_published_baseline = TRUE
                        LIMIT 1
                        """,
                        run_name,
                    )
                    if existing is not None:
                        continue

                    payload = _baseline_results_payload(score_map)
                    aggregate = payload["aggregate"]
                    tasks = payload["tasks"]

                    async with connection.transaction():
                        run_id = await connection.fetchval(
                            """
                            INSERT INTO benchmark_runs(
                                run_name,
                                model_name,
                                model_path,
                                status,
                                requested_tasks,
                                results,
                                is_published_baseline,
                                tasks_completed,
                                tasks_total,
                                avg_micro_f1,
                                avg_macro_f1,
                                started_at,
                                completed_at,
                                updated_at
                            )
                            VALUES(
                                $1,
                                $2,
                                $3,
                                $4,
                                $5::jsonb,
                                $6::jsonb,
                                TRUE,
                                $7,
                                $8,
                                $9,
                                $10,
                                NOW(),
                                NOW(),
                                NOW()
                            )
                            RETURNING id
                            """,
                            run_name,
                            run_name,
                            None,
                            "completed",
                            json.dumps(sorted(tasks.keys())),
                            json.dumps(_serialize({"tasks": tasks, "aggregate": aggregate})),
                            int(aggregate["tasks_completed"]),
                            int(aggregate["tasks_total"]),
                            float(aggregate["avg_micro_f1"]),
                            float(aggregate["avg_macro_f1"]),
                        )

                        for task_config, result in tasks.items():
                            await connection.execute(
                                """
                                INSERT INTO benchmark_scores(
                                    run_id,
                                    task_name,
                                    task_config,
                                    micro_f1,
                                    macro_f1,
                                    error
                                )
                                VALUES($1, $2, $3, $4, $5, NULL)
                                """,
                                run_id,
                                result["task_name"],
                                task_config,
                                result.get("micro_f1"),
                                result.get("macro_f1"),
                            )
        except Exception:
            return

    async def create_run(
        self,
        model_name: str,
        run_name: str,
        tasks: Sequence[str] | None = None,
        model_path: str | None = None,
    ) -> dict[str, Any]:
        task_ids = normalize_task_ids(tasks)

        async with self._acquire() as connection:
            run_id = await connection.fetchval(
                """
                INSERT INTO benchmark_runs(
                    run_name,
                    model_name,
                    model_path,
                    status,
                    requested_tasks,
                    tasks_total,
                    tasks_completed,
                    created_at,
                    updated_at
                )
                VALUES($1, $2, $3, 'pending', $4::jsonb, $5, 0, NOW(), NOW())
                RETURNING id
                """,
                run_name,
                model_name,
                model_path,
                json.dumps(task_ids),
                len(task_ids),
            )

        if self.celery_app is None:
            await self.fail_run(run_id=str(run_id), error="Celery is unavailable")
            return {
                "run_id": str(run_id),
                "status": "failed",
                "message": "Benchmark run could not be queued: Celery unavailable",
            }

        try:
            self.celery_app.send_task(
                self.celery_task_name,
                kwargs={
                    "run_id": str(run_id),
                    "model_name": model_name,
                    "tasks": task_ids,
                },
                queue=self.celery_queue,
            )
        except Exception as exc:
            await self.fail_run(run_id=str(run_id), error=f"Queueing failed: {exc}")
            return {
                "run_id": str(run_id),
                "status": "failed",
                "message": f"Benchmark run could not be queued: {exc}",
            }

        return {
            "run_id": str(run_id),
            "status": "pending",
            "message": "Benchmark run queued",
        }

    async def register_run_result(
        self,
        model_name: str,
        run_name: str,
        task: str,
        micro_f1: float,
        macro_f1: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_task = normalize_task_ids([task])[0]
        task_name = _task_display_name(normalized_task)
        metadata_payload = metadata or {}

        async with self._acquire() as connection:
            existing = await connection.fetchrow(
                """
                SELECT id
                FROM benchmark_runs
                WHERE run_name = $1
                  AND model_name = $2
                  AND is_published_baseline = FALSE
                ORDER BY created_at DESC
                LIMIT 1
                """,
                run_name,
                model_name,
            )

            run_id = (
                existing["id"]
                if existing is not None
                else await connection.fetchval(
                    """
                    INSERT INTO benchmark_runs(
                        run_name,
                        model_name,
                        status,
                        requested_tasks,
                        tasks_total,
                        tasks_completed,
                        started_at,
                        completed_at,
                        created_at,
                        updated_at
                    )
                    VALUES($1, $2, 'completed', '[]'::jsonb, 0, 0, NOW(), NOW(), NOW(), NOW())
                    RETURNING id
                    """,
                    run_name,
                    model_name,
                )
            )

            await connection.execute(
                """
                INSERT INTO benchmark_scores(run_id, task_name, task_config, micro_f1, macro_f1, error)
                VALUES($1, $2, $3, $4, $5, NULL)
                ON CONFLICT (run_id, task_config)
                DO UPDATE
                SET task_name = EXCLUDED.task_name,
                    micro_f1 = EXCLUDED.micro_f1,
                    macro_f1 = EXCLUDED.macro_f1,
                    error = NULL
                """,
                run_id,
                task_name,
                normalized_task,
                float(micro_f1),
                float(macro_f1) if macro_f1 is not None else None,
            )

            score_rows = await connection.fetch(
                """
                SELECT task_name, task_config, micro_f1, macro_f1
                FROM benchmark_scores
                WHERE run_id = $1
                ORDER BY task_config ASC
                """,
                run_id,
            )

            task_results: dict[str, dict[str, Any]] = {}
            for row in score_rows:
                task_payload: dict[str, Any] = {
                    "task": row["task_config"],
                    "task_name": row["task_name"],
                }
                if row["micro_f1"] is not None:
                    task_payload["micro_f1"] = float(row["micro_f1"])
                if row["macro_f1"] is not None:
                    task_payload["macro_f1"] = float(row["macro_f1"])
                task_results[str(row["task_config"])] = task_payload

            aggregate = _aggregate_from_task_results(task_results)
            result_payload = {
                "tasks": task_results,
                "aggregate": aggregate,
                "metadata": metadata_payload,
            }

            await connection.execute(
                """
                UPDATE benchmark_runs
                SET
                    status = 'completed',
                    requested_tasks = $2::jsonb,
                    results = $3::jsonb,
                    avg_micro_f1 = $4,
                    avg_macro_f1 = $5,
                    tasks_completed = $6,
                    tasks_total = $7,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
                json.dumps(sorted(task_results.keys())),
                json.dumps(_serialize(result_payload), ensure_ascii=False),
                float(aggregate["avg_micro_f1"]),
                float(aggregate["avg_macro_f1"]),
                int(aggregate["tasks_completed"]),
                int(aggregate["tasks_total"]),
            )

        return {
            "run_id": str(run_id),
            "run_name": run_name,
            "model_name": model_name,
            "task": normalized_task,
            "status": "completed",
            "aggregate": aggregate,
        }

    async def mark_run_running(self, run_id: str) -> None:
        async with self._acquire() as connection:
            await connection.execute(
                """
                UPDATE benchmark_runs
                SET status = 'running', started_at = NOW(), updated_at = NOW()
                WHERE id = $1::uuid
                """,
                run_id,
            )

    async def update_progress(self, run_id: str, tasks_completed: int) -> None:
        async with self._acquire() as connection:
            await connection.execute(
                """
                UPDATE benchmark_runs
                SET tasks_completed = $2, updated_at = NOW()
                WHERE id = $1::uuid
                """,
                run_id,
                tasks_completed,
            )

    async def upsert_task_score(
        self,
        run_id: str,
        task_name: str,
        task_config: str,
        micro_f1: float | None,
        macro_f1: float | None,
        error: str | None,
    ) -> None:
        async with self._acquire() as connection:
            await connection.execute(
                """
                INSERT INTO benchmark_scores(run_id, task_name, task_config, micro_f1, macro_f1, error)
                VALUES($1::uuid, $2, $3, $4, $5, $6)
                ON CONFLICT (run_id, task_config)
                DO UPDATE
                SET task_name = EXCLUDED.task_name,
                    micro_f1 = EXCLUDED.micro_f1,
                    macro_f1 = EXCLUDED.macro_f1,
                    error = EXCLUDED.error
                """,
                run_id,
                task_name,
                task_config,
                micro_f1,
                macro_f1,
                error,
            )

    async def complete_run(self, run_id: str, results: dict[str, Any]) -> None:
        aggregate_raw = results.get("aggregate", {})
        aggregate = _parse_json_like(aggregate_raw, {})

        async with self._acquire() as connection:
            await connection.execute(
                """
                UPDATE benchmark_runs
                SET
                    status = 'completed',
                    results = $2::jsonb,
                    avg_micro_f1 = $3,
                    avg_macro_f1 = $4,
                    tasks_completed = $5,
                    tasks_total = $6,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1::uuid
                """,
                run_id,
                json.dumps(_serialize(results), ensure_ascii=False),
                float(aggregate.get("avg_micro_f1", 0.0)),
                float(aggregate.get("avg_macro_f1", 0.0)),
                int(aggregate.get("tasks_completed", 0)),
                int(aggregate.get("tasks_total", 0)),
            )

    async def fail_run(self, run_id: str, error: str) -> None:
        async with self._acquire() as connection:
            await connection.execute(
                """
                UPDATE benchmark_runs
                SET status = 'failed', error = $2, completed_at = NOW(), updated_at = NOW()
                WHERE id = $1::uuid
                """,
                run_id,
                error,
            )

    async def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self._acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    id,
                    run_name,
                    model_name,
                    status,
                    tasks_completed,
                    tasks_total,
                    avg_micro_f1,
                    avg_macro_f1,
                    completed_at,
                    is_published_baseline,
                    created_at
                FROM benchmark_runs
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )

        output: list[dict[str, Any]] = []
        for row in rows:
            output.append(
                {
                    "run_id": str(row["id"]),
                    "run_name": row["run_name"],
                    "model_name": row["model_name"],
                    "status": row["status"],
                    "tasks_completed": int(row["tasks_completed"] or 0),
                    "tasks_total": int(row["tasks_total"] or 0),
                    "avg_micro_f1": float(row["avg_micro_f1"]) if row["avg_micro_f1"] is not None else None,
                    "avg_macro_f1": float(row["avg_macro_f1"]) if row["avg_macro_f1"] is not None else None,
                    "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                    "is_published_baseline": bool(row["is_published_baseline"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
            )
        return output

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        async with self._acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    id,
                    run_name,
                    model_name,
                    model_path,
                    status,
                    requested_tasks,
                    results,
                    error,
                    tasks_completed,
                    tasks_total,
                    avg_micro_f1,
                    avg_macro_f1,
                    is_published_baseline,
                    started_at,
                    completed_at,
                    created_at,
                    updated_at
                FROM benchmark_runs
                WHERE id = $1::uuid
                LIMIT 1
                """,
                run_id,
            )
            if row is None:
                return None

            scores = await connection.fetch(
                """
                SELECT task_name, task_config, micro_f1, macro_f1, error
                FROM benchmark_scores
                WHERE run_id = $1::uuid
                ORDER BY task_config ASC
                """,
                run_id,
            )

        score_rows: list[dict[str, Any]] = []
        score_map: dict[str, dict[str, Any]] = {}
        for score in scores:
            payload = {
                "task_name": score["task_name"],
                "task": score["task_config"],
                "micro_f1": float(score["micro_f1"]) if score["micro_f1"] is not None else None,
                "macro_f1": float(score["macro_f1"]) if score["macro_f1"] is not None else None,
                "error": score["error"],
            }
            score_rows.append(payload)
            score_map[score["task_config"]] = {
                "task_name": score["task_name"],
                "task": score["task_config"],
                **({"micro_f1": payload["micro_f1"]} if payload["micro_f1"] is not None else {}),
                **({"macro_f1": payload["macro_f1"]} if payload["macro_f1"] is not None else {}),
                **({"error": payload["error"]} if payload["error"] else {}),
            }

        requested_tasks = _parse_json_like(row["requested_tasks"], [])
        result_payload = _parse_json_like(row["results"], None)
        if result_payload is None:
            aggregate = {
                "avg_micro_f1": float(row["avg_micro_f1"]) if row["avg_micro_f1"] is not None else 0.0,
                "avg_macro_f1": float(row["avg_macro_f1"]) if row["avg_macro_f1"] is not None else 0.0,
                "tasks_completed": int(row["tasks_completed"] or 0),
                "tasks_total": int(row["tasks_total"] or len(score_map)),
            }
            result_payload = {"tasks": score_map, "aggregate": aggregate}

        return {
            "run_id": str(row["id"]),
            "run_name": row["run_name"],
            "model_name": row["model_name"],
            "model_path": row["model_path"],
            "status": row["status"],
            "requested_tasks": requested_tasks,
            "results": result_payload,
            "scores": score_rows,
            "error": row["error"],
            "tasks_completed": int(row["tasks_completed"] or 0),
            "tasks_total": int(row["tasks_total"] or 0),
            "avg_micro_f1": float(row["avg_micro_f1"]) if row["avg_micro_f1"] is not None else None,
            "avg_macro_f1": float(row["avg_macro_f1"]) if row["avg_macro_f1"] is not None else None,
            "is_published_baseline": bool(row["is_published_baseline"]),
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    async def leaderboard(
        self,
        task: str | None = None,
        sort_by: str = "avg_micro_f1",
    ) -> dict[str, Any]:
        task_filter = task.strip() if task else None
        if task_filter:
            normalize_task_ids([task_filter])

        async with self._acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    id,
                    run_name,
                    model_name,
                    status,
                    results,
                    avg_micro_f1,
                    avg_macro_f1,
                    tasks_completed,
                    tasks_total,
                    is_published_baseline,
                    completed_at,
                    created_at
                FROM benchmark_runs
                WHERE status = 'completed'
                ORDER BY created_at DESC
                """
            )

        entries: list[dict[str, Any]] = []
        baseline_entries: list[dict[str, Any]] = []

        for row in rows:
            results = _parse_json_like(row["results"], {})
            task_results = _parse_json_like(results.get("tasks"), {})
            score_map: dict[str, float] = {}
            for task_config, task_payload in task_results.items():
                parsed = _parse_json_like(task_payload, {})
                micro = parsed.get("micro_f1")
                if micro is not None:
                    score_map[str(task_config)] = float(micro)

            avg_micro = float(row["avg_micro_f1"]) if row["avg_micro_f1"] is not None else 0.0
            avg_macro = float(row["avg_macro_f1"]) if row["avg_macro_f1"] is not None else 0.0

            row_payload = {
                "run_id": str(row["id"]),
                "run_name": row["run_name"],
                "model_name": row["model_name"],
                "avg_micro_f1": avg_micro,
                "avg_macro_f1": avg_macro,
                "task_scores": score_map,
                "tasks_completed": int(row["tasks_completed"] or 0),
                "tasks_total": int(row["tasks_total"] or 0),
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "is_published_baseline": bool(row["is_published_baseline"]),
            }

            if row_payload["is_published_baseline"]:
                baseline_entries.append(row_payload)
            else:
                entries.append(row_payload)

        metric_name = task_filter or sort_by

        def ranking_value(entry: dict[str, Any]) -> float:
            if task_filter is not None:
                return float(entry["task_scores"].get(task_filter, -1.0))
            if metric_name in {"avg_micro_f1", "avg_macro_f1"}:
                return float(entry.get(metric_name, -1.0))
            if metric_name in LEXGLUE_TASKS_BY_CONFIG:
                return float(entry["task_scores"].get(metric_name, -1.0))
            return float(entry.get("avg_micro_f1", -1.0))

        entries.sort(key=ranking_value, reverse=True)
        for index, entry in enumerate(entries, start=1):
            entry["rank"] = index

        baseline_entries.sort(key=lambda item: item["run_name"])
        baselines = [
            {
                "name": entry["run_name"],
                "source": "Chalkidis et al., ACL 2022",
                "task_scores": entry["task_scores"],
            }
            for entry in baseline_entries
        ]

        if not baselines:
            baselines = []
            for run_name, baseline_scores in PUBLISHED_BASELINES.items():
                task_scores: dict[str, float] = {}
                for task_config, metrics in baseline_scores.items():
                    micro = metrics.get("micro_f1")
                    if micro is None:
                        continue
                    task_scores[task_config] = float(micro)

                baselines.append(
                    {
                        "name": run_name,
                        "source": "Chalkidis et al., ACL 2022",
                        "task_scores": task_scores,
                    }
                )

        return {
            "leaderboard": entries,
            "baselines": baselines,
            "task_labels": {task_id: _task_display_name(task_id) for task_id in LEXGLUE_TASKS_BY_CONFIG},
            "generated_at": datetime.now(UTC).isoformat(),
        }
