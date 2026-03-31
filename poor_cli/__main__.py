"""Launch poor-cli TUI by default or expose headless/automation subcommands."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from .automation_manager import (
    AutomationManager,
    parse_daily_schedule,
    parse_weekly_schedule,
    schedule_interval,
)
from .config import Config, ConfigManager, PermissionMode
from .core import PoorCLICore
from .cli_errors import run_with_cli_error_handling
from .custom_commands import CustomCommandRegistry
from .github_task import create_task_from_context, default_mode_for_context, load_github_context
from .repo_config import get_repo_config
from .sandbox import PRESET_DESCRIPTION, evaluate_tool_access, normalize_preset
from .skills import SkillRegistry
from .task_manager import APPROVAL_REQUIRED_PRESETS, TaskManager, run_task_worker
from .tui_launcher import launch_tui, run_install_info_mode
from . import __version__


def _render_root_help() -> str:
    return (
        "usage: poor-cli [subcommand] [options]\n\n"
        "Interactive surface:\n"
        "  poor-cli, poor-cli tui      Launch the Rust TUI (requires `poor-cli-tui`)\n"
        "  poor-cli install            Interactive installer and setup wizard\n"
        "  poor-cli install-info       Inspect which TUI launcher the current install can use\n\n"
        "Headless and automation:\n"
        "  poor-cli exec              Run one shared-core request from the terminal or CI\n"
        "  poor-cli task              Manage durable background tasks and worktrees\n"
        "  poor-cli agent             Manage background agents\n"
        "  poor-cli automation        Manage scheduled local automations\n"
        "  poor-cli github-task       Create a task from a GitHub event payload\n\n"
        "State and session:\n"
        "  poor-cli session           List, create, fork, or destroy sessions\n"
        "  poor-cli history           Search, list, or export conversation history\n"
        "  poor-cli checkpoint        List, create, preview, or restore checkpoints\n"
        "  poor-cli memory            List, save, search, or delete memory entries\n\n"
        "Configuration and diagnostics:\n"
        "  poor-cli config            List, get, set, or toggle configuration values\n"
        "  poor-cli provider          List, switch, or inspect AI providers\n"
        "  poor-cli profile           List or apply execution profiles\n"
        "  poor-cli trust             Show or manage repository trust\n"
        "  poor-cli doctor            Run structured diagnostics\n"
        "  poor-cli status            Show session status summary\n"
        "  poor-cli cost              Show session cost and economy settings\n"
        "  poor-cli policy            Show policy and audit hook status\n"
        "  poor-cli tools             List available tools\n"
        "  poor-cli mcp               Show MCP server status\n"
        "  poor-cli search            Search the codebase\n\n"
        "Code review and utilities:\n"
        "  poor-cli review            Review a file or staged diff\n"
        "  poor-cli commit            Generate a commit message from staged changes\n"
        "  poor-cli review-pr         Review a GitHub pull request\n"
        "  poor-cli deploy            Detect and deploy to platforms\n"
        "  poor-cli preview           Start a web preview server\n"
        "  poor-cli watch             Monitor files for inline instructions\n\n"
        "Reuse and integration:\n"
        "  poor-cli skills            List, inspect, or run repo/user skills\n"
        "  poor-cli commands          List, inspect, or run repo/user custom commands\n"
        "  poor-cli server            Run the JSON-RPC server (alias for `poor-cli-server`)\n"
        "  poor-cli telegram          Run the Telegram bot frontend\n"
        "  poor-cli telegram setup    Step-by-step Telegram bot setup guide\n\n"
        "Examples:\n"
        "  poor-cli\n"
        "  poor-cli exec --prompt \"Summarize this repository\" --plan-only\n"
        "  poor-cli task create --title \"Review docs\" --preset review-only --prompt \"Review README\"\n"
        "  poor-cli automation create --name \"Daily QA\" --every-minutes 60 --prompt \"Run QA checklist\"\n"
        "  poor-cli server --stdio\n\n"
        "Notes:\n"
        "  - The Python package always provides `poor-cli-server`.\n"
        "  - The interactive TUI can be launched from a repo build, a packaged binary, PATH, or POOR_CLI_TUI_BIN.\n"
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


def _build_exec_parser() -> argparse.ArgumentParser:
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
        choices=tuple(PRESET_DESCRIPTION.keys()),
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


def _build_exec_permission_callback(
    core: PoorCLICore,
    allow_tools: set[str],
    deny_tools: set[str],
    *,
    plan_only: bool,
    permission_mode: str,
    sandbox_preset: str,
    auto_approve: bool,
):
    async def _callback(tool_name: str, tool_args: dict[str, Any], preview: Optional[dict[str, Any]] = None):
        if plan_only:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if tool_name in deny_tools:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if allow_tools and tool_name not in allow_tools:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if not core.tool_registry:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}

        mutation_paths = list(preview.get("paths") or []) if isinstance(preview, dict) else []
        if not mutation_paths:
            mutation_paths = core.tool_registry.inspect_mutation_targets(tool_name, tool_args)

        security_cfg = getattr(core.config, "security", None)
        trusted_roots = _trusted_workspace_roots(security_cfg)
        enforce_trusted_workspace = bool(
            getattr(security_cfg, "enforce_trusted_workspace", True)
        ) if security_cfg is not None else True
        safe_commands = getattr(security_cfg, "safe_commands", None) if security_cfg is not None else None

        decision = evaluate_tool_access(
            tool_name=tool_name,
            tool_args=tool_args,
            tool_capabilities=core.tool_registry.get_tool_capabilities(tool_name),
            permission_mode=permission_mode,
            sandbox_preset=sandbox_preset,
            trusted_roots=trusted_roots,
            mutation_paths=mutation_paths,
            enforce_trusted_workspace=enforce_trusted_workspace,
            safe_process_commands=safe_commands,
        )
        if not decision.allowed:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        if decision.requires_approval and not auto_approve:
            return {"allowed": False, "approvedPaths": [], "approvedChunks": []}
        return {"allowed": True, "approvedPaths": [], "approvedChunks": []}

    return _callback


def _trusted_workspace_roots(security_cfg: Any) -> list[Path]:
    roots: list[Path] = []
    raw_roots = getattr(security_cfg, "trusted_roots", []) if security_cfg is not None else []
    if isinstance(raw_roots, list):
        for raw_root in raw_roots:
            if not isinstance(raw_root, str) or not raw_root.strip():
                continue
            root_path = Path(raw_root).expanduser()
            if not root_path.is_absolute():
                root_path = Path.cwd() / root_path
            roots.append(root_path.resolve())
    if not roots:
        roots.append(Path.cwd().resolve())

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


async def _run_exec_mode_async(args: argparse.Namespace) -> int:
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
            core.config.security.permission_mode = PermissionMode(args.permission_mode)
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
        effective_permission_mode = args.permission_mode or PermissionMode.PROMPT.value
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
    parser = _build_exec_parser()
    args = parser.parse_args(list(argv))
    return asyncio.run(_run_exec_mode_async(args))


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def _run_skill_async(name: str, request: str) -> int:
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
        return preset not in APPROVAL_REQUIRED_PRESETS

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
    approval_required = bool(requires_approval or (preset in APPROVAL_REQUIRED_PRESETS and not auto_approve))
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
    create.add_argument("--preset", default="workspace-write", choices=tuple(PRESET_DESCRIPTION.keys()))
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
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli watch")
    parser.add_argument("--debounce", type=float, default=2.0, help="Debounce seconds")
    parser.add_argument("--scan", action="store_true", help="Scan once and exit (don't watch)")
    args = parser.parse_args(list(argv))
    from .ide_watch import scan_directory_for_instructions, FileWatcher
    if args.scan:
        instructions = scan_directory_for_instructions()
        if not instructions:
            print("No poor-cli instructions found.")
        for instr in instructions:
            print(f"  {instr['file']}:{instr['line']}: {instr['instruction']}")
        return 0
    async def _on_instruction(instr: dict) -> None:
        print(f"[watch] {instr['file']}:{instr['line']}: {instr['instruction']}")
    watcher = FileWatcher(debounce=args.debounce, on_instruction=_on_instruction)
    print(f"Watching for # poor-cli: instructions (debounce={args.debounce}s)...")
    try:
        asyncio.run(watcher.start())
    except KeyboardInterrupt:
        pass
    return 0


def _run_deploy_mode(argv: Sequence[str]) -> int:
    """Handle 'poor-cli deploy'."""
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli deploy")
    parser.add_argument("--target", "-t", help="Deploy target (vercel, netlify, fly, railway, cloudflare)")
    parser.add_argument("--prod", action="store_true", help="Deploy to production")
    parser.add_argument("--list", action="store_true", help="List detected targets")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from .deploy import detect_deploy_targets, deploy
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
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli preview")
    parser.add_argument("--port", type=int, default=3456)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(list(argv))
    from .preview_server import PreviewServer
    server = PreviewServer(port=args.port)
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
    import argparse
    parser = argparse.ArgumentParser(prog="poor-cli review-pr")
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
    parser = argparse.ArgumentParser(prog="poor-cli skills")
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
    parser = argparse.ArgumentParser(prog="poor-cli commands")
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
    create.add_argument("--preset", default="read-only", choices=tuple(PRESET_DESCRIPTION.keys()))
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
    return parser


def _coerce_automation_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return str(args.prompt)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("`poor-cli automation create` requires --prompt or piped stdin.")


def _automation_schedule_from_args(args: argparse.Namespace) -> dict[str, Any]:
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
    parser = _build_automation_parser()
    args = parser.parse_args(list(argv))
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


def _validate_telegram_token(token: str) -> bool:
    """basic format check: <bot_id>:<alphanumeric_hash>."""
    import re
    return bool(re.match(r"^\d+:[A-Za-z0-9_-]{30,}$", token))


def _telegram_setup_guide() -> str:
    return (
        "telegram bot setup\n"
        "──────────────────\n"
        "1. open Telegram, search for @BotFather\n"
        "2. send /newbot and follow the prompts\n"
        "3. copy the token (format: 123456:ABC-DEF...)\n"
        "4. set it:\n"
        "     export POOR_CLI_TELEGRAM_TOKEN='<your-token>'\n"
        "   or pass --token on the command line\n"
        "5. (optional) restrict access with --allowed-users <id1,id2>\n"
        "   tip: send /start to @userinfobot to find your user ID\n"
        "6. run:\n"
        "     poor-cli telegram\n\n"
        "flags:\n"
        "  --verbose          show INFO-level logs on console\n"
        "  --debug            show DEBUG-level logs on console\n"
        "  --log-file <path>  write all logs to a file (default: ~/.poor-cli/telegram.log)\n"
        "  --sandbox-preset   capability sandbox (default: review-only)\n"
        "  --max-sessions     max concurrent user sessions (default: 5)\n"
        "  --webhook-url      use webhook mode instead of long-polling\n"
        "  --webhook-port     webhook server port (default: 8443)\n"
    )


def _print_telegram_banner(args: argparse.Namespace, token: str, log_file_path: str) -> None:
    masked = token[:8] + "..." + token[-4:] if len(token) > 16 else "***"
    print(
        "\n"
        "┌─────────────────────────────────────┐\n"
        "│  poor-cli telegram bot              │\n"
        "└─────────────────────────────────────┘\n"
        f"  token:          {masked}\n"
        f"  sandbox:        {args.sandbox_preset}\n"
        f"  max sessions:   {args.max_sessions}\n"
        f"  allowed users:  {args.allowed_users or 'all'}\n"
        f"  log file:       {log_file_path}\n"
        f"  log level:      {'DEBUG' if args.debug else 'VERBOSE' if args.verbose else 'WARNING (use --verbose for more)'}\n"
        f"  mode:           {'webhook' if args.webhook_url else 'long-polling'}\n"
        f"  edit interval:  {args.edit_interval}s\n"
    )
    if not args.allowed_users:
        print("  ⚠ no --allowed-users set — bot is open to ALL Telegram users\n")


def _run_telegram_mode(argv: Sequence[str]) -> int:
    if argv and argv[0] == "setup":
        print(_telegram_setup_guide())
        return 0
    parser = argparse.ArgumentParser(
        prog="poor-cli telegram",
        description="run the Telegram bot frontend for poor-cli",
        epilog="run 'poor-cli telegram setup' for first-time setup guide",
    )
    parser.add_argument("--token", help="Telegram bot token (or set POOR_CLI_TELEGRAM_TOKEN)")
    parser.add_argument("--allowed-users", help="comma-separated Telegram user IDs", default="")
    parser.add_argument("--sandbox-preset", default="review-only",
                        help="capability sandbox preset (default: review-only)")
    parser.add_argument("--max-sessions", type=int, default=5,
                        help="max concurrent user sessions (default: 5)")
    parser.add_argument("--edit-interval", type=float, default=1.5,
                        help="telegram message edit interval in seconds (default: 1.5)")
    parser.add_argument("--webhook-url", default=None, help="webhook URL (uses long-polling if unset)")
    parser.add_argument("--webhook-port", type=int, default=8443, help="webhook port (default: 8443)")
    parser.add_argument("--verbose", "-v", action="store_true", help="enable INFO-level console logs")
    parser.add_argument("--debug", action="store_true", help="enable DEBUG-level console logs")
    parser.add_argument("--log-file", default=None,
                        help="log file path (default: ~/.poor-cli/telegram.log)")
    args = parser.parse_args(argv)
    token = args.token or os.environ.get("POOR_CLI_TELEGRAM_TOKEN", "")
    if not token:
        print(
            "error: telegram bot token not found\n\n"
            "set the token via one of:\n"
            "  export POOR_CLI_TELEGRAM_TOKEN='<your-token>'\n"
            "  poor-cli telegram --token '<your-token>'\n\n"
            "run 'poor-cli telegram setup' for a step-by-step guide",
            file=sys.stderr,
        )
        return 1
    if not _validate_telegram_token(token):
        print(
            "error: token format looks invalid (expected <bot_id>:<hash>)\n"
            "get a valid token from @BotFather on Telegram\n"
            "run 'poor-cli telegram setup' for help",
            file=sys.stderr,
        )
        return 1
    import logging
    log_file_path = args.log_file or str(Path.home() / ".poor-cli" / "telegram.log")
    Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
    if args.debug:
        console_level = logging.DEBUG
    elif args.verbose:
        console_level = logging.INFO
    else:
        console_level = logging.WARNING
    from .exceptions import setup_logger as _setup_tg_logger, set_console_log_level
    _setup_tg_logger("poor_cli", log_file=log_file_path, level=logging.DEBUG, console_level=console_level)
    _setup_tg_logger("poor_cli.telegram", log_file=log_file_path, level=logging.DEBUG, console_level=console_level)
    set_console_log_level(console_level)
    _print_telegram_banner(args, token, log_file_path)
    allowed = set()
    if args.allowed_users:
        try:
            allowed = {int(uid.strip()) for uid in args.allowed_users.split(",") if uid.strip()}
        except ValueError as e:
            print(f"error: --allowed-users must be comma-separated integers: {e}", file=sys.stderr)
            return 1
    from .telegram import PoorCLITelegramBot
    bot = PoorCLITelegramBot(
        token=token,
        allowed_users=allowed or None,
        sandbox_preset=args.sandbox_preset,
        max_sessions=args.max_sessions,
        edit_interval=args.edit_interval,
        webhook_url=args.webhook_url,
        webhook_port=args.webhook_port,
    )
    async def _run() -> None:
        try:
            await bot.start()
        except Exception as e:
            print(f"\nerror: bot failed to start: {e}", file=sys.stderr)
            print(f"check logs at {log_file_path} for details", file=sys.stderr)
            return
        print("bot is running. press Ctrl+C to stop.\n")
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            print("\nshutting down...")
        finally:
            await bot.stop()
            print("bot stopped.")
    asyncio.run(_run())
    return 0


def _run_checkpoint_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli checkpoint")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int)
    p_list.add_argument("--json", action="store_true")
    p_create = sub.add_parser("create")
    p_create.add_argument("--description", "-d", default="manual checkpoint")
    p_create.add_argument("files", nargs="*")
    p_create.add_argument("--json", action="store_true")
    p_preview = sub.add_parser("preview")
    p_preview.add_argument("checkpoint_id")
    p_preview.add_argument("--json", action="store_true")
    p_restore = sub.add_parser("restore")
    p_restore.add_argument("checkpoint_id")
    p_restore.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from .checkpoint import CheckpointManager
    mgr = CheckpointManager(workspace_root=Path.cwd())
    if args.subcommand == "list":
        checkpoints = mgr.list_checkpoints(limit=args.limit)
        payload = [c.to_dict() for c in checkpoints]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No checkpoints found.")
            for c in payload:
                print(f"  {c['checkpoint_id']}  {c['created_at']}  {c['description']}  ({c['file_count']} files)")
        return 0
    if args.subcommand == "create":
        cp = mgr.create_checkpoint(file_paths=args.files or [], description=args.description)
        payload = cp.to_dict()
        if args.json:
            _print_json(payload)
        else:
            print(f"Checkpoint {payload['checkpoint_id']} created ({payload['file_count']} files)")
        return 0
    if args.subcommand == "preview":
        diffs = mgr.preview_checkpoint(args.checkpoint_id)
        if args.json:
            _print_json(diffs)
        else:
            if not diffs:
                print("No file changes in checkpoint.")
            for d in diffs:
                print(f"  {d.get('status', '?'):10s} {d.get('filePath', '?')}")
        return 0
    if args.subcommand == "restore":
        count = mgr.restore_checkpoint(args.checkpoint_id)
        payload = {"checkpoint_id": args.checkpoint_id, "restored_files": count}
        if args.json:
            _print_json(payload)
        else:
            print(f"Restored {count} files from checkpoint {args.checkpoint_id}")
        return 0
    raise SystemExit(f"Unknown checkpoint subcommand: {args.subcommand}")


def _run_history_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli history")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--json", action="store_true")
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--json", action="store_true")
    p_export = sub.add_parser("export")
    p_export.add_argument("session_id")
    p_export.add_argument("--output", "-o", required=True)
    args = parser.parse_args(list(argv))
    from .history import HistoryManager
    mgr = HistoryManager()
    if args.subcommand == "list":
        sessions = mgr.list_sessions(limit=args.limit)
        if args.json:
            _print_json([{"session_id": s[0], "started_at": s[1], "message_count": s[2]} for s in sessions])
        else:
            if not sessions:
                print("No sessions found.")
            for sid, started, count in sessions:
                print(f"  {sid}  {started}  ({count} messages)")
        return 0
    if args.subcommand == "search":
        results = mgr.search_messages(args.query, limit=args.limit)
        if args.json:
            _print_json(results)
        else:
            if not results:
                print("No results found.")
            for r in results:
                print(f"  [{r.get('role', '?')}] {r.get('content', '')[:120]}")
        return 0
    if args.subcommand == "export":
        mgr.export_session(args.session_id, Path(args.output).expanduser())
        print(f"Exported session {args.session_id} to {args.output}")
        return 0
    raise SystemExit(f"Unknown history subcommand: {args.subcommand}")


def _run_session_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli session")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--limit", type=int, default=10)
    p_list.add_argument("--json", action="store_true")
    p_create = sub.add_parser("create")
    p_create.add_argument("--label", default="")
    p_create.add_argument("--json", action="store_true")
    p_fork = sub.add_parser("fork")
    p_fork.add_argument("source_id")
    p_fork.add_argument("--label", default="")
    p_fork.add_argument("--json", action="store_true")
    p_destroy = sub.add_parser("destroy")
    p_destroy.add_argument("session_id")
    p_destroy.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from .session_manager import SessionManager
    mgr = SessionManager()
    if args.subcommand == "list":
        sessions = mgr.list_sessions()
        if args.json:
            _print_json(sessions)
        else:
            if not sessions:
                print("No sessions found.")
            for s in sessions:
                sid = s.get("session_id", s.get("id", "?"))
                label = s.get("label", "")
                status = s.get("status", "")
                print(f"  {sid}  {label}  {status}")
        return 0
    if args.subcommand == "create":
        session = mgr.create_session(label=args.label)
        payload = {"session_id": session.session_id, "label": args.label}
        if args.json:
            _print_json(payload)
        else:
            print(f"Session {session.session_id} created")
        return 0
    if args.subcommand == "fork":
        session = mgr.fork_session(args.source_id, label=args.label)
        payload = {"session_id": session.session_id, "forked_from": args.source_id}
        if args.json:
            _print_json(payload)
        else:
            print(f"Session {session.session_id} forked from {args.source_id}")
        return 0
    if args.subcommand == "destroy":
        mgr.destroy_session(args.session_id)
        if args.json:
            _print_json({"destroyed": args.session_id})
        else:
            print(f"Session {args.session_id} destroyed")
        return 0
    raise SystemExit(f"Unknown session subcommand: {args.subcommand}")


def _run_memory_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli memory")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--type")
    p_list.add_argument("--json", action="store_true")
    p_save = sub.add_parser("save")
    p_save.add_argument("--name", required=True)
    p_save.add_argument("--type", default="project")
    p_save.add_argument("--description", default="")
    p_save.add_argument("--content", required=True)
    p_save.add_argument("--json", action="store_true")
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--json", action="store_true")
    p_delete = sub.add_parser("delete")
    p_delete.add_argument("name")
    p_delete.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from .memory import MemoryManager, MemoryEntry
    mgr = MemoryManager()
    mgr.load()
    if args.subcommand == "list":
        entries = mgr.list_all(type_filter=args.type)
        payload = [e.to_dict() for e in entries]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No memory entries found.")
            for e in payload:
                print(f"  [{e.get('type', '?')}] {e.get('name', '?')}: {e.get('description', '')}")
        return 0
    if args.subcommand == "save":
        entry = MemoryEntry(name=args.name, type=args.type, description=args.description, content=args.content)
        mgr.save(entry)
        if args.json:
            _print_json(entry.to_dict())
        else:
            print(f"Saved memory entry: {args.name}")
        return 0
    if args.subcommand == "search":
        results = mgr.search(args.query, max_results=args.limit)
        payload = [e.to_dict() for e in results]
        if args.json:
            _print_json(payload)
        else:
            if not payload:
                print("No results found.")
            for e in payload:
                print(f"  [{e.get('type', '?')}] {e.get('name', '?')}: {e.get('description', '')}")
        return 0
    if args.subcommand == "delete":
        deleted = mgr.delete(args.name)
        if not deleted:
            raise SystemExit(f"Memory entry not found: {args.name}")
        if args.json:
            _print_json({"deleted": args.name})
        else:
            print(f"Deleted memory entry: {args.name}")
        return 0
    raise SystemExit(f"Unknown memory subcommand: {args.subcommand}")


def _run_config_mode(argv: Sequence[str]) -> int:
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
    raise SystemExit(f"Unknown config subcommand: {args.subcommand}")


def _run_profile_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli profile")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_apply = sub.add_parser("apply")
    p_apply.add_argument("name")
    p_apply.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from .profiles import ProfileManager
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


def _run_trust_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli trust")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("status")
    p_add = sub.add_parser("trust")
    p_add.add_argument("--path")
    p_rm = sub.add_parser("untrust")
    p_rm.add_argument("--path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    from .trust import TrustManager
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


def _run_provider_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli provider")
    sub = parser.add_subparsers(dest="subcommand", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_info = sub.add_parser("info")
    p_info.add_argument("--config", help="config file path")
    p_info.add_argument("--json", action="store_true")
    p_switch = sub.add_parser("switch")
    p_switch.add_argument("name")
    p_switch.add_argument("model", nargs="?")
    p_switch.add_argument("--config", help="config file path")
    p_switch.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    if args.subcommand == "list":
        from .providers.provider_factory import ProviderFactory
        providers = ProviderFactory.list_providers()
        payload = [{"name": name} for name in sorted(providers)]
        if args.json:
            _print_json(payload)
        else:
            for p in payload:
                print(f"  {p['name']}")
        return 0
    if args.subcommand == "info":
        async def _info():
            core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
            await core.initialize()
            try:
                return core.get_provider_info()
            finally:
                await core.shutdown()
        info = asyncio.run(_info())
        if args.json:
            _print_json(info)
        else:
            for k, v in info.items():
                print(f"  {k}: {v}")
        return 0
    if args.subcommand == "switch":
        async def _switch():
            core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
            await core.initialize()
            try:
                await core.switch_provider(args.name, model_name=args.model)
                return core.get_provider_info()
            finally:
                await core.shutdown()
        info = asyncio.run(_switch())
        if args.json:
            _print_json(info)
        else:
            print(f"Switched to {info.get('name', args.name)} / {info.get('model', args.model or 'default')}")
        return 0
    raise SystemExit(f"Unknown provider subcommand: {args.subcommand}")


def _run_core_info_command(method_name: str, argv: Sequence[str], prog: str) -> int:
    """Generic handler for core info queries (doctor, status, policy, tools, mcp, cost)."""
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--config", help="config file path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    async def _query():
        core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
        await core.initialize()
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


def _run_cost_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli cost")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("summary")
    p_economy = sub.add_parser("economy")
    p_economy.add_argument("preset", nargs="?", choices=("frugal", "balanced", "quality"))
    p_savings = sub.add_parser("savings")
    parser.add_argument("--config", help="config file path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv))
    cmd = args.subcommand or "summary"
    async def _run():
        core = PoorCLICore(config_path=Path(args.config).expanduser() if getattr(args, "config", None) else None)
        await core.initialize()
        try:
            if cmd == "summary":
                return core.get_session_cost_summary()
            if cmd == "savings":
                return core.get_economy_savings()
            if cmd == "economy":
                preset = getattr(args, "preset", None)
                if preset:
                    return core.set_economy_preset(preset)
                return {"current_preset": getattr(core.config, "economy_preset", "balanced")}
        finally:
            await core.shutdown()
        return {}
    result = asyncio.run(_run())
    if args.json:
        _print_json(result)
    else:
        _print_json(result)
    return 0


def _run_search_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli search")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--mode", choices=("semantic", "hybrid"), default="hybrid")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("index")
    sub.add_parser("stats")
    args = parser.parse_args(list(argv))
    from .indexer import CodebaseIndexer
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


def _run_review_file_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli review")
    parser.add_argument("file", nargs="?", help="file to review (default: staged diff)")
    parser.add_argument("--output-format", choices=("text", "json"), default="text")
    parser.add_argument("--config", help="config file path")
    args = parser.parse_args(list(argv))
    if args.file:
        prompt = f"Review the following file for issues, improvements, and best practices:\n\nFile: {args.file}"
    else:
        prompt = "Review the current staged git diff for issues, improvements, and best practices. Use git_diff to inspect changes."
    async def _run():
        core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
        await core.initialize()
        core.permission_callback = _build_exec_permission_callback(
            core, set(), set(), plan_only=False, permission_mode="auto-safe",
            sandbox_preset="review-only", auto_approve=True,
        )
        try:
            return await core.send_message_sync(prompt, source_kind="exec", source_id="cli-review")
        finally:
            await core.shutdown()
    result = asyncio.run(_run())
    if args.output_format == "json":
        _print_json({"review": result})
    else:
        print(result)
    return 0


def _run_commit_mode(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="poor-cli commit")
    parser.add_argument("--output-format", choices=("text", "json"), default="text")
    parser.add_argument("--config", help="config file path")
    args = parser.parse_args(list(argv))
    prompt = (
        "Generate a concise, conventional commit message for the currently staged git changes. "
        "Use git_diff and git_status to inspect the staged changes. "
        "Output ONLY the commit message, nothing else."
    )
    async def _run():
        core = PoorCLICore(config_path=Path(args.config).expanduser() if args.config else None)
        await core.initialize()
        core.permission_callback = _build_exec_permission_callback(
            core, set(), set(), plan_only=False, permission_mode="auto-safe",
            sandbox_preset="review-only", auto_approve=True,
        )
        try:
            return await core.send_message_sync(prompt, source_kind="exec", source_id="cli-commit")
        finally:
            await core.shutdown()
    result = asyncio.run(_run())
    if args.output_format == "json":
        _print_json({"commit_message": result})
    else:
        print(result)
    return 0


def _main() -> None:
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(launch_tui(argv))
    if argv[0] in {"help", "--help", "-h"}:
        print(_render_root_help())
        raise SystemExit(0)
    if argv[0] in {"version", "--version", "-V"}:
        print(__version__)
        raise SystemExit(0)
    if argv and argv[0] == "exec":
        raise SystemExit(_run_exec_mode(argv[1:]))
    if argv and argv[0] == "agent":
        raise SystemExit(_run_agent_mode(argv[1:]))
    if argv and argv[0] == "task":
        raise SystemExit(_run_task_mode(argv[1:]))
    if argv and argv[0] == "skills":
        raise SystemExit(_run_skills_mode(argv[1:]))
    if argv and argv[0] == "commands":
        raise SystemExit(_run_commands_mode(argv[1:]))
    if argv and argv[0] == "automation":
        raise SystemExit(_run_automation_mode(argv[1:]))
    if argv and argv[0] == "checkpoint":
        raise SystemExit(_run_checkpoint_mode(argv[1:]))
    if argv and argv[0] == "history":
        raise SystemExit(_run_history_mode(argv[1:]))
    if argv and argv[0] == "session":
        raise SystemExit(_run_session_mode(argv[1:]))
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
    if argv and argv[0] == "doctor":
        raise SystemExit(_run_core_info_command("build_doctor_report", argv[1:], "poor-cli doctor"))
    if argv and argv[0] == "status":
        raise SystemExit(_run_core_info_command("build_status_view", argv[1:], "poor-cli status"))
    if argv and argv[0] == "policy":
        raise SystemExit(_run_core_info_command("get_policy_status", argv[1:], "poor-cli policy"))
    if argv and argv[0] == "tools":
        raise SystemExit(_run_core_info_command("get_available_tools", argv[1:], "poor-cli tools"))
    if argv and argv[0] == "mcp":
        raise SystemExit(_run_core_info_command("get_mcp_status", argv[1:], "poor-cli mcp"))
    if argv and argv[0] == "cost":
        raise SystemExit(_run_cost_mode(argv[1:]))
    if argv and argv[0] == "search":
        raise SystemExit(_run_search_mode(argv[1:]))
    if argv and argv[0] == "review":
        raise SystemExit(_run_review_file_mode(argv[1:]))
    if argv and argv[0] == "commit":
        raise SystemExit(_run_commit_mode(argv[1:]))
    if argv and argv[0] == "watch":
        raise SystemExit(_run_watch_mode(argv[1:]))
    if argv and argv[0] == "deploy":
        raise SystemExit(_run_deploy_mode(argv[1:]))
    if argv and argv[0] == "preview":
        raise SystemExit(_run_preview_mode(argv[1:]))
    if argv and argv[0] == "review-pr":
        raise SystemExit(_run_review_pr_mode(argv[1:]))
    if argv and argv[0] == "github-task":
        raise SystemExit(_run_github_task_mode(argv[1:]))
    if argv and argv[0] == "server":
        raise SystemExit(_run_server_mode(argv[1:]))
    if argv and argv[0] == "telegram":
        raise SystemExit(_run_telegram_mode(argv[1:]))
    if argv and argv[0] == "install":
        from .installer import show_landing
        raise SystemExit(show_landing())
    if argv and argv[0] == "install-info":
        raise SystemExit(run_install_info_mode(argv[1:]))
    if argv and argv[0] == "tui":
        raise SystemExit(launch_tui(argv[1:]))
    raise SystemExit(launch_tui(argv))


def main() -> None:
    run_with_cli_error_handling(_main)


if __name__ == "__main__":
    main()
