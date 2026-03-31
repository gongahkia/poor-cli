"""Session management commands for Telegram."""

from typing import Any
from poor_cli.telegram.keyboards import session_keyboard, parse_callback

try:
    from telegram.ext import CommandHandler, CallbackQueryHandler
except ImportError:
    pass


async def _handle_sessions(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    threads = bot._threads.list_threads(uid)
    if not threads:
        await update.message.reply_text("no sessions")
        return
    lines = []
    for t in threads:
        marker = " (active)" if t.get("active") else ""
        lines.append(f"• `{t['name']}`{marker} — {t.get('message_count', 0)} msgs")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=session_keyboard(threads),
    )


async def _handle_session_callback(bot, query, data) -> None:
    uid = query.from_user.id
    action = data.get("value", "")
    tid = data.get("extra", "")
    if action == "switch" and tid:
        if bot._threads.switch_thread(uid, tid):
            await query.edit_message_text(f"switched to `{tid}`")
        else:
            await query.edit_message_text(f"session `{tid}` not found")
    elif action == "fork" and tid:
        new_tid = bot._threads.create_thread(uid, f"{tid}-fork")
        await query.edit_message_text(f"forked to `{new_tid}`")
    elif action == "destroy" and tid:
        bot._threads.archive_thread(uid, tid)
        await query.edit_message_text(f"destroyed `{tid}`")
    elif action == "rename" and tid:
        await query.edit_message_text(f"send new name as: /thread <newname> (then destroy old `{tid}`)")
    elif action == "create":
        new_tid = bot._threads.create_thread(uid)
        await query.edit_message_text(f"created session `{new_tid}`")
    elif action == "save" and tid:
        await query.edit_message_text(f"session `{tid}` saved")
    else:
        await query.edit_message_text("unknown session action")


def register(app, bot):
    async def handler(update, context):
        await _handle_sessions(bot, update, context)
    app.add_handler(CommandHandler("sessions", handler))
