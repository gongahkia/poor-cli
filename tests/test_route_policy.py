from __future__ import annotations

from pathlib import Path

from poor_cli.models import Budget, Plan, TaskSpec
from poor_cli.route_policy import classify_task, preflight_route


def _plan(task: TaskSpec) -> Plan:
    return Plan("p", "summary", "arch", [], [], [task], [], "route", {})


def test_route_policy_classifies_small_design_and_hard_tasks() -> None:
    small = TaskSpec("t1", "Fix parser", "edit src/parser.py", risk="low")
    design = TaskSpec("t2", "Update UI", "change SwiftUI layout", task_type="design")
    hard = TaskSpec("t3", "Auth migration", "ambiguous auth migration", complexity="hard", risk="high")

    assert classify_task("goal", _plan(small), small, Budget()).policy == "direct-executor"
    assert classify_task("goal", _plan(design), design, Budget()).policy == "design-review"
    decision = classify_task("goal", _plan(hard), hard, Budget())
    assert decision.policy == "planner-reviewer"
    assert "high-risk" in decision.labels


def test_route_policy_emits_parallel_worker_jobs() -> None:
    first = TaskSpec("t1", "A", "independent file a.py")
    second = TaskSpec("t2", "B", "independent file b.py")
    plan = Plan("p", "summary", "arch", [], [], [first, second], [], "route", {})

    decision = classify_task("parallel batch", plan, first, Budget(max_parallel_agents=2))

    assert decision.policy == "plan-task"
    assert [job["task_id"] for job in decision.worker_jobs] == ["t1", "t2"]


def test_route_preflight_labels_and_selects_shim_route(tmp_path: Path) -> None:
    route = {"profile": "local", "model": "qwen", "provider_kind": "vllm", "fallbacks": []}

    preflight = preflight_route(
        "codex",
        ["exec", "fix failing tests in src/parser.py and tests/test_parser.py"],
        "tty",
        tmp_path,
        {},
        route=route,
    )

    assert preflight["selected_route"] == "graph-enriched"
    assert {"small-edit", "test-fix", "needs-graph", "multi-file-edit"} <= set(preflight["labels"])
    assert preflight["pass_through_command"] == ["codex", "exec", "fix failing tests in src/parser.py and tests/test_parser.py"]
    parser_preflight = preflight_route("codex", ["exec", "fix failing parser test"], "tty", tmp_path, {}, route=route)
    assert parser_preflight["selected_route"] == "graph-enriched"


def test_route_preflight_records_intervention_reasons(tmp_path: Path) -> None:
    route = {"profile": "openai", "model": "gpt-5.5", "provider_kind": "openai", "fallbacks": []}

    risky = preflight_route("claude", ["-p", "migrate auth schema and delete old tokens"], "tty", tmp_path, {}, route=route)
    offline = preflight_route("claude", ["-p", "review patch"], "tty", tmp_path, {"POOR_CLI_OFFLINE": "1"}, route=route)

    assert risky["selected_route"] == "planner-reviewer"
    assert risky["intervention_reason"] == "high-risk write task requires confirmation"
    assert offline["intervention_reason"] == "offline blocks network agent"


def test_route_preflight_does_not_interrupt_empty_default_fallback(tmp_path: Path) -> None:
    route = {
        "profile": "",
        "provider_kind": "",
        "reason": "fallback to first configured profile",
        "fallbacks": [{"profile": "", "reason": "missing profile"}],
    }

    preflight = preflight_route("claude", ["-p", "explain repo"], "tty", tmp_path, {}, route=route)

    assert preflight["selected_route"] == "pass-through"
    assert preflight["intervention_reason"] == ""


def test_route_preflight_retains_route_decision_vocabulary(tmp_path: Path) -> None:
    route = {"profile": "openai", "model": "gpt-5.5", "provider_kind": "openai", "fallbacks": []}
    cases = [
        ("claude", ["-p", "hello"], {}, "pass-through"),
        ("claude", ["-p", "review diff"], {}, "review-lane"),
        ("claude", ["-p", "review diff"], {"fusion": True}, "fusion-review"),
        ("claude", ["-p", "fix symbol parser"], {}, "graph-enriched"),
        ("codex", ["exec", "fix whole repo large refactor"], {}, "swarm"),
        ("claude", ["-p", "migrate auth"], {}, "planner-reviewer"),
        ("claude", ["-p", "run offline local model"], {}, "local-provider"),
    ]

    decisions = {
        preflight_route(command, args, "tty", tmp_path, {}, route={**route, **extra})["selected_route"] for command, args, extra, _ in cases
    }

    assert decisions == {expected for *_, expected in cases}
