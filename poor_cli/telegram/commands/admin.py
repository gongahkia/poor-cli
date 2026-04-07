"""Admin commands: config, trust, doctor, context, tools, services, economy."""

import time
from typing import Any
from poor_cli.telegram import formatter as fmt
from poor_cli.telegram.keyboards import economy_keyboard

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


async def _handle_config(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    sub = args[0] if args else "list"
    rest = " ".join(args[1:]) if len(args) > 1 else ""
    try:
        result = await _chat_cmd(core, f"/config {sub} {rest}".strip())
        pages = fmt.paginate(result or "config done")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_trust(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    sub = args[0] if args else "status"
    try:
        result = await _chat_cmd(core, f"/trust {sub}")
        await update.message.reply_text(result[:4000] or "trust done")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


def _format_uptime(seconds: float) -> str:
    if seconds <= 0:
        return "unknown"
    d = int(seconds // 86400)
    h = int((seconds % 86400) // 3600)
    m = int((seconds % 3600) // 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def _tg_bar(fraction: float, width: int = 10) -> str:
    """unicode progress bar for Telegram monospace."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def _tg_ok_bar(ok: bool, width: int = 8) -> str:
    return "█" * width if ok else "░" * width


def _tg_row(label: str, bar: str, value: str) -> str:
    return f"  {label:<12} {bar}  {value}"


def _tg_health(checks: list) -> tuple:
    """returns (score, emoji)."""
    if not checks:
        return 0, "🔴"
    score = round(sum(1 for c in checks if c) / len(checks) * 100)
    if score >= 80:
        return score, "🟢"
    elif score >= 50:
        return score, "🟡"
    return score, "🔴"


async def _handle_doctor(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    uptime = time.monotonic() - bot._start_time if bot._start_time else 0
    rate_status = bot._rate_limiter.get_status(uid)
    thread_count = bot._threads.get_thread_count(uid)
    cost = bot._costs.get_session_cost(uid)
    info = core.get_provider_info() if core._initialized else {}
    # health checks
    checks = [
        core._initialized,
        bool(info.get("name")),
        rate_status["user_tokens"] > 0,
        rate_status["global_tokens"] > 0,
        uptime > 0,
    ]
    score, emoji = _tg_health(checks)
    user_frac = rate_status["user_tokens"] / max(rate_status["user_capacity"], 1)
    global_frac = rate_status["global_tokens"] / max(rate_status["global_capacity"], 1)
    lines = [
        f"Status  {emoji} Health {score}",
        f"{'─' * 36}",
        "",
        "◉ Provider",
        _tg_row("Provider", _tg_ok_bar(core._initialized), info.get("name", "none")),
        _tg_row("Model", _tg_ok_bar(core._initialized), info.get("model", "n/a")),
        _tg_row("Uptime", _tg_bar(min(uptime / 86400, 1.0)), _format_uptime(uptime)),
        "",
        "◧ Session",
        _tg_row("Thread", _tg_ok_bar(True), tid),
        _tg_row("Threads", _tg_bar(min(thread_count / 10, 1.0)), str(thread_count)),
        _tg_row("Sandbox", _tg_ok_bar(True), bot._sandbox_preset),
        _tg_row("Sessions", _tg_bar(0.5), f"max {bot._max_sessions}"),
        "",
        "◈ Rate Limits",
        _tg_row("User", _tg_bar(user_frac), f"{rate_status['user_tokens']:.0f}/{rate_status['user_capacity']:.0f}"),
        _tg_row("Global", _tg_bar(global_frac), f"{rate_status['global_tokens']:.0f}/{rate_status['global_capacity']:.0f}"),
        "",
        "⚙ Cost",
        fmt.format_cost(cost),
        "",
        f"{'─' * 36}",
        f"DB: {bot._store._db_path}",
        f"Log: {bot._log_file or 'not set (--log-file)'}",
    ]
    diag = "\n".join(lines)
    if core._initialized:
        try:
            await bot._threads.ensure_initialized(core)
            if hasattr(core, 'build_doctor_report'):
                report = await core.build_doctor_report()
                if isinstance(report, dict):
                    import json
                    core_result = json.dumps(report, indent=2, ensure_ascii=False)
                else:
                    core_result = str(report)
            else:
                core_result = await _chat_cmd(core, "/doctor")
            if core_result and core_result.strip():
                diag += "\n\n── core ──\n" + core_result
        except Exception as e:
            diag += f"\n\ncore doctor failed: {e}"
    pages = fmt.paginate(diag)
    for page in pages:
        await update.effective_message.reply_text(page)


async def _handle_context(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    sub = args[0] if args else "preview"
    try:
        if sub == "compact":
            strategy = args[1] if len(args) > 1 else "auto"
            if hasattr(core, 'compact_context'):
                result = await core.compact_context(strategy)
                await update.message.reply_text(f"context compacted ({strategy})\n{result}")
            else:
                result = await _chat_cmd(core, f"/context compact {strategy}")
                await update.message.reply_text(result or f"context compacted ({strategy})")
        elif sub == "preview":
            if hasattr(core, 'preview_context'):
                result = await core.preview_context(message="", context_files=[], pinned_context_files=[])
                text = str(result)[:3000]
                await update.message.reply_text(f"context preview:\n{text}")
            else:
                result = await _chat_cmd(core, "/context preview")
                pages = fmt.paginate(result or "context preview unavailable")
                for page in pages:
                    await update.effective_message.reply_text(page)
        else:
            result = await _chat_cmd(core, f"/context {sub}")
            pages = fmt.paginate(result or "context done")
            for page in pages:
                await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_tools(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, "/tools")
        pages = fmt.paginate(result or "no tools")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_services(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    sub = args[0] if args else ""
    rest = " ".join(args[1:]) if len(args) > 1 else ""
    if not sub:
        await update.message.reply_text("usage: /services [start <name> <cmd>|stop <name>|status <name>|logs <name>]")
        return
    try:
        result = await _chat_cmd(core, f"/services {sub} {rest}".strip())
        await update.message.reply_text(result[:4000] or f"services {sub} done")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_economy(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    if not args:
        await update.message.reply_text("select economy preset:", reply_markup=economy_keyboard())
        return
    preset = args[0]
    if preset not in ("none", "light", "moderate", "aggressive"):
        await update.message.reply_text("usage: /economy [none|light|moderate|aggressive]")
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, f"/economy {preset}")
        await update.message.reply_text(result[:4000] or f"economy: {preset}")
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_readiness(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    if core and hasattr(core, 'get_provider_readiness'):
        result = core.get_provider_readiness()
        lines = [f"{k}: {'✓' if v else '✗'}" for k, v in result.items()]
        await update.message.reply_text("provider readiness:\n" + "\n".join(lines))
    else:
        checks = {
            "core": core is not None,
            "initialized": getattr(core, '_initialized', False) if core else False,
            "provider": bool(getattr(core, 'provider', None)) if core else False,
        }
        lines = [f"{k}: {'✓' if v else '✗'}" for k, v in checks.items()]
        await update.message.reply_text("provider readiness:\n" + "\n".join(lines))


def register(app, bot):
    for cmd, handler_fn in [
        ("config", _handle_config),
        ("trust", _handle_trust),
        ("doctor", _handle_doctor),
        ("context", _handle_context),
        ("tools", _handle_tools),
        ("services", _handle_services),
        ("economy", _handle_economy),
        ("readiness", _handle_readiness),
    ]:
        fn = handler_fn
        async def make_handler(update, context, _fn=fn):
            await _fn(bot, update, context)
        app.add_handler(CommandHandler(cmd, make_handler))
