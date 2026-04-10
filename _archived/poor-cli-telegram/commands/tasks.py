"""Task management commands for Telegram."""

from typing import Any
from poor_cli.telegram import formatter as fmt
from poor_cli.telegram.keyboards import task_keyboard

try:
    from telegram.ext import CommandHandler
except ImportError:
    pass


async def _chat_cmd(core, cmd):
    """run a slash command through core and collect text result."""
    result = ""
    async for event in core.send_message_events(cmd):
        if event.type == "text_chunk":
            result += event.data.get("chunk", "")
        elif event.type == "done":
            break
    return result


async def _handle_tasks(bot, update: Any, context: Any) -> None:
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
        if sub == "list":
            result = await _chat_cmd(core, "/tasks list")
            pages = fmt.paginate(result or "no tasks")
            for page in pages:
                await update.effective_message.reply_text(page)
        elif sub == "create" and rest:
            result = await _chat_cmd(core, f"/tasks create {rest}")
            await update.message.reply_text(result[:4000] or "task created")
        elif sub in ("show", "start", "approve", "cancel", "retry", "replay") and rest:
            result = await _chat_cmd(core, f"/tasks {sub} {rest}")
            await update.message.reply_text(result[:4000] or f"task {sub} done")
        else:
            await update.message.reply_text(
                "usage: /tasks [list|create <prompt>|show <id>|start <id>|approve <id>|cancel <id>|retry <id>|replay <id>]"
            )
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_task_callback(bot, query, data) -> None:
    uid = query.from_user.id
    action = data.get("value", "")
    task_id = data.get("extra", "")
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, f"/tasks {action} {task_id}")
        await query.edit_message_text(result[:4000] or f"task {action} done")
    except Exception as e:
        await query.edit_message_text(f"error: {e}")


def register(app, bot):
    async def handler(update, context):
        await _handle_tasks(bot, update, context)
    app.add_handler(CommandHandler("tasks", handler))
