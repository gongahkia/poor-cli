"""Execution control commands: sandbox, permission-mode, profile, mcp, policy, instructions, broke/my-treat, inbox, workspace-map, bootstrap, onboarding, runs, savings."""

from typing import Any
from poor_cli.telegram import formatter as fmt

try:
    from telegram.ext import CommandHandler
except ImportError:
    pass


async def _chat_cmd(core, cmd):
    result = ""
    async for event in core.send_message_events(cmd):
        if event.type == "text_chunk":
            result += event.data.get("chunk", "")
        elif event.type == "done":
            break
    return result


async def _handle_sandbox(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    if not args:
        preset = getattr(getattr(core.config, "sandbox", None), "default_preset", "unknown")
        await update.message.reply_text(f"current sandbox: {preset}\noptions: read-only, review-only, workspace-write, full-access")
        return
    try:
        result = await _chat_cmd(core, f"/sandbox {args[0]}")
        await update.message.reply_text(result or f"sandbox set: {args[0]}")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_permission_mode(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    if not args:
        mode = getattr(getattr(core.config, "security", None), "permission_mode", "unknown")
        await update.message.reply_text(f"current mode: {mode}\noptions: prompt, auto-safe, danger-full-access")
        return
    try:
        result = await _chat_cmd(core, f"/permission-mode {args[0]}")
        await update.message.reply_text(result or f"permission mode: {args[0]}")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_profile(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    if not args:
        from poor_cli.profiles import ProfileManager
        mgr = ProfileManager()
        profiles = mgr.list_profiles()
        lines = ["available profiles:"] + [f"  {p.name}: {p.description}" for p in profiles]
        await update.message.reply_text("\n".join(lines))
        return
    try:
        result = await _chat_cmd(core, f"/profile {args[0]}")
        await update.message.reply_text(result or f"profile applied: {args[0]}")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_mcp(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    sub = args[0] if args else "status"
    try:
        if sub == "health":
            result = await _chat_cmd(core, "/mcp-health")
        else:
            status = core.get_mcp_status()
            import json
            result = json.dumps(status, indent=2, ensure_ascii=False)
        pages = fmt.paginate(result or "mcp status unavailable")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_policy(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        status = core.get_policy_status()
        import json
        result = json.dumps(status, indent=2, ensure_ascii=False)
        pages = fmt.paginate(result or "no policies")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_instructions(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        stack = core.inspect_instruction_stack()
        import json
        result = json.dumps(stack, indent=2, ensure_ascii=False)
        pages = fmt.paginate(result or "no instructions")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_broke(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        core.set_economy_preset("frugal")
        await update.message.reply_text("terse mode enabled (frugal economy)")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_my_treat(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        core.set_economy_preset("quality")
        await update.message.reply_text("rich mode enabled (quality economy)")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_inbox(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, "/tasks list --inbox")
        await update.message.reply_text(result or "inbox empty")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_runs(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    limit = int(args[0]) if args else 10
    try:
        runs = core.list_runs(limit=limit)
        if not runs:
            await update.message.reply_text("no recent runs")
            return
        lines = ["recent runs:"]
        for r in runs:
            lines.append(f"  {r.get('runId', '?')} [{r.get('status', '?')}] {r.get('sourceKind', '')}/{r.get('sourceId', '')}")
        pages = fmt.paginate("\n".join(lines))
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_savings(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        savings = core.get_economy_savings()
        import json
        result = json.dumps(savings, indent=2, ensure_ascii=False)
        await update.message.reply_text(result or "no savings data")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_workspace_map(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, "Analyze the workspace structure and provide a concise map of the project layout.")
        pages = fmt.paginate(result or "workspace map unavailable")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_bootstrap(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, "Analyze the project and provide bootstrap recommendations for development setup.")
        pages = fmt.paginate(result or "bootstrap analysis unavailable")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


def register(app, bot):
    for cmd, handler_fn in [
        ("sandbox", _handle_sandbox),
        ("permission_mode", _handle_permission_mode),
        ("profile", _handle_profile),
        ("mcp", _handle_mcp),
        ("policy", _handle_policy),
        ("instructions", _handle_instructions),
        ("broke", _handle_broke),
        ("my_treat", _handle_my_treat),
        ("inbox", _handle_inbox),
        ("runs", _handle_runs),
        ("savings", _handle_savings),
        ("workspace_map", _handle_workspace_map),
        ("bootstrap", _handle_bootstrap),
    ]:
        fn = handler_fn
        async def make_handler(update, context, _fn=fn):
            await _fn(bot, update, context)
        app.add_handler(CommandHandler(cmd, make_handler))
