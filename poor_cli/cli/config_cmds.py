"""Configuration and diagnostics CLI subcommands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from ..config import Config, ConfigManager


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _load_cli_config(config_path_hint: str | None = None) -> Config:
    manager = ConfigManager(config_path=Path(config_path_hint).expanduser() if config_path_hint else None)
    return manager.load() if manager.config_path.exists() else Config()


def _core_cls():
    from ..core import PoorCLICore
    return PoorCLICore


def run_config_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli config")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_get = sub.add_parser("get")
    p_get.add_argument("key")
    p_get.add_argument("--json", action="store_true")
    p_set = sub.add_parser("set")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.add_argument("--json", action="store_true")
    p_toggle = sub.add_parser("toggle")
    p_toggle.add_argument("key")
    p_toggle.add_argument("--json", action="store_true")
    p_permissions = sub.add_parser("permissions")
    permissions_sub = p_permissions.add_subparsers(dest="permissions_command", required=True)
    permissions_sub.add_parser("show").add_argument("--json", action="store_true")
    permissions_sub.add_parser("validate").add_argument("--json", action="store_true")
    p_explain = permissions_sub.add_parser("explain")
    p_explain.add_argument("tool")
    p_explain.add_argument("--input", default="")
    p_explain.add_argument("--provider", default="")
    p_explain.add_argument("--model", default="")
    p_explain.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    manager = ConfigManager()
    config = manager.load() if manager.config_path.exists() else Config()
    if args.subcommand == "list":
        payload = config.to_dict() if hasattr(config, "to_dict") else {}
        if args.json:
            _print_json(payload)
        else:
            for k, v in payload.items():
                print(f"  {k}: {v}")
        return 0
    if args.subcommand == "get":
        parts = args.key.split(".")
        obj: Any = config
        for p in parts:
            obj = getattr(obj, p, None)
            if obj is None:
                raise SystemExit(f"Unknown config key: {args.key}")
        if args.json:
            _print_json({"key": args.key, "value": obj})
        else:
            print(obj)
        return 0
    if args.subcommand == "set":
        parts = args.key.split(".")
        obj: Any = config
        for p in parts[:-1]:
            obj = getattr(obj, p, None)
            if obj is None:
                raise SystemExit(f"Unknown config key: {args.key}")
        current = getattr(obj, parts[-1], None)
        if current is None:
            raise SystemExit(f"Unknown config key: {args.key}")
        if isinstance(current, bool):
            value: Any = args.value.lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            value = int(args.value)
        elif isinstance(current, float):
            value = float(args.value)
        else:
            value = args.value
        setattr(obj, parts[-1], value)
        manager.config = config
        manager.save()
        if args.json:
            _print_json({"key": args.key, "value": value})
        else:
            print(f"{args.key} = {value}")
        return 0
    if args.subcommand == "toggle":
        parts = args.key.split(".")
        obj: Any = config
        for p in parts[:-1]:
            obj = getattr(obj, p, None)
            if obj is None:
                raise SystemExit(f"Unknown config key: {args.key}")
        current = getattr(obj, parts[-1], None)
        if not isinstance(current, bool):
            raise SystemExit(f"Config key {args.key} is not boolean (got {type(current).__name__})")
        new_value = not current
        setattr(obj, parts[-1], new_value)
        manager.config = config
        manager.save()
        if args.json:
            _print_json({"key": args.key, "value": new_value})
        else:
            print(f"{args.key} = {new_value}")
        return 0
    if args.subcommand == "permissions":
        from ..permission_dsl import PermissionDsl, input_from_cli
        dsl = PermissionDsl(Path.cwd())
        if args.permissions_command == "show":
            payload = dsl.show()
            if args.json:
                _print_json(payload)
            else:
                _print_json(payload)
            return 1 if payload.get("errors") else 0
        if args.permissions_command == "validate":
            errors = dsl.errors()
            payload = {"ok": not errors, "errors": errors}
            if args.json:
                _print_json(payload)
            else:
                print("permissions.yml ok" if not errors else "permissions.yml has errors")
                for error in errors:
                    print(f"  {error}")
            return 0 if not errors else 1
        if args.permissions_command == "explain":
            payload = dsl.explain(
                args.tool,
                input_from_cli(args.tool, args.input),
                context={"provider": args.provider, "model": args.model},
            )
            if args.json:
                _print_json(payload)
            else:
                _print_json(payload)
            return 0
    raise SystemExit(f"Unknown config subcommand: {args.subcommand}")


def run_profile_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli profile")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_apply = sub.add_parser("apply")
    p_apply.add_argument("name")
    p_apply.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from ..profiles import ProfileManager
    mgr = ProfileManager()
    if args.subcommand == "list":
        profiles = mgr.list_profiles()
        payload = [p.to_dict() for p in profiles]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No profiles found.")
            for p in payload:
                print(f"  {p['name']:15s} {p['description']} ({p['source']})")
        return 0
    if args.subcommand == "apply":
        config = _load_cli_config()
        mgr.apply_to_config(config, args.name)
        cm = ConfigManager()
        cm.config = config
        cm.save()
        if args.json:
            _print_json({"applied": args.name})
        else:
            print(f"Profile '{args.name}' applied.")
        return 0
    raise SystemExit(f"Unknown profile subcommand: {args.subcommand}")


def run_trust_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli trust")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("status")
    p_add = sub.add_parser("trust")
    p_add.add_argument("--path")
    p_rm = sub.add_parser("untrust")
    p_rm.add_argument("--path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from ..trust import TrustManager
    mgr = TrustManager()
    cmd = args.subcommand or "status"
    if cmd == "status":
        payload = mgr.to_dict()
        if args.json:
            _print_json(payload)
        else:
            trusted = payload.get("trusted", [])
            current = payload.get("currentRepo", "")
            is_trusted = payload.get("currentRepoTrusted", False)
            print(f"Current repo: {current} ({'trusted' if is_trusted else 'not trusted'})")
            if trusted:
                for t in trusted:
                    print(f"  {t}")
            else:
                print("  No trusted repos.")
        return 0
    if cmd == "trust":
        canonical = mgr.trust(getattr(args, "path", None))
        payload = {"trusted": True, "path": canonical}
        if args.json:
            _print_json(payload)
        else:
            print(f"Trusted: {canonical}")
        return 0
    if cmd == "untrust":
        removed = mgr.untrust(getattr(args, "path", None))
        path = getattr(args, "path", None) or str(Path.cwd())
        payload = {"untrusted": removed, "path": path}
        if args.json:
            _print_json(payload)
        else:
            print(f"Untrusted: {path}" if removed else f"Not trusted: {path}")
        return 0
    raise SystemExit(f"Unknown trust subcommand: {cmd}")

def run_core_info_command(method_name: str, argv: Sequence[str], prog: str) -> int:
    """Generic handler for core info queries (doctor, status, policy, tools, mcp, cost)."""
    import asyncio

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--config", help="config file path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    minimal_methods = {
        "build_doctor_report",
        "build_status_view",
        "get_policy_status",
        "get_available_tools",
        "get_mcp_status",
    }
    minimal_init = method_name in minimal_methods

    async def _query():
        core = _core_cls()(config_path=Path(args.config).expanduser() if args.config else None)
        await core.initialize(minimal=minimal_init)
        try:
            return getattr(core, method_name)()
        finally:
            await core.shutdown()
    result = asyncio.run(_query())
    if args.json:
        _print_json(result)
    else:
        _print_json(result)
    return 0


def run_cost_mode(argv: Sequence[str]) -> int:
    import asyncio

    parser = argparse.ArgumentParser(prog="poor-cli cost")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("summary")
    p_economy = sub.add_parser("economy")
    p_economy.add_argument("preset", nargs="?", choices=("frugal", "balanced", "quality"))
    sub.add_parser("savings")
    sub.add_parser("export")
    p_history = sub.add_parser("history")
    p_history.add_argument("--limit", type=int, default=50)
    sub.add_parser("tokens") # token visualization
    sub.add_parser("cache-stats")
    sub.add_parser("cache-clear")
    p_budget = sub.add_parser("budget")
    p_budget.add_argument("template", nargs="?", help="quick_question|code_review|deep_refactor|unlimited")
    # cost pressure + cost breakdown removed — use `poor-cli context pressure|breakdown`.
    p_compare = sub.add_parser("compare")
    p_compare.add_argument("provider", nargs="?")
    p_compare.add_argument("model", nargs="?")
    sub.add_parser("templates") # list budget templates
    parser.add_argument("--config", help="config file path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    cmd = args.subcommand or "summary"
    # history and templates don't need a running core
    if cmd == "history":
        entries = _core_cls().get_cost_history(getattr(args, "limit", 50))
        total = sum(e.get("cost_usd", 0) for e in entries)
        _print_json({"entries": entries, "count": len(entries), "total_cost_usd": round(total, 6)})
        return 0
    if cmd == "templates":
        _print_json(_core_cls().list_budget_templates())
        return 0
    async def _run():
        core = _core_cls()(config_path=Path(args.config).expanduser() if getattr(args, "config", None) else None)
        await core.initialize()
        try:
            if cmd == "summary":
                return core.get_session_cost_summary()
            if cmd == "savings":
                return core.get_economy_savings()
            if cmd == "export":
                return core.export_cost_report()
            if cmd == "economy":
                preset = getattr(args, "preset", None)
                if preset:
                    return core.set_economy_preset(preset)
                return {"current_preset": getattr(core.config, "economy_preset", "balanced")}
            if cmd == "tokens":
                return core.get_tokens_visualization()
            if cmd == "cache-stats":
                return core.get_cache_stats()
            if cmd == "cache-clear":
                return core.clear_semantic_cache()
            if cmd == "budget":
                template = getattr(args, "template", None)
                if template:
                    return core.apply_budget_template(template)
                return {"templates": list(_core_cls().list_budget_templates().keys())}
            if cmd == "compare":
                provider = getattr(args, "provider", None)
                model = getattr(args, "model", None)
                if not provider or not model:
                    return {"error": "usage: poor-cli cost compare <provider> <model>"}
                return core.compare_model_cost(provider, model)
        finally:
            await core.shutdown()
        return {}
    result = asyncio.run(_run())
    _print_json(result)
    return 0


def run_context_mode(argv: Sequence[str]) -> int:
    import asyncio

    parser = argparse.ArgumentParser(prog="poor-cli context")
    sub = parser.add_subparsers(dest="subcommand")
    p_compact = sub.add_parser("compact")
    p_compact.add_argument(
        "strategy",
        nargs="?",
        default="auto",
        choices=("auto", "compact", "compress", "handoff", "gentle", "aggressive"),
    )
    p_preview = sub.add_parser("preview")
    p_pressure = sub.add_parser("pressure")
    p_breakdown = sub.add_parser("breakdown")
    p_init = sub.add_parser("init", help="create file-first context substrate")
    p_doctor = sub.add_parser("doctor", help="validate context substrate files")
    p_map = sub.add_parser("map", help="show context substrate file map")
    p_append = sub.add_parser("append", help="append a record to a context JSONL file")
    p_append.add_argument("file", choices=("decisions.jsonl", "failures.jsonl", "runs.jsonl"))
    p_append.add_argument("--record", required=True, help="JSON object to append")
    for subparser in (p_compact, p_preview, p_pressure, p_breakdown, p_init, p_doctor, p_map, p_append):
        subparser.add_argument("--json", action="store_true")
    parser.add_argument("--config", help="config file path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    cmd = args.subcommand or "preview"
    if cmd in {"init", "doctor", "map", "append"}:
        from ..context_substrate import append_jsonl_record, context_map, doctor_context, init_context
        if cmd == "init":
            result = init_context(Path.cwd())
        elif cmd == "doctor":
            result = doctor_context(Path.cwd())
        elif cmd == "map":
            result = context_map(Path.cwd())
        else:
            try:
                record = json.loads(args.record)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"--record must be JSON object: {exc}") from exc
            if not isinstance(record, dict):
                raise SystemExit("--record must be JSON object")
            result = append_jsonl_record(args.file, record, repo_root=Path.cwd())
        _print_json(result)
        return 0
    async def _run():
        core = _core_cls()(config_path=Path(args.config).expanduser() if getattr(args, "config", None) else None)
        await core.initialize()
        try:
            if cmd == "compact":
                return await core.compact_context(getattr(args, "strategy", "auto"))
            if cmd == "preview":
                return await core.preview_context(message="", context_files=[], pinned_context_files=[])
            if cmd == "pressure":
                return core.get_context_pressure()
            if cmd == "breakdown":
                return core.get_context_breakdown()
        finally:
            await core.shutdown()
        return {}
    result = asyncio.run(_run())
    _print_json(result)
    return 0


def run_workflow_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli workflow")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("list")
    p_get = sub.add_parser("get")
    p_get.add_argument("name")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    cmd = args.subcommand or "list"
    from ..automations import get_workflow_template, list_workflow_templates
    if cmd == "list":
        templates = list_workflow_templates()
        _print_json([{"name": t.name, "description": t.description} for t in templates])
    elif cmd == "get":
        tmpl = get_workflow_template(args.name)
        if tmpl:
            _print_json({"name": tmpl.name, "description": tmpl.description, "steps": tmpl.steps})
        else:
            _print_json({"error": f"workflow '{args.name}' not found"})
    return 0


def run_services_mode(argv: Sequence[str]) -> int:
    import asyncio

    parser = argparse.ArgumentParser(prog="poor-cli services")
    sub = parser.add_subparsers(dest="subcommand")
    p_start = sub.add_parser("start")
    p_start.add_argument("name")
    p_start.add_argument("command")
    p_stop = sub.add_parser("stop")
    p_stop.add_argument("name")
    p_status = sub.add_parser("status")
    p_status.add_argument("name")
    p_logs = sub.add_parser("logs")
    p_logs.add_argument("name")
    parser.add_argument("--config", help="config file path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    cmd = args.subcommand
    if not cmd:
        print("usage: poor-cli services [start|stop|status|logs] <name>")
        return 1
    async def _run():
        core = _core_cls()(config_path=Path(args.config).expanduser() if getattr(args, "config", None) else None)
        await core.initialize()
        try:
            if cmd == "start":
                return await core.start_service(args.name, args.command)
            if cmd == "stop":
                return await core.stop_service(args.name)
            if cmd == "status":
                return await core.get_service_status(args.name)
            if cmd == "logs":
                return await core.get_service_logs(args.name)
        finally:
            await core.shutdown()
        return {}
    result = asyncio.run(_run())
    _print_json(result)
    return 0


def run_search_mode(argv: Sequence[str]) -> int:
    import asyncio

    parser = argparse.ArgumentParser(prog="poor-cli search")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--mode", choices=("semantic", "hybrid"), default="hybrid")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("index")
    sub.add_parser("stats")
    args = parser.parse_args(list(argv))
    from ..indexer import CodebaseIndexer
    async def _run():
        indexer = CodebaseIndexer(Path.cwd())
        if args.subcommand == "index":
            indexer.index()
            return {"indexed": True}
        if args.subcommand == "stats":
            return indexer.get_stats().to_dict()
        if not args.query:
            raise SystemExit("Search requires a query argument.")
        results = await indexer.hybrid_search(args.query, max_results=args.limit)
        return [r.to_dict() for r in results]
    result = asyncio.run(_run())
    if args.json:
        _print_json(result)
    else:
        if isinstance(result, list):
            if not result:
                print("No results found.")
            for r in result:
                print(f"  {r.get('score', 0):.3f}  {r.get('filePath', '?')}")
                snippet = r.get("content", "").strip()
                if snippet:
                    print(f"         {snippet[:100]}")
        else:
            _print_json(result)
    return 0
