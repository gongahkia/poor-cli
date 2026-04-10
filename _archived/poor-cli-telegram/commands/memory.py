"""Memory management commands for Telegram."""

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


async def _handle_memory(bot, update: Any, context: Any) -> None:
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
        if sub in ("list", "save", "search", "delete"):
            result = await _chat_cmd(core, f"/memory {sub} {rest}".strip())
            pages = fmt.paginate(result or f"memory {sub} done")
            for page in pages:
                await update.effective_message.reply_text(page)
        else:
            await update.message.reply_text(
                "usage: /memory [list|save <key> <value>|search <query>|delete <key>]"
            )
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


def register(app, bot):
    async def handler(update, context):
        await _handle_memory(bot, update, context)
    app.add_handler(CommandHandler("memory", handler))
