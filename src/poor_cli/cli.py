from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .agents import detect_agents
from .config import (
    ConfigError,
    add_provider,
    doctor,
    explain_route,
    export_config,
    import_config,
    load_config,
    model_registry,
    parse_config_text,
    provider_preset,
    provider_rows,
    save_repo_config,
    switch_provider,
    to_toml,
)
from .hooks import load_hooks
from .mcp_client import call_mcp_tool, list_mcp_tools
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
    except ConfigError as exc:
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
    if args.command == "provider":
        return _provider(args)
    if args.command == "route":
        return _route(args)
    if args.command == "inspect":
        return _inspect(args, store)
    if args.command == "replay":
        return _replay(args, store)
    if args.command == "mcp":
        return _mcp(args)
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
    run_id, plan = Orchestrator(store, hooks=load_hooks()).plan(" ".join(args.goal), budget, graph_mode=args.graph)
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
    run_id, plan = orchestrator.plan(" ".join(args.goal), budget, graph_mode=args.graph)
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
    for run in store.list_runs(failed_only=args.failed, prompt_prefix=args.prefix):
        print(f"{run['run_id']}\t{run['status']}\t{run['created_at']}\t{run['user_goal'][:80]}")
    return 0


def _provider(args: argparse.Namespace) -> int:
    config = load_config(include_env=args.provider_command in {"list", "doctor"})
    if args.provider_command == "add":
        kind = "openai-compatible" if args.kind == "compatible" else args.kind
        profile_id = args.id or args.kind
        profile = provider_preset(
            kind,
            profile_id=profile_id,
            model=getattr(args, "model", None),
            base_url=args.base_url,
            auth_env=args.auth_env,
        )
        next_config = add_provider(config, profile_id, profile[profile_id], make_active=not args.no_switch)
        if not args.skip_verify and kind in {"openrouter", "kimi", "ollama", "vllm", "sglang"}:
            report = doctor(next_config, profile_id)
            if report["endpoint"] != "ok":
                raise ConfigError(f"provider verification failed for {profile_id}: {report.get('error') or report['endpoint']}")
            if report["model_exists"] is False:
                raise ConfigError(f"configured model was not found for {profile_id}")
            discovered = report.get("discovered_models")
            if kind == "ollama" and not args.model:
                if not isinstance(discovered, list) or not discovered:
                    raise ConfigError("ollama discovery returned no models")
                next_config["providers"][profile_id]["models"] = discovered
        path = save_repo_config(next_config)
        print(f"wrote {path}")
        return 0
    if args.provider_command == "list":
        rows = provider_rows(config)
        if args.json:
            print(json.dumps({"providers": rows}, indent=2, sort_keys=True))
            return 0
        for row in rows:
            active = "*" if row["active"] else " "
            print(
                f"{active} {row['id']}\t{row['kind']}\t{row['model']}\t{row['base_url']}\t"
                f"tools={row['tools']}\tweb={row['web']}\t{row['health']}"
            )
        return 0
    if args.provider_command == "doctor":
        profile_ids = [args.profile] if args.profile else sorted(config.get("providers", {}))
        reports = [doctor(config, profile_id) for profile_id in profile_ids]
        if args.json:
            print(json.dumps({"reports": reports}, indent=2, sort_keys=True))
            return 0
        for report in reports:
            auth = report["auth"]
            print(
                f"{report['profile']}\t{report['kind']}\tauth={auth['ref'] or 'none'} present={auth['present']}\t"
                f"endpoint={report['endpoint']}\tmodel_exists={report['model_exists']}"
            )
        return 0
    if args.provider_command == "models":
        models = model_registry(config)
        if args.json:
            print(json.dumps({"models": models}, indent=2, sort_keys=True))
            return 0
        for model in models:
            print(f"{model['alias']}\t{model['profile']}\t{model['model']}")
        return 0
    if args.provider_command == "switch":
        path = save_repo_config(switch_provider(load_config(include_env=False), args.profile))
        print(f"active provider: {args.profile}")
        print(f"wrote {path}")
        return 0
    if args.provider_command == "export":
        exported = export_config(config, args.profile)
        print(json.dumps(exported, indent=2, sort_keys=True) if args.json else to_toml(exported), end="")
        return 0
    if args.provider_command == "import":
        text = Path(args.path).read_text(encoding="utf-8") if args.path != "-" else sys.stdin.read()
        imported = parse_config_text(text, source=args.path)
        path = save_repo_config(import_config(load_config(include_env=False), imported))
        print(f"wrote {path}")
        return 0
    raise RuntimeError("missing provider command")


