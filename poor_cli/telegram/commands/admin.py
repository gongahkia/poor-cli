"""Admin commands: config, trust, doctor, context, tools, services, economy."""

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


async def _handle_doctor(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, "/doctor")
        pages = fmt.paginate(result or "doctor: all ok")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


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


def register(app, bot):
    for cmd, handler_fn in [
        ("config", _handle_config),
        ("trust", _handle_trust),
        ("doctor", _handle_doctor),
        ("context", _handle_context),
        ("tools", _handle_tools),
        ("services", _handle_services),
        ("economy", _handle_economy),
    ]:
        fn = handler_fn
        async def make_handler(update, context, _fn=fn):
            await _fn(bot, update, context)
        app.add_handler(CommandHandler(cmd, make_handler))
