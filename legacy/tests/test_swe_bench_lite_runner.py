from bench.swe_bench_lite.run import (
    benchmark_prompt,
    cost_from_payload,
    percentile,
    select_tasks,
)


def test_benchmark_prompt_is_problem_statement_only():
    task = {"problem_statement": "Fix the parser crash."}
    assert benchmark_prompt(task) == "Fix the parser crash."


def test_select_tasks_filters_regex_and_limit():
    tasks = [
        {"instance_id": "django__django-1"},
        {"instance_id": "sympy__sympy-2"},
        {"instance_id": "django__django-3"},
    ]
    selected = select_tasks(
        tasks,
        instance_ids=[],
        task_subset_filter=r"^django__",
        limit=1,
        shuffle=False,
        seed=0,
    )
    assert selected == [{"instance_id": "django__django-1"}]


def test_cost_from_payload_accepts_snake_and_camel_case():
    payload = {
        "cost": {
            "inputTokens": 10,
            "output_tokens": 5,
            "estimatedCost": 0.0123,
            "cacheReadInputTokens": 2,
            "cache_creation_input_tokens": 3,
        }
    }
    assert cost_from_payload(payload) == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 0,
        "cost_usd": 0.0123,
        "cache_read_input_tokens": 2,
        "cache_creation_input_tokens": 3,
    }


def test_percentile_uses_nearest_rank_for_small_sets():
    assert percentile([1.0, 2.0, 3.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0], 95) == 3.0
