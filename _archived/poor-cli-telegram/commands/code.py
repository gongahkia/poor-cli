"""Code operation commands: review file, test, commit, diff, explain-diff, fix-failures."""

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


async def _handle_review_file(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    target = args[0] if args else None
    prompt = (
        f"Review the file {target} for issues, improvements, and best practices."
        if target else
        "Review the current staged git diff for issues, improvements, and best practices. "
        "Use git_diff to inspect changes."
    )
    try:
        result = await _chat_cmd(core, prompt)
        pages = fmt.paginate(result or "review complete")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_test(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    target = args[0] if args else None
    if not target:
        await update.message.reply_text("usage: /test <file>")
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, f"Generate comprehensive unit tests for the file {target}.")
        pages = fmt.paginate(result or "test generation complete")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_commit(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(
            core,
            "Generate a concise, conventional commit message for the currently staged git changes. "
            "Use git_diff and git_status to inspect the staged changes. Output ONLY the commit message.",
        )
        await update.message.reply_text(f"```\n{result}\n```", parse_mode=None)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_diff(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    if len(args) < 2:
        await update.message.reply_text("usage: /diff <file1> <file2>")
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        result = await _chat_cmd(core, f"Compare files {args[0]} and {args[1]} and show the differences.")
        pages = fmt.paginate(result or "no differences")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_explain_diff(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    target = args[0] if args else ""
    prompt = f"Explain the git diff{' for ' + target if target else ''}. Use git_diff to inspect changes."
    try:
        result = await _chat_cmd(core, prompt)
        pages = fmt.paginate(result or "no diff to explain")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_fix_failures(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    cmd = " ".join(args) if args else ""
    prompt = (
        f"Run `{cmd}`, analyze any failures, and propose fixes."
        if cmd else
        "Run the project's test suite, analyze any failures, and propose fixes."
    )
    try:
        result = await _chat_cmd(core, prompt)
        pages = fmt.paginate(result or "no failures found")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


def register(app, bot):
    for cmd, handler_fn in [
        ("review_file", _handle_review_file),
        ("test", _handle_test),
        ("commit_msg", _handle_commit),
        ("diff", _handle_diff),
        ("explain_diff", _handle_explain_diff),
        ("fix_failures", _handle_fix_failures),
    ]:
        fn = handler_fn
        async def make_handler(update, context, _fn=fn):
            await _fn(bot, update, context)
        app.add_handler(CommandHandler(cmd, make_handler))