def _route(args: argparse.Namespace) -> int:
    config = load_config()
    if args.route_command == "explain":
        explanation = explain_route(config, " ".join(args.task), role=args.role)
        if args.json:
            print(json.dumps(explanation, indent=2, sort_keys=True))
            return 0
        print(
            f"role={explanation['role']} profile={explanation['profile']} model={explanation['model']} "
            f"provider={explanation['provider_kind']} reason={explanation['reason']}"
        )
        return 0
    raise RuntimeError("missing route command")


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


def _mcp(args: argparse.Namespace) -> int:
    if args.mcp_command == "list":
        tools = asyncio.run(list_mcp_tools(Path.cwd()))
        if args.json:
            print(json.dumps({"tools": tools}, indent=2, sort_keys=True))
            return 0
        for tool in tools:
            print(f"{tool['name']}\t{tool.get('description', '')}")
        return 0
    if args.mcp_command == "call":
        arguments = json.loads(args.args)
        if not isinstance(arguments, dict):
            raise RuntimeError("--args must decode to a JSON object")
        print(asyncio.run(call_mcp_tool(Path.cwd(), args.tool, arguments)))
        return 0
    raise RuntimeError("missing mcp command")


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
    _graph_arg(plan)
    plan.add_argument("--json", action="store_true")

    run = sub.add_parser("run")
    _goal_args(run)
    _budget_args(run)
    _graph_arg(run)
    run.add_argument("--agents")
    run.add_argument("--yes", action="store_true")
    run.add_argument("--dry-run", action="store_true")

    runs = sub.add_parser("runs")
    runs.add_argument("--failed", action="store_true")
    runs.add_argument("--prefix", help="Filter runs by goal prefix")

    provider = sub.add_parser("provider")
    provider_sub = provider.add_subparsers(dest="provider_command")
    provider_add = provider_sub.add_parser("add")
    provider_add.add_argument("kind", choices=("openai", "compatible", "openrouter", "kimi", "ollama", "vllm", "sglang"))
    provider_add.add_argument("--id")
    provider_add.add_argument("--model")
    provider_add.add_argument("--base-url")
    provider_add.add_argument("--auth-env")
    provider_add.add_argument("--no-switch", action="store_true")
    provider_add.add_argument("--skip-verify", action="store_true")
    provider_list = provider_sub.add_parser("list")
    provider_list.add_argument("--json", action="store_true")
    provider_doctor = provider_sub.add_parser("doctor")
    provider_doctor.add_argument("profile", nargs="?")
    provider_doctor.add_argument("--json", action="store_true")
    provider_models = provider_sub.add_parser("models")
    provider_models.add_argument("--json", action="store_true")
    provider_switch = provider_sub.add_parser("switch")
    provider_switch.add_argument("profile")
    provider_export = provider_sub.add_parser("export")
    provider_export.add_argument("profile", nargs="?")
    provider_export.add_argument("--json", action="store_true")
    provider_import = provider_sub.add_parser("import")
    provider_import.add_argument("path")

    route = sub.add_parser("route")
    route_sub = route.add_subparsers(dest="route_command")
    route_explain = route_sub.add_parser("explain")
    route_explain.add_argument("task", nargs="+")
    route_explain.add_argument("--role", default="executor")
    route_explain.add_argument("--json", action="store_true")

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

    mcp = sub.add_parser("mcp")
    mcp_sub = mcp.add_subparsers(dest="mcp_command")
    mcp_list = mcp_sub.add_parser("list")
    mcp_list.add_argument("--json", action="store_true")
    mcp_call = mcp_sub.add_parser("call")
    mcp_call.add_argument("tool")
    mcp_call.add_argument("--args", default="{}")

    tui = sub.add_parser("tui")
    tui.add_argument("--run-id")
    return parser


def _goal_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("goal", nargs="+")


def _budget_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--budget", type=float)
    parser.add_argument("--mode", choices=("cheap", "balanced", "best", "local-only", "manual"), default="balanced")
    parser.add_argument("--parallel", type=int, default=1)


def _graph_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--graph", action="store_true", help="Bias planning toward symbolic repo-graph navigation")
