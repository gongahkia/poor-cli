from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .agents import detect_agents
from .hooks import load_hooks
from .models import Budget, to_jsonable
from .offline import enable_offline
from .orchestrator import Orchestrator
from .replay import replay_summary, replay_verify
from .store import RunStore, StoreError


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.offline:
        enable_offline()
    if args.version:
        print(__version__)
        return 0
    if args.command is None:
        parser.print_help()
        return 0
    store = RunStore(Path(args.store_dir).expanduser() if args.store_dir else None)
    try:
        return _dispatch(args, store)
    except (RuntimeError, StoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()


def _dispatch(args: argparse.Namespace, store: RunStore) -> int:
    if args.command == "agents":
        return _agents(args)
    if args.command == "plan":
        return _plan(args, store)
    if args.command == "run":
        return _run(args, store)
    if args.command == "runs":
        return _runs(args, store)
    if args.command == "inspect":
        return _inspect(args, store)
    if args.command == "replay":
        return _replay(args, store)
    if args.command == "tui":
        return _tui(args, store)
    raise RuntimeError("missing command")


def _agents(args: argparse.Namespace) -> int:
    agents = detect_agents()
    if args.agent_command == "inspect":
        matches = [agent for agent in agents if agent.name == args.name or agent.agent_id == args.name]
        if not matches:
            raise RuntimeError(f"agent not found: {args.name}")
        print(json.dumps(to_jsonable(matches[0]), indent=2, sort_keys=True))
        return 0
    if args.agent_command == "doctor":
        for agent in agents:
            print(f"{agent.name}: {agent.command} ({agent.version})")
        return 0
    for agent in agents:
        print(f"{agent.name}\t{agent.command}\t{agent.version}")
    return 0


def _plan(args: argparse.Namespace, store: RunStore) -> int:
    budget = _budget(args)
    run_id, plan = Orchestrator(store, hooks=load_hooks()).plan(" ".join(args.goal), budget)
    if args.json:
        print(json.dumps({"run_id": run_id, "plan": to_jsonable(plan)}, indent=2, sort_keys=True))
        return 0
    print(f"run_id: {run_id}")
    print(f"summary: {plan.problem_summary}")
    for index, task in enumerate(plan.tasks, 1):
        print(f"{index}. {task.title} [{task.task_type}/{task.complexity}/{task.risk}] -> {task.suggested_agent or 'auto'}")
    return 0


def _run(args: argparse.Namespace, store: RunStore) -> int:
    budget = _budget(args)
    orchestrator = Orchestrator(store, hooks=load_hooks())
    run_id, plan = orchestrator.plan(" ".join(args.goal), budget)
    print(f"run_id: {run_id}")
    for index, task in enumerate(plan.tasks, 1):
        print(f"{index}. {task.title} -> {task.suggested_agent or 'auto'}")
    if args.dry_run:
        return orchestrator.run(run_id, budget, _selected(args), dry_run=True)
    if not args.yes:
        if not sys.stdin.isatty():
            store.set_run_status(run_id, "awaiting_confirmation", "confirmation required")
            store.append_event(run_id, "run.confirmation_required", {"reason": "non-interactive stdin"})
            raise RuntimeError("confirmation required; rerun with --yes or --dry-run")
        answer = input("Execute this plan with write-capable agents? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            store.set_run_status(run_id, "cancelled", "cancelled before execution")
            store.append_event(run_id, "run.cancelled", {"reason": "user declined execution"})
            print("cancelled")
            return 2
    return orchestrator.run(run_id, budget, _selected(args), dry_run=False)


def _runs(args: argparse.Namespace, store: RunStore) -> int:
    for run in store.list_runs(failed_only=args.failed):
        print(f"{run['run_id']}\t{run['status']}\t{run['created_at']}\t{run['user_goal'][:80]}")
    return 0


def _inspect(args: argparse.Namespace, store: RunStore) -> int:
    run = store.get_run(args.run_id)
    if args.json:
        payload: dict[str, Any] = {"run": run, "tasks": store.list_tasks(args.run_id)}
        if args.events:
            payload["events"] = store.list_events(args.run_id)
        if args.context:
            payload["context_artifacts"] = store.list_artifacts(args.run_id, "context.packet")
            payload["handoff_artifacts"] = store.list_artifacts(args.run_id, "handoff.packet")
        if args.cost:
            payload["budget"] = run.get("budget")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(f"run: {run['run_id']} [{run['status']}]")
    print(f"goal: {run['user_goal']}")
    print(f"repo: {run['repo_path']}")
    for task in store.list_tasks(args.run_id):
        if args.task and task["task_id"] != args.task:
            continue
        print(f"- {task['task_id']} {task['status']} {task['title']} -> {task.get('assigned_agent') or 'unassigned'}")
    if args.events:
        for event in store.list_events(args.run_id):
            print(f"{event['created_at']} {event['type']} {event.get('task_id') or ''}")
    if args.context:
        for artifact in store.list_artifacts(args.run_id, "context.packet"):
            print(f"context {artifact['artifact_id']} {artifact['sha256']} {artifact['size']}b")
        for artifact in store.list_artifacts(args.run_id, "handoff.packet"):
            print(f"handoff {artifact['artifact_id']} {artifact['sha256']} {artifact['size']}b")
    if args.cost:
        print(json.dumps(run.get("budget"), sort_keys=True))
    return 0


def _replay(args: argparse.Namespace, store: RunStore) -> int:
    state = replay_summary(store, args.run_id, args.from_event)
    if args.verify:
        state["verification"] = replay_verify(store, args.run_id)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    print(f"replay: {state['run_id']} [{state['status']}] events={state['event_count']}")
    for task_id, task in state["tasks"].items():
        print(f"- {task_id} {task['status']} {task['title']} -> {task.get('agent') or 'unassigned'}")
    if args.verify:
        verification = state["verification"]
        print(
            f"verified: events={verification['event_count']} artifacts={verification['artifact_count']} "
            f"bytes={verification['artifact_bytes']} trace={verification['trace_sha256']}"
        )
    return 0


def _tui(args: argparse.Namespace, store: RunStore) -> int:
    from .tui import run_tui

    run_tui(store.root, args.run_id)
    return 0


def _budget(args: argparse.Namespace) -> Budget:
    return Budget(mode=args.mode, max_usd=args.budget, max_parallel_agents=max(1, args.parallel))


def _selected(args: argparse.Namespace) -> set[str] | None:
    if not args.agents:
        return None
    return {item.strip() for item in args.agents.split(",") if item.strip()}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli")
    parser.add_argument("--store-dir", help="Override .poor-cli/v6 storage directory")
    parser.add_argument("--offline", action="store_true", help="Fail before live network-backed provider or agent calls")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")

    agents = sub.add_parser("agents")
    agents_sub = agents.add_subparsers(dest="agent_command")
    agents_sub.add_parser("doctor")
    inspect_agent = agents_sub.add_parser("inspect")
    inspect_agent.add_argument("name")

    plan = sub.add_parser("plan")
    _goal_args(plan)
    _budget_args(plan)
    plan.add_argument("--json", action="store_true")

    run = sub.add_parser("run")
    _goal_args(run)
    _budget_args(run)
    run.add_argument("--agents")
    run.add_argument("--yes", action="store_true")
    run.add_argument("--dry-run", action="store_true")

    runs = sub.add_parser("runs")
    runs.add_argument("--failed", action="store_true")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("run_id")
    inspect.add_argument("--task")
    inspect.add_argument("--events", action="store_true")
    inspect.add_argument("--context", action="store_true")
    inspect.add_argument("--cost", action="store_true")
    inspect.add_argument("--json", action="store_true")

    replay = sub.add_parser("replay")
    replay.add_argument("run_id")
    replay.add_argument("--dry", action="store_true")
    replay.add_argument("--from-event")
    replay.add_argument("--verify", action="store_true")
    replay.add_argument("--json", action="store_true")

    tui = sub.add_parser("tui")
    tui.add_argument("--run-id")
    return parser


def _goal_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("goal", nargs="+")


def _budget_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--budget", type=float)
    parser.add_argument("--mode", choices=("cheap", "balanced", "best", "local-only", "manual"), default="balanced")
    parser.add_argument("--parallel", type=int, default=1)
