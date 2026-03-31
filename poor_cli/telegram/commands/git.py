"""Git operations commands for Telegram."""

from typing import Any
from poor_cli.telegram import formatter as fmt
from poor_cli.telegram.keyboards import git_keyboard

try:
    from telegram.ext import CommandHandler
except ImportError:
    pass


async def _handle_git(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    if not args:
        await update.message.reply_text("select git operation:", reply_markup=git_keyboard())
        return
    sub = args[0]
    try:
        if sub == "status":
            result = ""
            async for event in core.send_message_events("/git status"):
                if event.type == "text_chunk":
                    result += event.data.get("chunk", "")
                elif event.type == "done":
                    break
            await _send_result(update, result or "clean")
        elif sub == "log":
            count = args[1] if len(args) > 1 else "10"
            result = ""
            async for event in core.send_message_events(f"/git log --oneline -n {count}"):
                if event.type == "text_chunk":
                    result += event.data.get("chunk", "")
                elif event.type == "done":
                    break
            await _send_result(update, result or "no commits")
        elif sub == "diff":
            file_arg = args[1] if len(args) > 1 else ""
            cmd = f"/git diff {file_arg}".strip()
            result = ""
            async for event in core.send_message_events(cmd):
                if event.type == "text_chunk":
                    result += event.data.get("chunk", "")
                elif event.type == "done":
                    break
            await _send_result(update, result or "no changes")
        elif sub == "branches":
            result = ""
            async for event in core.send_message_events("/git branch -a"):
                if event.type == "text_chunk":
                    result += event.data.get("chunk", "")
                elif event.type == "done":
                    break
            await _send_result(update, result or "no branches")
        elif sub == "commit":
            msg = " ".join(args[1:]) if len(args) > 1 else ""
            if not msg:
                await update.message.reply_text("usage: /git commit <message>")
                return
            result = ""
            async for event in core.send_message_events(f'/git commit -m "{msg}"'):
                if event.type == "text_chunk":
                    result += event.data.get("chunk", "")
                elif event.type == "done":
                    break
            await _send_result(update, result or "committed")
        else:
            await update.message.reply_text(
                "usage: /git [status|log [n]|diff [file]|branches|commit <msg>]"
            )
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _send_result(update, text):
    pages = fmt.paginate(text)
    for page in pages:
        await update.effective_message.reply_text(page)


def register(app, bot):
    async def handler(update, context):
        await _handle_git(bot, update, context)
    app.add_handler(CommandHandler("git", handler))
