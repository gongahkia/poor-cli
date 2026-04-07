"""Execution control commands: sandbox, permission-mode, profile, mcp, policy, instructions, broke/my-treat, inbox, workspace-map, bootstrap, onboarding, runs, savings, plan, cancel, routing."""

import asyncio
from typing import Any
from poor_cli.telegram import formatter as fmt

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
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
        await update.message.reply_text(
            "current mode: "
            f"{mode}\n"
            "options: default, acceptEdits, plan, bypassPermissions, dontAsk "
            "(legacy: prompt, auto-safe, danger-full-access)"
        )
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


async def _handle_plan(bot, update: Any, context: Any) -> None:
    """toggle plan mode. /plan on|off|status"""
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    chat_id = update.effective_chat.id
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    if not core:
        await update.message.reply_text("no active session")
        return
    if not args or args[0] == "status":
        enabled = getattr(core, '_plan_mode_enabled', False)
        await update.message.reply_text(f"plan mode: {'on' if enabled else 'off'}")
        return
    if args[0] == "on":
        core._plan_mode_enabled = True
        async def _plan_callback(plan_data):
            text = f"📋 Plan Review\n\n{plan_data.get('summary', str(plan_data))[:3000]}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✓ Approve", callback_data="plan:approve:"),
                InlineKeyboardButton("✗ Reject", callback_data="plan:reject:"),
            ]])
            await update.message.reply_text(text, reply_markup=keyboard)
            future = asyncio.get_event_loop().create_future()
            bot._pending_plan_futures[chat_id] = future
            return await future
        core.plan_callback = _plan_callback
        await update.message.reply_text("plan mode enabled — plans require approval before execution")
    elif args[0] == "off":
        core._plan_mode_enabled = False
        core.plan_callback = None
        await update.message.reply_text("plan mode disabled")


async def _handle_cancel(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    if core and hasattr(core, 'cancel_request'):
        core.cancel_request()
        await update.message.reply_text("request cancelled")
    else:
        await update.message.reply_text("no active request")


async def _handle_routing(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    if not core:
        await update.message.reply_text("no active session")
        return
    if not args:
        mode = core.get_routing_mode() if hasattr(core, 'get_routing_mode') else "unknown"
        await update.message.reply_text(f"routing: {mode}\noptions: manual, cost, quality, auto")
        return
    result = core.set_routing_mode(args[0]) if hasattr(core, 'set_routing_mode') else None
    await update.message.reply_text(f"routing set: {result or args[0]}")


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
        ("plan", _handle_plan),
        ("cancel", _handle_cancel),
        ("routing", _handle_routing),
    ]:
        fn = handler_fn
        async def make_handler(update, context, _fn=fn):
            await _fn(bot, update, context)
        app.add_handler(CommandHandler(cmd, make_handler))
