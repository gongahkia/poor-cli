"""poor-cli entry point: CLI agent harness, JSON-RPC server, and headless subcommands."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Sequence

from .cli_errors import run_with_cli_error_handling
from . import __version__

if TYPE_CHECKING:
    from .config import Config
    from .task_manager import TaskManager


def _render_root_help() -> str:
    return (
        "usage: poor-cli <noun> <verb> [options]\n\n"
        "Lifecycle:\n"
        "  poor-cli exec               Run one shared-core request headlessly\n"
        "  poor-cli server             Run the JSON-RPC server (automation/API)\n"
        "  poor-cli tui                Launch the dependency-free curses TUI\n"
        "  poor-cli install            Installer: poor-cli install (run) / poor-cli install info\n"
        "\n"
        "Work units:\n"
        "  poor-cli task               Durable background tasks + worktrees\n"
        "  poor-cli agent              Background agents\n"
        "  poor-cli automation         Scheduled AutomationRule triggers\n"
        "  poor-cli pr                 Pull-request workflows (poor-cli pr review <n>, pr task create)\n\n"
        "State:\n"
        "  poor-cli session            List, create, fork, or destroy sessions\n"
        "  poor-cli history            Search, list, or export conversation history\n"
        "  poor-cli checkpoint         List, create, preview, or restore checkpoints\n"
        "  poor-cli state              Init, inspect, remove, export, or import local harness state\n"
        "  poor-cli memory             List, save, search, or delete memory entries\n\n"
        "Configuration:\n"
        "  poor-cli config             List, get, set, or toggle configuration\n"
        "  poor-cli provider           List, switch, or inspect AI providers\n"
        "  poor-cli profile            List or apply execution profiles\n"
        "  poor-cli trust              Repository trust management\n\n"
        "Diagnostics:\n"
        "  poor-cli diag               doctor | status | policy | tools | mcp\n"
        "  poor-cli cost               Session cost and economy settings\n"
        "  poor-cli audit              Export or rotate audit logs\n"
        "  poor-cli context            Compact, preview, or budget context\n"
        "  poor-cli search             Search the codebase (and search watch)\n\n"
        "Code review and delivery:\n"
        "  poor-cli review             Review a file or staged diff\n"
        "  poor-cli review-loop        Clean-context review loop over current diff\n"
        "  poor-cli commit             Generate a commit message from staged changes\n"
        "  poor-cli deploy             poor-cli deploy run | preview | history | validate\n"
        "  poor-cli workflow           List/inspect AutomationRule slash-command workflows\n"
        "  poor-cli services           Manage external long-running services\n\n"
        "Reuse:\n"
        "  poor-cli skill              list / show / run repo or user skills; alias-* for slash aliases\n\n"
        "Examples:\n"
        "  poor-cli exec --prompt \"Summarize this repository\" --plan-only\n"
        "  poor-cli task create --title \"Review docs\" --preset review-only --prompt \"Review README\"\n"
        "  poor-cli automation create --name \"Daily QA\" --every-minutes 60 --prompt \"Run QA checklist\"\n"
        "  poor-cli diag doctor\n"
        "  poor-cli pr review 123\n"
        "  poor-cli server --stdio\n\n"
        "Notes:\n"
        "  - Run `poor-cli help` or `poor-cli --help` to show this overview.\n"
    )

def _run_server_mode(argv: Sequence[str]) -> int:
    from .server import main as server_main

    original_argv = sys.argv[:]
    try:
        sys.argv = ["poor-cli server", *argv]
        server_main()
    finally:
        sys.argv = original_argv
    return 0


def _preset_description() -> dict[str, str]:
    from .sandbox import PRESET_DESCRIPTION
    return PRESET_DESCRIPTION


def _approval_required_presets() -> set[str]:
    from .task_manager import APPROVAL_REQUIRED_PRESETS
    return set(APPROVAL_REQUIRED_PRESETS)


def _build_exec_parser() -> argparse.ArgumentParser:
    from .config import PermissionMode

    parser = argparse.ArgumentParser(prog="poor-cli exec")
    parser.add_argument("--prompt", help="Prompt to send to the shared poor-cli core")
    parser.add_argument(
        "--output-format",
        choices=("text", "json", "stream-json"),
        default="text",
        help="Output mode for headless execution",
    )
    parser.add_argument("--resume", action="store_true", help="Prefix the prompt with recent repo session history")
    parser.add_argument(
        "--allow-tool",
        action="append",
        default=[],
        help="Allow only the named tool(s); repeat to allow multiple",
    )
    parser.add_argument(
        "--deny-tool",
        action="append",
        default=[],
        help="Deny the named tool(s); repeat to block multiple",
    )
    parser.add_argument("--plan-only", action="store_true", help="Return a plan without executing tools")
    parser.add_argument("--provider", help="Override provider for this execution")
    parser.add_argument("--model", help="Override model for this execution")
    parser.add_argument(
        "--routing-mode",
        choices=("manual", "quality", "speed", "cheap", "private"),
        help="Routing policy for provider selection and privacy posture",
    )
    parser.add_argument("--api-key", help="Override API key for this execution")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--cwd", help="Working directory for this execution")
    parser.add_argument(
        "--sandbox-preset",
        choices=tuple(_preset_description().keys()),
        help="Capability sandbox preset for this execution",
    )
    parser.add_argument(
        "--permission-mode",
        choices=tuple(mode.value for mode in PermissionMode),
        help="Permission mode for this execution",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve operations that would otherwise require interactive approval",
    )
    parser.add_argument(
        "--context-file",
        action="append",
        default=[],
        help="Explicit context file to attach; repeat to attach multiple",
    )
    parser.add_argument(
        "--pinned-context-file",
        action="append",
        default=[],
        help="Pinned context file to attach; repeat to attach multiple",
    )
    parser.add_argument("--context-budget-tokens", type=int, help="Context token budget for backend context selection")
    return parser


def _coerce_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return str(args.prompt)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("`poor-cli exec` requires --prompt or piped stdin.")


def _build_resume_prefix() -> str:
    from .repo_config import get_repo_config
    from .session_store import SessionStore

    session_store = SessionStore(Path.cwd())
    latest_snapshot = session_store.load_latest()
    if latest_snapshot:
        history = latest_snapshot.get("history") or latest_snapshot.get("messages") or []
        if isinstance(history, list) and history:
            lines = [
                "[Recent saved session context]",
                f"Session: {latest_snapshot.get('session_id', '')}",
                f"Model: {latest_snapshot.get('model', '')}",
            ]
            for message in history[-8:]:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role", "assistant")).strip() or "assistant"
                role = "assistant" if role == "model" else role
                content = str(message.get("content", "")).strip()
                if not content:
                    continue
                if len(content) > 1200:
                    content = f"{content[:1200]}\n... (truncated)"
                lines.append(f"{role}: {content}")
            if len(lines) > 3:
                return "\n\n".join(lines)

    repo_config = get_repo_config(enable_legacy_history_migration=False)
    sessions = repo_config.list_sessions(limit=1)
    if not sessions:
        return ""

    session = sessions[0]
    if not session.messages:
        return ""

    lines = [
        "[Recent repository session context]",
        f"Session: {session.session_id}",
        f"Model: {session.model}",
    ]
    for message in session.messages[-8:]:
        role = "assistant" if message.role == "model" else message.role
        content = message.content.strip()
        if not content:
            continue
        if len(content) > 1200:
            content = f"{content[:1200]}\n... (truncated)"
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _build_exec_permission_callback(*args: Any, **kwargs: Any) -> Any:
    from ._exec_helpers import build_exec_permission_callback
    return build_exec_permission_callback(*args, **kwargs)


async def _run_exec_mode_async(args: argparse.Namespace) -> int:
    from .config import PermissionMode, parse_permission_mode
    from .core import PoorCLICore
    from .sandbox import normalize_preset

    if args.cwd:
        os.chdir(Path(args.cwd).expanduser())

    prompt = _coerce_prompt(args).strip()
    if not prompt:
        raise SystemExit("Prompt cannot be empty.")

    if args.resume:
        resume_prefix = _build_resume_prefix()
        if resume_prefix:
            prompt = f"{resume_prefix}\n\nUser request:\n{prompt}"

    if args.plan_only:
        prompt = (
            "Return a concise numbered plan only. Do not call tools or make changes.\n\n"
            f"User request:\n{prompt}"
        )

    config_path = Path(args.config).expanduser() if args.config else None
    core = PoorCLICore(config_path=config_path)
    await core.initialize(
        provider_name=args.provider,
        model_name=args.model,
        api_key=args.api_key,
    )
    # drain init progress events to stderr
    for ev in core._pending_events:
        if ev.type == "progress":
            msg = ev.data.get("message", "")
            if msg:
                print(f"[init] {msg}", file=sys.stderr)
    core._pending_events = []
    if args.routing_mode:
        core.set_routing_mode(args.routing_mode)
    if core.config is not None:
        if args.permission_mode:
            core.config.security.permission_mode = parse_permission_mode(args.permission_mode)
        effective_permission_mode = (
            args.permission_mode
            or getattr(core.config.security.permission_mode, "value", str(core.config.security.permission_mode))
        )
        effective_sandbox_preset = normalize_preset(
            args.sandbox_preset or getattr(core.config.sandbox, "default_preset", ""),
            fallback_permission_mode=effective_permission_mode,
        )
        core.config.sandbox.default_preset = effective_sandbox_preset
    else:
        effective_permission_mode = args.permission_mode or PermissionMode.DEFAULT.value
        effective_sandbox_preset = normalize_preset(
            args.sandbox_preset,
            fallback_permission_mode=effective_permission_mode,
        )
    core.permission_callback = _build_exec_permission_callback(
        core,
        set(args.allow_tool or []),
        set(args.deny_tool or []),
        plan_only=bool(args.plan_only),
        permission_mode=effective_permission_mode,
        sandbox_preset=effective_sandbox_preset,
        auto_approve=bool(args.auto_approve),
    )

    try:
        if args.output_format == "stream-json":
            async for event in core.send_message_events(
                prompt,
                context_files=list(args.context_file or []),
                pinned_context_files=list(args.pinned_context_file or []),
                context_budget_tokens=args.context_budget_tokens,
                source_kind="exec",
                source_id="cli-exec",
                run_metadata={"cliCommand": "exec"},
            ):
                print(
                    json.dumps(
                        {
                            "type": event.type,
                            "data": event.data,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            return 0

        response_text = await core.send_message_sync(
            prompt,
            context_files=list(args.context_file or []),
            pinned_context_files=list(args.pinned_context_file or []),
            context_budget_tokens=args.context_budget_tokens,
            source_kind="exec",
            source_id="cli-exec",
            run_metadata={"cliCommand": "exec"},
        )
        if args.output_format == "json":
            print(
                json.dumps(
                    {
                        "content": response_text,
                        "provider": core.get_provider_info(),
                        "permissionMode": effective_permission_mode,
                        "sandboxPreset": effective_sandbox_preset,
                        "autoApprove": bool(args.auto_approve),
                        "cost": core.get_session_cost_summary(),
                        "statusView": core.build_status_view(),
                        "instructionStack": core.inspect_instruction_stack(
                            list(args.context_file or []) + list(args.pinned_context_file or [])
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        print(response_text)
        return 0
    finally:
        await core.shutdown()


def _run_exec_mode(argv: Sequence[str]) -> int:
    import asyncio

    parser = _build_exec_parser()
    args = parser.parse_args(list(argv))
    return asyncio.run(_run_exec_mode_async(args))


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def _run_skill_async(name: str, request: str) -> int:
    from .core import PoorCLICore
    from .skills import SkillRegistry

    registry = SkillRegistry(Path.cwd())
    prompt = registry.render_skill_prompt(name, request)
    core = PoorCLICore()
    await core.initialize()
    try:
        print(await core.send_message_sync(prompt))
        return 0
    finally:
        await core.shutdown()


async def _run_custom_command_async(name: str, args_text: str) -> int:
    from .automations import CustomCommandRegistry
    from .core import PoorCLICore

    registry = CustomCommandRegistry(Path.cwd())
    prompt = registry.render_prompt(name, args_text=args_text)
    core = PoorCLICore()
    await core.initialize()
    try:
        print(await core.send_message_sync(prompt))
        return 0
    finally:
        await core.shutdown()


def _collect_string_values(raw_values: Any) -> list[str]:
    if not isinstance(raw_values, list):
        return []
    values: list[str] = []
    for raw_value in raw_values:
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if value:
            values.append(value)
    return values


def _build_execution_metadata_from_args(args: argparse.Namespace) -> dict[str, Any]:
    execution: dict[str, Any] = {}

    provider = str(getattr(args, "provider", "") or "").strip()
    if provider:
        execution["provider"] = provider

    model = str(getattr(args, "model", "") or "").strip()
    if model:
        execution["model"] = model

    routing_mode = str(getattr(args, "routing_mode", "") or "").strip()
    if routing_mode:
        execution["routingMode"] = routing_mode

    config_path = str(getattr(args, "config", "") or "").strip()
    if config_path:
        execution["configPath"] = config_path

    execution_mode = str(getattr(args, "execution_mode", "") or "").strip().lower()
    if execution_mode:
        execution["executionMode"] = execution_mode

    reasoning_effort = str(getattr(args, "reasoning_effort", "") or "").strip().lower()
    if reasoning_effort:
        execution["reasoningEffort"] = reasoning_effort

    context_files = _collect_string_values(getattr(args, "context_file", []))
    if context_files:
        execution["contextFiles"] = context_files

    pinned_context_files = _collect_string_values(
        getattr(args, "pinned_context_file", [])
    )
    if pinned_context_files:
        execution["pinnedContextFiles"] = pinned_context_files

    raw_context_budget = getattr(args, "context_budget_tokens", None)
    if raw_context_budget is not None:
        try:
            context_budget = int(raw_context_budget)
        except (TypeError, ValueError) as error:
            raise SystemExit("`--context-budget-tokens` must be an integer.") from error
        if context_budget <= 0:
            raise SystemExit("`--context-budget-tokens` must be greater than zero.")
        execution["contextBudgetTokens"] = context_budget

    return execution


def _load_cli_config(config_path_hint: Optional[str] = None) -> Config:
    from .config import Config, ConfigManager

    if config_path_hint:
        hinted_path = Path(config_path_hint).expanduser()
        if not hinted_path.is_absolute():
            hinted_path = Path.cwd() / hinted_path
        manager = ConfigManager(hinted_path.resolve())
        if manager.config_path.exists():
            return manager.load()
        return Config()

    manager = ConfigManager()
    if manager.config_path.exists():
        return manager.load()

    manager.config = Config()
    manager._apply_repo_overrides()
    return manager.config


def _task_default_auto_start(preset: str, config: Config) -> bool:
    tasks_config = getattr(config, "tasks", None)
    if tasks_config is None:
        return preset not in _approval_required_presets()

    if preset in {"read-only", "review-only"}:
        return bool(tasks_config.auto_start_read_only)
    if preset == "workspace-write":
        return bool(tasks_config.auto_start_workspace_write)
    return False


def _resolve_task_create_behavior(
    *,
    preset: str,
    config: Config,
    auto_start: Optional[bool],
    auto_approve: bool,
    requires_approval: bool,
    wait: bool,
) -> tuple[bool, bool]:
    effective_auto_start = (
        _task_default_auto_start(preset, config) if auto_start is None else bool(auto_start)
    )
    approval_required = bool(requires_approval or (preset in _approval_required_presets() and not auto_approve))
    if wait:
        if approval_required:
            raise SystemExit(
                "`--wait` requires a task that can start immediately. Use `--auto-approve` "
                "or approve the task in a separate step."
            )
        effective_auto_start = True
    return effective_auto_start, approval_required


def _task_payload_with_wait(
    manager: TaskManager,
    task,
    *,
    wait: bool,
    timeout_seconds: int,
    command_label: str,
) -> dict[str, Any]:
    payload = task.to_dict()
    if not wait:
        return payload
    if payload["status"] in {"queued", "awaiting_approval"}:
        raise SystemExit(
            f"`{command_label} --wait` requires a running or terminal task; "
            f"current status is {payload['status']}."
        )
    return _wait_for_task_completion(
        manager,
        payload["taskId"],
        timeout_seconds=timeout_seconds,
    )


def _read_text_if_present(path: str) -> str:
    candidate = Path(path)
    if not candidate.exists() or candidate.is_dir():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def _build_task_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli task")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--title")
    create.add_argument("--prompt")
    create.add_argument("--preset", default="workspace-write", choices=tuple(_preset_description().keys()))
    create.add_argument("--source", default="manual")
    create.add_argument("--requires-approval", action="store_true")
    create.add_argument(
        "--auto-approve",
        action="store_true",
        help="Approve immediately instead of leaving the task awaiting approval.",
    )
    create.add_argument(
        "--approve",
        dest="auto_approve",
        action="store_true",
        help="Alias for --auto-approve.",
    )
    auto_start_group = create.add_mutually_exclusive_group()
    auto_start_group.add_argument("--auto-start", dest="auto_start", action="store_true")
    auto_start_group.add_argument("--no-auto-start", dest="auto_start", action="store_false")
    create.set_defaults(auto_start=None)
    create.add_argument("--provider")
    create.add_argument("--model")
    create.add_argument("--routing-mode", choices=("manual", "quality", "speed", "cheap", "private"))
    create.add_argument("--timezone", help="IANA timezone for daily/weekly schedules (defaults to local timezone)")
    create.add_argument("--execution-mode", choices=("worktree", "local"), default="worktree")
    create.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    create.add_argument("--config")
    create.add_argument("--context-file", action="append", default=[])
    create.add_argument("--pinned-context-file", action="append", default=[])
    create.add_argument("--context-budget-tokens", type=int)
    create.add_argument("--wait", action="store_true")
    create.add_argument("--wait-timeout-seconds", type=int, default=900)
    create.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status", action="append", default=[])
    list_parser.add_argument("--inbox", action="store_true")
    list_parser.add_argument("--json", action="store_true")

    show = subparsers.add_parser("show")
    show.add_argument("task_id")
    show.add_argument("--response", action="store_true")
    show.add_argument("--events", action="store_true")
    show.add_argument("--log", action="store_true")
    show.add_argument("--json", action="store_true")

    start = subparsers.add_parser("start")
    start.add_argument("task_id")
    start.add_argument("--wait", action="store_true")
    start.add_argument("--wait-timeout-seconds", type=int, default=900)
    start.add_argument("--json", action="store_true")

    wait_parser = subparsers.add_parser("wait")
    wait_parser.add_argument("task_id")
    wait_parser.add_argument("--timeout-seconds", type=int, default=900)
    wait_parser.add_argument("--json", action="store_true")

    approve = subparsers.add_parser("approve")
    approve.add_argument("task_id")
    approve.add_argument("--no-auto-start", action="store_true")
    approve.add_argument("--wait", action="store_true")
    approve.add_argument("--wait-timeout-seconds", type=int, default=900)
    approve.add_argument("--json", action="store_true")

    cancel = subparsers.add_parser("cancel")
    cancel.add_argument("task_id")
    cancel.add_argument("--json", action="store_true")

    retry = subparsers.add_parser("retry")
    retry.add_argument("task_id")
    retry.add_argument("--no-auto-start", action="store_true")
    retry.add_argument("--wait", action="store_true")
    retry.add_argument("--wait-timeout-seconds", type=int, default=900)
    retry.add_argument("--json", action="store_true")

    replay = subparsers.add_parser("replay")
    replay.add_argument("task_id")
    replay.add_argument("--no-auto-start", action="store_true")
    replay.add_argument("--wait", action="store_true")
    replay.add_argument("--wait-timeout-seconds", type=int, default=900)
    replay.add_argument("--json", action="store_true")

    run = subparsers.add_parser("run")
    run.add_argument("--task-id", required=True)
    run.add_argument("--repo-root", required=True)
    run.add_argument("--config")
    return parser


def _coerce_task_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return str(args.prompt)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("`poor-cli task create` requires --prompt or piped stdin.")


def _format_task(task: dict) -> str:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    lines = [
        f"Task: {task['taskId']} [{task['status']}]",
        f"Title: {task['title']}",
        f"Preset: {task['sandboxPreset']}",
        f"Source: {task['source']}",
        f"Worktree: {task['worktreePath']}",
        f"Artifacts: {task['artifactDir']}",
    ]
    last_run_id = str(metadata.get("lastRunId", "") or "").strip()
    if last_run_id:
        lines.append(f"Last run: {last_run_id}")
    if task.get("summary"):
        lines.append(f"Summary: {task['summary']}")
    if task.get("errorMessage"):
        lines.append(f"Error: {task['errorMessage']}")
    return "\n".join(lines)


def _wait_for_task_completion(manager: TaskManager, task_id: str, *, timeout_seconds: int) -> dict:
    deadline = time.time() + max(1, int(timeout_seconds))
    terminal_statuses = {"completed", "failed", "cancelled"}
    while time.time() <= deadline:
        task = manager.get_task(task_id)
        if task is not None and task.status in terminal_statuses:
            return task.to_dict()
        time.sleep(1)
    raise SystemExit(f"Timed out waiting for task {task_id} to finish.")


def _run_watch_mode(argv: Sequence[str]) -> int:
    """Handle 'poor-cli watch' — monitor files for inline instructions."""
    import asyncio
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli watch")
    parser.add_argument("--debounce", type=float, default=2.0, help="Debounce seconds")
    parser.add_argument("--scan", action="store_true", help="Scan once and exit (don't watch)")
    parser.add_argument("--execute", action="store_true", help="Execute found instructions via core engine")
    args = parser.parse_args(list(argv))
    from .file_watcher import scan_directory_for_instructions, FileWatcher
    if args.scan:
        instructions = scan_directory_for_instructions()
        if not instructions:
            print("No poor-cli instructions found.")
        for instr in instructions:
            print(f"  {instr['file']}:{instr['line']}: {instr['instruction']}")
        return 0
    async def _on_instruction(instr: dict) -> None:
        print(f"[watch] {instr['file']}:{instr['line']}: {instr['instruction']}")
    on_execute = None
    if args.execute:
        async def _exec_instruction(instr: dict) -> None:
            from .core import PoorCLICore
            core = PoorCLICore()
            await core.initialize()
            prompt = f"In file {instr['file']} at line {instr['line']}: {instr['instruction']}"
            async for _ in core.run(prompt):
                pass
            await core.shutdown()
        on_execute = _exec_instruction
    watcher = FileWatcher(debounce=args.debounce, on_instruction=_on_instruction, on_execute=on_execute)
    print(f"Watching for # poor-cli: instructions (debounce={args.debounce}s)...")
    try:
        asyncio.run(watcher.start())
    except KeyboardInterrupt:
        pass
    return 0


def _run_tui_mode(argv: Sequence[str]) -> int:
    from .tui.app import main as tui_main

    return tui_main(list(argv))


def _run_deploy_mode(argv: Sequence[str]) -> int:
    """Handle 'poor-cli deploy'."""
    import asyncio
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli deploy")
    parser.add_argument("--target", "-t", help="Deploy target (vercel, netlify, fly, railway, cloudflare)")
    parser.add_argument("--prod", action="store_true", help="Deploy to production")
    parser.add_argument("--list", action="store_true", help="List detected targets")
    parser.add_argument("--validate", action="store_true", help="Run pre-deploy validation only")
    parser.add_argument("--history", action="store_true", help="Show deployment history")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from .deploy import detect_deploy_targets, deploy, validate_pre_deploy, get_deploy_history
    if args.validate:
        result = validate_pre_deploy()
        if args.json:
            import json
            print(json.dumps(result, indent=2))
        else:
            print("Pre-deploy: " + ("PASS" if result["valid"] else "FAIL"))
            for issue in result["issues"]:
                print(f"  - {issue}")
        return 0 if result["valid"] else 1
    if args.history:
        entries = get_deploy_history()
        if args.json:
            import json
            print(json.dumps(entries, indent=2))
        else:
            if not entries:
                print("No deployment history.")
            for e in entries:
                print(f"  [{e.get('target')}] {'OK' if e.get('success') else 'FAIL'} {e.get('url', '')} {e.get('message', '')}")
        return 0
    if args.list:
        targets = detect_deploy_targets()
        for t in targets:
            status = "✓" if t.available else "✗"
            cfg = f" ({t.config_file})" if t.config_file else ""
            print(f"  [{status}] {t.name}: {t.description}{cfg}")
        return 0
    result = asyncio.run(deploy(target=args.target, prod=args.prod))
    if args.json:
        import json
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.message)
        if result.url:
            print(f"  URL: {result.url}")
    return 0 if result.success else 1


def _run_preview_mode(argv: Sequence[str]) -> int:
    """Handle 'poor-cli preview'."""
    import asyncio
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli preview")
    parser.add_argument("--port", type=int, default=3456)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--health", action="store_true", help="Check server health status")
    args = parser.parse_args(list(argv))
    from .preview_server import PreviewServer
    server = PreviewServer(port=args.port)
    if args.health:
        import json
        print(json.dumps(server.status(), indent=2))
        return 0
    if args.stop:
        result = asyncio.run(server.stop())
        print(f"Stopped: {result}")
        return 0
    result = asyncio.run(server.start())
    print(result.get("message", str(result)))
    if result.get("mode") in {"static", "proxy"}:
        print("Press Ctrl+C to stop.")
        try:
            while True:
                status = server.status()
                if not status.get("running"):
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            asyncio.run(server.stop())
    return 0


def _run_review_pr_mode(argv: Sequence[str]) -> int:
    """Handle 'poor-cli review-pr <number>'."""
    import asyncio
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli pr review")
    parser.add_argument("pr_number", type=int, help="PR number to review")
    parser.add_argument("--post", action="store_true", help="Post review as PR comment")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--ci", action="store_true", help="CI mode: exit code reflects severity")
    args = parser.parse_args(list(argv))
    from .review_agent import review_pr
    result = asyncio.run(review_pr(args.pr_number, post_comment=args.post))
    if args.json:
        import json
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.to_markdown())
    if args.ci:
        return 0 if result.passed else 1
    return 0


def _run_agent_mode(argv: Sequence[str]) -> int:
    """Handle 'poor-cli agent' subcommands."""
    import asyncio
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli agent", description="Background agent management")
    sub = parser.add_subparsers(dest="subcommand")

    # agent start
    p_start = sub.add_parser("start", help="Start a background agent")
    p_start.add_argument("--prompt", "-p", required=True, help="Task prompt")
    p_start.add_argument("--sandbox", default="workspace-write", help="Sandbox preset")
    p_start.add_argument("--no-worktree", action="store_true", help="Run in current directory")
    p_start.add_argument("--max-runtime", type=int, default=3600, help="Max runtime in seconds")
    p_start.add_argument("--max-cost", type=float, default=5.0, help="Max cost in USD")
    p_start.add_argument("--json", action="store_true")

    # agent list
    p_list = sub.add_parser("list", help="List agents")
    p_list.add_argument("--status", nargs="*", help="Filter by status")
    p_list.add_argument("--json", action="store_true")

    # agent logs
    p_logs = sub.add_parser("logs", help="Show agent logs")
    p_logs.add_argument("agent_id", help="Agent ID")
    p_logs.add_argument("--tail", type=int, default=100)

    # agent result
    p_result = sub.add_parser("result", help="Show agent result")
    p_result.add_argument("agent_id", help="Agent ID")

    # agent cancel
    p_cancel = sub.add_parser("cancel", help="Cancel a running agent")
    p_cancel.add_argument("agent_id", help="Agent ID")

    # agent run (internal — called by subprocess)
    p_run = sub.add_parser("run", help=argparse.SUPPRESS)
    p_run.add_argument("--agent-id", required=True)
    p_run.add_argument("--repo-root", required=True)

    args = parser.parse_args(list(argv))
    if not args.subcommand:
        parser.print_help()
        return 0

    from .agent_runner import AgentManager, run_agent_worker
    from pathlib import Path

    if args.subcommand == "run":
        asyncio.run(run_agent_worker(args.agent_id, args.repo_root))
        return 0

    mgr = AgentManager(Path.cwd())

    if args.subcommand == "start":
        agent = mgr.create_agent(
            prompt=args.prompt,
            sandbox_preset=args.sandbox,
            use_worktree=not args.no_worktree,
            max_runtime=args.max_runtime,
            max_cost_usd=args.max_cost,
            auto_start=True,
        )
        if args.json:
            import json as _json
            print(_json.dumps(agent.to_dict(), indent=2))
        else:
            print(f"Agent {agent.agent_id} started (pid {agent.worker_pid})")
            print(f"  Branch: {agent.branch_name}")
            print(f"  Logs: {agent.log_path}")
        return 0

    if args.subcommand == "list":
        agents = mgr.list_agents(statuses=args.status or None)
        if args.json:
            import json as _json
            print(_json.dumps([a.to_dict() for a in agents], indent=2))
        else:
            if not agents:
                print("No agents found")
            for a in agents:
                print(f"  {a.agent_id}  {a.status:12s}  {a.prompt[:60]}")
        return 0

    if args.subcommand == "logs":
        print(mgr.get_logs(args.agent_id, tail=args.tail))
        return 0

    if args.subcommand == "result":
        print(mgr.get_result(args.agent_id))
        return 0

    if args.subcommand == "cancel":
        agent = mgr.cancel_agent(args.agent_id)
        print(f"Agent {agent.agent_id}: {agent.status}")
        return 0

    return 0


def _run_task_mode(argv: Sequence[str]) -> int:
    import asyncio
    from .sandbox import normalize_preset
    from .task_manager import TaskManager, run_task_worker

    parser = _build_task_parser()
    args = parser.parse_args(list(argv))
    manager = TaskManager(Path.cwd())

    if args.subcommand == "create":
        prompt = _coerce_task_prompt(args).strip()
        if not prompt:
            raise SystemExit("Prompt cannot be empty.")
        preset = normalize_preset(args.preset)
        cli_config = _load_cli_config(getattr(args, "config", None))
        auto_start, requires_approval = _resolve_task_create_behavior(
            preset=preset,
            config=cli_config,
            auto_start=args.auto_start,
            auto_approve=bool(args.auto_approve),
            requires_approval=bool(args.requires_approval),
            wait=bool(args.wait),
        )
        metadata: dict[str, Any] = {}
        execution = _build_execution_metadata_from_args(args)
        if execution:
            metadata["execution"] = execution
        task = manager.create_task(
            title=(args.title or prompt.splitlines()[0][:80]).strip(),
            prompt=prompt,
            sandbox_preset=preset,
            source=str(args.source or "manual"),
            metadata=metadata,
            auto_start=auto_start and not requires_approval,
            requires_approval=requires_approval,
            auto_approve=bool(args.auto_approve),
        )
        payload = _task_payload_with_wait(
            manager,
            task,
            wait=bool(args.wait),
            timeout_seconds=args.wait_timeout_seconds,
            command_label="poor-cli task create",
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "list":
        tasks = manager.list_tasks(
            statuses=args.status or None,
            inbox_only=bool(args.inbox),
        )
        payload = [task.to_dict() for task in tasks]
        if args.json:
            _print_json(payload)
        else:
            for task in payload:
                print(_format_task(task))
                print()
        return 0

    if args.subcommand == "show":
        task = manager.get_task(args.task_id)
        if task is None:
            raise SystemExit(f"Unknown task: {args.task_id}")
        payload = task.to_dict()
        extras = {}
        if args.response:
            extras["response"] = _read_text_if_present(task.response_path)
        if args.events:
            extras["events"] = _read_text_if_present(task.events_path)
        if args.log:
            extras["log"] = _read_text_if_present(task.log_path)
        if args.json:
            if extras:
                _print_json({"task": payload, **extras})
            else:
                _print_json(payload)
        else:
            print(_format_task(payload))
            if extras:
                for name, content in extras.items():
                    print()
                    print(f"{name.upper()}:")
                    print(content.rstrip())
        return 0

    if args.subcommand == "start":
        task = manager.start_task_process(args.task_id)
        payload = _task_payload_with_wait(
            manager,
            task,
            wait=bool(args.wait),
            timeout_seconds=args.wait_timeout_seconds,
            command_label="poor-cli task start",
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "wait":
        task = manager.get_task(args.task_id)
        if task is None:
            raise SystemExit(f"Unknown task: {args.task_id}")
        payload = _wait_for_task_completion(
            manager,
            args.task_id,
            timeout_seconds=args.timeout_seconds,
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "approve":
        if args.wait and args.no_auto_start:
            raise SystemExit("`poor-cli task approve --wait` requires auto-start.")
        task = manager.approve_task(args.task_id, auto_start=not args.no_auto_start)
        payload = _task_payload_with_wait(
            manager,
            task,
            wait=bool(args.wait),
            timeout_seconds=args.wait_timeout_seconds,
            command_label="poor-cli task approve",
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "cancel":
        task = manager.cancel_task(args.task_id)
        if args.json:
            _print_json(task.to_dict())
        else:
            print(_format_task(task.to_dict()))
        return 0

    if args.subcommand == "retry":
        if args.wait and args.no_auto_start:
            raise SystemExit("`poor-cli task retry --wait` requires auto-start.")
        task = manager.retry_task(args.task_id, auto_start=not args.no_auto_start)
        payload = _task_payload_with_wait(
            manager,
            task,
            wait=bool(args.wait),
            timeout_seconds=args.wait_timeout_seconds,
            command_label="poor-cli task retry",
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "replay":
        if args.wait and args.no_auto_start:
            raise SystemExit("`poor-cli task replay --wait` requires auto-start.")
        task = manager.replay_task(args.task_id, auto_start=not args.no_auto_start)
        payload = _task_payload_with_wait(
            manager,
            task,
            wait=bool(args.wait),
            timeout_seconds=args.wait_timeout_seconds,
            command_label="poor-cli task replay",
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "run":
        repo_root = Path(args.repo_root).expanduser().resolve()
        config_path = Path(args.config).expanduser() if args.config else None
        return asyncio.run(
            run_task_worker(
                repo_root=repo_root,
                task_id=str(args.task_id),
                config_path=config_path,
            )
        )

    raise SystemExit(f"Unknown task subcommand: {args.subcommand}")


def _build_skill_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli skill")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    show = subparsers.add_parser("show")
    show.add_argument("name")
    run = subparsers.add_parser("run")
    run.add_argument("name")
    run.add_argument("request", nargs="*")
    return parser


def _run_skills_mode(argv: Sequence[str]) -> int:
    import asyncio
    from .skills import SkillRegistry

    parser = _build_skill_parser()
    args = parser.parse_args(list(argv))
    registry = SkillRegistry(Path.cwd())
    if args.subcommand == "list":
        skills = [skill.to_dict() for skill in registry.list_skills()]
        if args.json:
            _print_json(skills)
        else:
            for skill in skills:
                print(f"{skill['name']}: {skill['description']} ({skill['scope']})")
        return 0
    if args.subcommand == "show":
        skill = registry.get_skill(args.name)
        if skill is None:
            raise SystemExit(f"Unknown skill: {args.name}")
        print(skill.skill_file.read_text(encoding="utf-8"))
        return 0
    if args.subcommand == "run":
        return asyncio.run(_run_skill_async(args.name, " ".join(args.request)))
    raise SystemExit(f"Unknown skills subcommand: {args.subcommand}")


def _build_commands_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli skill alias")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    show = subparsers.add_parser("show")
    show.add_argument("name")
    run = subparsers.add_parser("run")
    run.add_argument("name")
    run.add_argument("args_text", nargs="*")
    return parser


def _run_commands_mode(argv: Sequence[str]) -> int:
    import asyncio
    from .automations import CustomCommandRegistry

    parser = _build_commands_parser()
    args = parser.parse_args(list(argv))
    registry = CustomCommandRegistry(Path.cwd())
    if args.subcommand == "list":
        commands = [command.to_dict() for command in registry.list_commands()]
        if args.json:
            _print_json(commands)
        else:
            for command in commands:
                print(f"{command['name']}: {command['description']} ({command['scope']})")
        return 0
    if args.subcommand == "show":
        command = registry.get_command(args.name)
        if command is None:
            raise SystemExit(f"Unknown command wrapper: {args.name}")
        print(command.template)
        return 0
    if args.subcommand == "run":
        return asyncio.run(_run_custom_command_async(args.name, " ".join(args.args_text)))
    raise SystemExit(f"Unknown commands subcommand: {args.subcommand}")


def _build_automation_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli automation")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--name")
    create.add_argument("--prompt")
    schedule_group = create.add_mutually_exclusive_group(required=True)
    schedule_group.add_argument("--every-minutes", type=int)
    schedule_group.add_argument("--daily")
    schedule_group.add_argument("--weekly")
    create.add_argument("--preset", default="read-only", choices=tuple(_preset_description().keys()))
    create.add_argument("--requires-approval", action="store_true")
    create.add_argument("--auto-approve", action="store_true")
    create.add_argument("--disabled", action="store_true")
    create.add_argument("--provider")
    create.add_argument("--model")
    create.add_argument("--routing-mode", choices=("manual", "quality", "speed", "cheap", "private"))
    create.add_argument("--timezone", help="IANA timezone for daily/weekly schedules (defaults to local timezone)")
    create.add_argument("--execution-mode", choices=("worktree", "local"), default="worktree")
    create.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    create.add_argument("--config")
    create.add_argument("--context-file", action="append", default=[])
    create.add_argument("--pinned-context-file", action="append", default=[])
    create.add_argument("--context-budget-tokens", type=int)
    create.add_argument("--run-now", action="store_true")
    create.add_argument("--wait", action="store_true")
    create.add_argument("--wait-timeout-seconds", type=int, default=900)
    create.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list")
    state_group = list_parser.add_mutually_exclusive_group()
    state_group.add_argument("--enabled", action="store_true")
    state_group.add_argument("--disabled", action="store_true")
    list_parser.add_argument("--json", action="store_true")

    show = subparsers.add_parser("show")
    show.add_argument("automation_id")
    show.add_argument("--json", action="store_true")

    enable = subparsers.add_parser("enable")
    enable.add_argument("automation_id")
    enable.add_argument("--json", action="store_true")

    disable = subparsers.add_parser("disable")
    disable.add_argument("automation_id")
    disable.add_argument("--json", action="store_true")

    run_now = subparsers.add_parser("run-now")
    run_now.add_argument("automation_id")
    run_now.add_argument("--wait", action="store_true")
    run_now.add_argument("--wait-timeout-seconds", type=int, default=900)
    run_now.add_argument("--json", action="store_true")

    run_due = subparsers.add_parser("run-due")
    run_due.add_argument("--limit", type=int, default=20)
    run_due.add_argument("--wait", action="store_true")
    run_due.add_argument("--wait-timeout-seconds", type=int, default=900)
    run_due.add_argument("--json", action="store_true")

    serve = subparsers.add_parser("serve")
    serve.add_argument("--poll-seconds", type=int, default=30)

    history = subparsers.add_parser("history")
    history.add_argument("automation_id")
    history.add_argument("--limit", type=int, default=25)
    history.add_argument("--json", action="store_true")

    replay = subparsers.add_parser("replay")
    replay.add_argument("automation_id")
    replay.add_argument("--wait", action="store_true")
    replay.add_argument("--wait-timeout-seconds", type=int, default=900)
    replay.add_argument("--json", action="store_true")

    migrate = subparsers.add_parser("migrate")
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--force", action="store_true")
    migrate.add_argument("--restore", action="store_true")
    migrate.add_argument("--json", action="store_true")
    return parser


def _coerce_automation_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return str(args.prompt)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("`poor-cli automation create` requires --prompt or piped stdin.")


def _automation_schedule_from_args(args: argparse.Namespace) -> dict[str, Any]:
    from .automations import parse_daily_schedule, parse_weekly_schedule, schedule_interval

    timezone_name = str(getattr(args, "timezone", "") or "").strip() or None
    if args.every_minutes is not None:
        return schedule_interval(args.every_minutes)
    if args.daily:
        return parse_daily_schedule(args.daily, timezone_name=timezone_name)
    if args.weekly:
        return parse_weekly_schedule(args.weekly, timezone_name=timezone_name)
    raise SystemExit("Missing automation schedule.")


def _format_automation(automation: dict) -> str:
    metadata = automation.get("metadata") if isinstance(automation.get("metadata"), dict) else {}
    execution = metadata.get("execution") if isinstance(metadata.get("execution"), dict) else {}
    lines = [
        f"Automation: {automation['automationId']} [{'enabled' if automation['enabled'] else 'disabled'}]",
        f"Name: {automation['name']}",
        f"Preset: {automation['sandboxPreset']}",
        f"Schedule: {automation['scheduleSummary']}",
    ]
    if automation.get("scheduleTimezone"):
        lines.append(f"Timezone: {automation['scheduleTimezone']}")
    execution_mode = str(automation.get("executionMode", "") or execution.get("executionMode", "")).strip()
    if execution_mode:
        lines.append(f"Execution mode: {execution_mode}")
    reasoning_effort = str(automation.get("reasoningEffort", "") or execution.get("reasoningEffort", "")).strip()
    if reasoning_effort:
        lines.append(f"Reasoning effort: {reasoning_effort}")
    if automation.get("nextRunAt"):
        lines.append(f"Next run: {automation['nextRunAt']}")
    if automation.get("lastRunAt"):
        lines.append(f"Last run: {automation['lastRunAt']}")
    if automation.get("lastTaskId"):
        lines.append(f"Last task: {automation['lastTaskId']}")
    if automation.get("lastRunId"):
        lines.append(f"Linked run: {automation['lastRunId']}")
    if automation.get("lastRunStatus"):
        lines.append(f"Last run status: {automation['lastRunStatus']}")
    if automation.get("lastRunSummary"):
        lines.append(f"Last run summary: {automation['lastRunSummary']}")
    if automation.get("lastRunError"):
        lines.append(f"Last run failure: {automation['lastRunError']}")
    if automation.get("replayOfRunId"):
        lines.append(f"Replay source: {automation['replayOfRunId']}")
    return "\n".join(lines)


def _format_run(run: dict) -> str:
    lines = [
        f"Run: {run.get('runId', '')} [{run.get('status', 'unknown')}]",
        f"Source: {run.get('sourceKind', 'unknown')}/{run.get('sourceId', 'unknown')}",
        f"Started: {run.get('startedAt', '')}",
    ]
    if run.get("finishedAt"):
        lines.append(f"Finished: {run['finishedAt']}")
    if run.get("errorClass"):
        lines.append(f"Error class: {run['errorClass']}")
    if run.get("checkpointId"):
        lines.append(f"Checkpoint: {run['checkpointId']}")
    provider = run.get("providerSummary") if isinstance(run.get("providerSummary"), dict) else {}
    provider_name = str(provider.get("name", "") or "").strip()
    provider_model = str(provider.get("model", "") or "").strip()
    if provider_name or provider_model:
        lines.append(f"Provider: {provider_name}/{provider_model}")
    if run.get("summary"):
        lines.append(f"Summary: {run['summary']}")
    return "\n".join(lines)


def _wait_for_tasks_completion(
    manager: TaskManager,
    tasks: Sequence[Any],
    *,
    timeout_seconds: int,
    action: str,
) -> list[dict[str, Any]]:
    waiting_ids = []
    terminal_payloads: list[dict[str, Any]] = []
    for task in tasks:
        payload = task.to_dict()
        if payload["status"] in {"queued", "awaiting_approval"}:
            raise SystemExit(
                f"`poor-cli automation {action} --wait` requires tasks that are already running "
                f"or terminal; {payload['taskId']} is {payload['status']}."
            )
        if payload["status"] in {"completed", "failed", "cancelled"}:
            terminal_payloads.append(payload)
        else:
            waiting_ids.append(payload["taskId"])

    completed = terminal_payloads[:]
    for task_id in waiting_ids:
        completed.append(
            _wait_for_task_completion(
                manager,
                task_id,
                timeout_seconds=timeout_seconds,
            )
        )
    return completed


def _run_automation_mode(argv: Sequence[str]) -> int:
    from .automations import AutomationManager, migrate_extensions, restore_migration
    from .sandbox import normalize_preset

    parser = _build_automation_parser()
    args = parser.parse_args(list(argv))

    if args.subcommand == "migrate":
        result = restore_migration(Path.cwd(), dry_run=bool(args.dry_run)) if args.restore else migrate_extensions(
            Path.cwd(),
            dry_run=bool(args.dry_run),
            force=bool(args.force),
        )
        payload = result.to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(
                f"Migration: {'done' if payload['migrated'] else 'skipped'} "
                f"rules={payload['ruleCount']} backup={payload['backupDir']}"
            )
            if payload.get("skippedReason"):
                print(f"Reason: {payload['skippedReason']}")
        return 0

    manager = AutomationManager(Path.cwd())

    if args.subcommand == "create":
        prompt = _coerce_automation_prompt(args).strip()
        if not prompt:
            raise SystemExit("Prompt cannot be empty.")
        if args.wait and not args.run_now:
            raise SystemExit("`poor-cli automation create --wait` requires `--run-now`.")
        metadata: dict[str, Any] = {}
        execution = _build_execution_metadata_from_args(args)
        if execution:
            metadata["execution"] = execution
        automation = manager.create_automation(
            name=(args.name or prompt.splitlines()[0][:80]).strip(),
            prompt=prompt,
            schedule=_automation_schedule_from_args(args),
            sandbox_preset=normalize_preset(args.preset),
            enabled=not args.disabled,
            requires_approval=bool(args.requires_approval),
            metadata=metadata,
            auto_approve=bool(args.auto_approve),
        )
        payload: Any = automation.to_dict()
        if args.run_now:
            if args.wait and payload["requiresApproval"]:
                raise SystemExit(
                    "`poor-cli automation create --wait` requires an automation that can start "
                    "without manual approval. Use `--auto-approve` or remove `--wait`."
                )
            task = manager.run_now(automation.automation_id)
            task_payload = task.to_dict()
            if args.wait:
                task_payload = _task_payload_with_wait(
                    manager.task_manager,
                    task,
                    wait=True,
                    timeout_seconds=args.wait_timeout_seconds,
                    command_label="poor-cli automation create",
                )
            payload = {"automation": payload, "task": task_payload}
        if args.json:
            _print_json(payload)
        else:
            if isinstance(payload, dict) and "automation" in payload and "task" in payload:
                print(_format_automation(payload["automation"]))
                print()
                print(_format_task(payload["task"]))
            else:
                print(_format_automation(payload))
        return 0

    if args.subcommand == "list":
        enabled_filter = True if args.enabled else False if args.disabled else None
        automations = [record.to_dict() for record in manager.list_automations(enabled=enabled_filter)]
        if args.json:
            _print_json(automations)
        else:
            for automation in automations:
                print(_format_automation(automation))
                print()
        return 0

    if args.subcommand == "show":
        automation = manager.get_automation(args.automation_id)
        if automation is None:
            raise SystemExit(f"Unknown automation: {args.automation_id}")
        payload = automation.to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(_format_automation(payload))
        return 0

    if args.subcommand == "enable":
        payload = manager.set_enabled(args.automation_id, True).to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(_format_automation(payload))
        return 0

    if args.subcommand == "disable":
        payload = manager.set_enabled(args.automation_id, False).to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(_format_automation(payload))
        return 0

    if args.subcommand == "run-now":
        task = manager.run_now(args.automation_id)
        payload = _task_payload_with_wait(
            manager.task_manager,
            task,
            wait=bool(args.wait),
            timeout_seconds=args.wait_timeout_seconds,
            command_label="poor-cli automation run-now",
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "run-due":
        tasks = manager.run_due(limit=args.limit)
        payload = [task.to_dict() for task in tasks]
        if args.wait and tasks:
            payload = _wait_for_tasks_completion(
                manager.task_manager,
                tasks,
                timeout_seconds=args.wait_timeout_seconds,
                action="run-due",
            )
        if args.json:
            _print_json(payload)
        else:
            for task in payload:
                print(_format_task(task))
                print()
        return 0

    if args.subcommand == "history":
        payload = manager.history(args.automation_id, limit=max(1, int(args.limit)))
        if args.json:
            _print_json(payload)
        else:
            for run in payload:
                print(_format_run(run))
                print()
        return 0

    if args.subcommand == "replay":
        task = manager.replay(args.automation_id)
        payload = _task_payload_with_wait(
            manager.task_manager,
            task,
            wait=bool(args.wait),
            timeout_seconds=args.wait_timeout_seconds,
            command_label="poor-cli automation replay",
        )
        if args.json:
            _print_json(payload)
        else:
            print(_format_task(payload))
        return 0

    if args.subcommand == "serve":
        manager.serve_forever(poll_seconds=args.poll_seconds)
        return 0

    raise SystemExit(f"Unknown automation subcommand: {args.subcommand}")


def _build_github_task_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli github-task")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--event-path")
    create.add_argument("--mode", choices=("read-only", "review-only"))
    auto_start_group = create.add_mutually_exclusive_group()
    auto_start_group.add_argument("--auto-start", dest="auto_start", action="store_true")
    auto_start_group.add_argument("--no-auto-start", dest="auto_start", action="store_false")
    create.set_defaults(auto_start=None)
    create.add_argument("--provider")
    create.add_argument("--model")
    create.add_argument("--config")
    create.add_argument("--context-file", action="append", default=[])
    create.add_argument("--pinned-context-file", action="append", default=[])
    create.add_argument("--context-budget-tokens", type=int)
    create.add_argument("--wait", action="store_true")
    create.add_argument("--wait-timeout-seconds", type=int, default=900)
    create.add_argument("--json", action="store_true")
    return parser


def _run_github_task_mode(argv: Sequence[str]) -> int:
    from .github_task import create_task_from_context, default_mode_for_context, load_github_context
    from .task_manager import TaskManager

    parser = _build_github_task_parser()
    args = parser.parse_args(list(argv))
    manager = TaskManager(Path.cwd())

    if args.subcommand == "create":
        context = load_github_context(Path(args.event_path).expanduser() if args.event_path else None, env=os.environ)
        mode = args.mode or default_mode_for_context(context)
        cli_config = _load_cli_config(getattr(args, "config", None))
        auto_start = (
            _task_default_auto_start(mode, cli_config)
            if args.auto_start is None
            else bool(args.auto_start)
        )
        metadata: dict[str, Any] = {}
        execution = _build_execution_metadata_from_args(args)
        if execution:
            metadata["execution"] = execution
        task = create_task_from_context(
            manager,
            context,
            mode=mode,
            auto_start=auto_start,
            metadata=metadata,
        )
        payload = task.to_dict()
        if args.wait:
            if not auto_start:
                raise SystemExit("`poor-cli github-task create --wait` requires auto-start.")
            payload = _wait_for_task_completion(
                manager,
                task.task_id,
                timeout_seconds=args.wait_timeout_seconds,
            )
        if args.json:
            _print_json({"task": payload, "context": context.to_dict()})
        else:
            print(_format_task(payload))
            print(f"GitHub: {context.kind} #{context.number} {context.url}")
        return 0

    raise SystemExit(f"Unknown github-task subcommand: {args.subcommand}")




def _run_checkpoint_mode(argv: Sequence[str]) -> int:
    from .cli import run_checkpoint_mode
    return run_checkpoint_mode(argv)


def _run_history_mode(argv: Sequence[str]) -> int:
    from .cli import run_history_mode
    return run_history_mode(argv)


def _run_session_mode(argv: Sequence[str]) -> int:
    from .cli import run_session_mode
    return run_session_mode(argv)


def _run_state_mode(argv: Sequence[str]) -> int:
    from .cli import run_state_mode
    return run_state_mode(argv)


def _run_memory_mode(argv: Sequence[str]) -> int:
    from .cli import run_memory_mode
    return run_memory_mode(argv)


def _run_config_mode(argv: Sequence[str]) -> int:
    from .cli import run_config_mode
    return run_config_mode(argv)


def _run_profile_mode(argv: Sequence[str]) -> int:
    from .cli import run_profile_mode
    return run_profile_mode(argv)


def _run_trust_mode(argv: Sequence[str]) -> int:
    from .cli import run_trust_mode
    return run_trust_mode(argv)


def _run_provider_mode(argv: Sequence[str]) -> int:
    from .cli import run_provider_mode
    return run_provider_mode(argv)


def _run_core_info_command(method_name: str, argv: Sequence[str], prog: str) -> int:
    from .cli import run_core_info_command
    return run_core_info_command(method_name, argv, prog)


def _run_cost_mode(argv: Sequence[str]) -> int:
    from .cli import run_cost_mode
    return run_cost_mode(argv)


def _run_search_mode(argv: Sequence[str]) -> int:
    from .cli import run_search_mode
    return run_search_mode(argv)


def _run_review_file_mode(argv: Sequence[str]) -> int:
    from .cli import run_review_file_mode
    return run_review_file_mode(argv)


def _run_review_loop_mode(argv: Sequence[str]) -> int:
    from .cli import run_review_loop_mode
    return run_review_loop_mode(argv)


def _run_commit_mode(argv: Sequence[str]) -> int:
    from .cli import run_commit_mode
    return run_commit_mode(argv)


def _run_audit_mode(argv: Sequence[str]) -> int:
    from .cli import run_audit_mode
    return run_audit_mode(argv)


def _run_context_mode(argv: Sequence[str]) -> int:
    from .cli import run_context_mode
    return run_context_mode(argv)


def _run_workflow_mode(argv: Sequence[str]) -> int:
    from .cli import run_workflow_mode
    return run_workflow_mode(argv)


def _run_services_mode(argv: Sequence[str]) -> int:
    from .cli import run_services_mode
    return run_services_mode(argv)


def _main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print(_render_root_help())
        raise SystemExit(0)
    if argv[0] in {"help", "--help", "-h"}:
        print(_render_root_help())
        raise SystemExit(0)
    if argv[0] in {"version", "--version", "-V"}:
        print(__version__)
        raise SystemExit(0)
    if argv and argv[0] == "exec":
        raise SystemExit(_run_exec_mode(argv[1:]))
    if argv and argv[0] == "tui":
        raise SystemExit(_run_tui_mode(argv[1:]))
    if argv and argv[0] == "agent":
        raise SystemExit(_run_agent_mode(argv[1:]))
    if argv and argv[0] == "task":
        raise SystemExit(_run_task_mode(argv[1:]))
    if argv and argv[0] == "skill":
        raise SystemExit(_run_skill_mode(argv[1:]))
    if argv and argv[0] == "automation":
        raise SystemExit(_run_automation_mode(argv[1:]))
    if argv and argv[0] == "checkpoint":
        raise SystemExit(_run_checkpoint_mode(argv[1:]))
    if argv and argv[0] == "history":
        raise SystemExit(_run_history_mode(argv[1:]))
    if argv and argv[0] == "session":
        raise SystemExit(_run_session_mode(argv[1:]))
    if argv and argv[0] == "state":
        raise SystemExit(_run_state_mode(argv[1:]))
    if argv and argv[0] == "memory":
        raise SystemExit(_run_memory_mode(argv[1:]))
    if argv and argv[0] == "config":
        raise SystemExit(_run_config_mode(argv[1:]))
    if argv and argv[0] == "profile":
        raise SystemExit(_run_profile_mode(argv[1:]))
    if argv and argv[0] == "trust":
        raise SystemExit(_run_trust_mode(argv[1:]))
    if argv and argv[0] == "provider":
        raise SystemExit(_run_provider_mode(argv[1:]))
    if argv and argv[0] == "diag":
        raise SystemExit(_run_diag_mode(argv[1:]))
    if argv and argv[0] == "cost":
        raise SystemExit(_run_cost_mode(argv[1:]))
    if argv and argv[0] == "audit":
        raise SystemExit(_run_audit_mode(argv[1:]))
    if argv and argv[0] == "context":
        raise SystemExit(_run_context_mode(argv[1:]))
    if argv and argv[0] == "workflow":
        raise SystemExit(_run_workflow_mode(argv[1:]))
    if argv and argv[0] == "services":
        raise SystemExit(_run_services_mode(argv[1:]))
    if argv and argv[0] == "search":
        raise SystemExit(_run_search_mode(argv[1:]))
    if argv and argv[0] == "review":
        raise SystemExit(_run_review_file_mode(argv[1:]))
    if argv and argv[0] == "review-loop":
        raise SystemExit(_run_review_loop_mode(argv[1:]))
    if argv and argv[0] == "commit":
        raise SystemExit(_run_commit_mode(argv[1:]))
    if argv and argv[0] == "deploy":
        raise SystemExit(_run_deploy_umbrella(argv[1:]))
    if argv and argv[0] == "pr":
        raise SystemExit(_run_pr_mode(argv[1:]))
    if argv and argv[0] == "server":
        raise SystemExit(_run_server_mode(argv[1:]))
    if argv and argv[0] == "install":
        raise SystemExit(_run_install_mode(argv[1:]))
    print(f"poor-cli: unknown command '{argv[0]}'")
    print(_render_root_help())
    raise SystemExit(2)


def _run_diag_mode(argv: Sequence[str]) -> int:
    """poor-cli diag {doctor|status|policy|tools|mcp} — consolidated diagnostics."""
    if not argv:
        print("usage: poor-cli diag {doctor|status|policy|tools|mcp} [options]")
        return 2
    verb = argv[0]
    rest = argv[1:]
    mapping = {
        "doctor": ("build_doctor_report", "poor-cli diag doctor"),
        "status": ("build_status_view", "poor-cli diag status"),
        "policy": ("get_policy_status", "poor-cli diag policy"),
        "tools": ("get_available_tools", "poor-cli diag tools"),
        "mcp": ("get_mcp_status", "poor-cli diag mcp"),
    }
    if verb not in mapping:
        print(f"poor-cli diag: unknown verb '{verb}' (expected: doctor|status|policy|tools|mcp)")
        return 2
    fn, prog = mapping[verb]
    return _run_core_info_command(fn, rest, prog)


def _run_pr_mode(argv: Sequence[str]) -> int:
    """poor-cli pr {review|task} — pull-request workflows.

    `poor-cli pr review <n>`      was `poor-cli review-pr <n>`.
    `poor-cli pr task <verb...>`  was `poor-cli github-task <verb...>`.
    """
    if not argv:
        print("usage: poor-cli pr {review|task} [options]")
        return 2
    verb = argv[0]
    rest = argv[1:]
    if verb == "review":
        return _run_review_pr_mode(rest)
    if verb == "task":
        return _run_github_task_mode(rest)
    print(f"poor-cli pr: unknown verb '{verb}' (expected: review|task)")
    return 2


def _run_install_mode(argv: Sequence[str]) -> int:
    """poor-cli install [info] — interactive installer, or show install details."""
    if argv and argv[0] == "info":
        print(f"poor-cli {__version__}")
        print(f"python: {sys.executable}")
        print("surface: headless CLI harness + JSON-RPC backend")
        print("run: poor-cli exec --prompt \"...\"")
        print("server: poor-cli server --stdio")
        return 0
    if argv and argv[0] not in {"", "run"}:
        print(f"poor-cli install: unknown verb '{argv[0]}' (expected: info, or omit for interactive)")
        return 2
    from .installer import show_landing
    return show_landing()


def _run_skill_mode(argv: Sequence[str]) -> int:
    """poor-cli skill {list|show|run|alias-list|alias-show|alias-run} — skills and
    the slash-command alias registry (formerly 'commands') collapsed onto one noun.
    """
    if not argv:
        return _run_skills_mode(argv)
    verb = argv[0]
    rest = argv[1:]
    alias_map = {
        "alias-list": ["list", *rest],
        "alias-show": ["show", *rest],
        "alias-run": ["run", *rest],
    }
    if verb in alias_map:
        return _run_commands_mode(alias_map[verb])
    return _run_skills_mode(argv)


def _run_deploy_umbrella(argv: Sequence[str]) -> int:
    """poor-cli deploy {run|preview|targets|validate|history} — collapse the
    former top-level `deploy`/`preview` into a single noun. Legacy
    `poor-cli deploy` (with just flags) now requires the `run` verb.
    """
    if not argv:
        print("usage: poor-cli deploy {run|preview|targets|validate|history} [options]")
        return 2
    verb = argv[0]
    rest = argv[1:]
    if verb == "run":
        return _run_deploy_mode(rest)
    if verb == "preview":
        return _run_preview_mode(rest)
    if verb == "targets":
        return _run_deploy_mode(["--list", *rest])
    if verb == "validate":
        return _run_deploy_mode(["--validate", *rest])
    if verb == "history":
        return _run_deploy_mode(["--history", *rest])
    print(f"poor-cli deploy: unknown verb '{verb}' (expected: run|preview|targets|validate|history)")
    return 2


def main() -> None:
    run_with_cli_error_handling(_main)


if __name__ == "__main__":
    main()
