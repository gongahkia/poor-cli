"""Workflow, search, export, deploy, review commands for Telegram."""

import tempfile
from pathlib import Path
from typing import Any
from poor_cli.telegram import formatter as fmt

try:
    from telegram.ext import CommandHandler
except ImportError:
    pass


async def _handle_workflows(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    if not args or args[0] == "list":
        try:
            wf = getattr(core, 'workflow_templates', None)
            workflows = wf.list_workflows() if wf else []
            if not workflows:
                await update.message.reply_text("no workflows")
                return
            lines = []
            for w in workflows:
                name = w.get("name", "?")
                desc = w.get("description", "")[:60]
                lines.append(f"• `{name}` — {desc}")
            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            await update.message.reply_text(f"error: {e}")
    elif args[0] == "run" and len(args) > 1:
        name = args[1]
        result = ""
        try:
            async for event in core.send_message_events(f"/{name}"):
                if event.type == "text_chunk":
                    result += event.data.get("chunk", "")
                elif event.type == "done":
                    break
            pages = fmt.paginate(result or "workflow complete")
            for page in pages:
                await update.effective_message.reply_text(page)
        except Exception as e:
            await update.message.reply_text(f"error: {e}")
    else:
        await update.message.reply_text("usage: /workflows [list|run <name>]")


async def _handle_search(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    if not args:
        await update.message.reply_text("usage: /search <query>")
        return
    query = " ".join(args)
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        indexer = getattr(core, 'indexer', None)
        if indexer and hasattr(indexer, 'hybrid_search'):
            results = indexer.hybrid_search(query, limit=10)
        elif indexer and hasattr(indexer, 'semantic_search'):
            results = indexer.semantic_search(query, limit=10)
        else:
            await update.message.reply_text("search index not available")
            return
        if not results:
            await update.message.reply_text("no results")
            return
        lines = [f"search: `{query}`"]
        for i, r in enumerate(results[:10], 1):
            path = r.get("path", r.get("file", "?"))
            lines.append(f"{i}. `{path}`")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_export(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    try:
        export = core.export_conversation(format="markdown") if hasattr(core, 'export_conversation') else None
        if not export:
            await update.message.reply_text("nothing to export")
            return
        content = export.get("content", str(export)) if isinstance(export, dict) else str(export)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, prefix='poor-cli-export-') as f:
            f.write(content)
            tmp_path = f.name
        await update.message.reply_document(
            document=open(tmp_path, 'rb'),
            filename=f"poor-cli-{tid}.md",
            caption="conversation export"
        )
        Path(tmp_path).unlink(missing_ok=True)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_deploy(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    target = args[0] if args else ""
    cmd = f"/deploy{' --target ' + target if target else ''}"
    result = ""
    try:
        async for event in core.send_message_events(cmd):
            if event.type == "text_chunk":
                result += event.data.get("chunk", "")
            elif event.type == "done":
                break
        pages = fmt.paginate(result or "deploy complete")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_review(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    if not args:
        await update.message.reply_text("usage: /review <pr_number>")
        return
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    result = ""
    try:
        async for event in core.send_message_events(f"/review-pr {args[0]}"):
            if event.type == "text_chunk":
                result += event.data.get("chunk", "")
            elif event.type == "done":
                break
        pages = fmt.paginate(result or "review complete")
        for page in pages:
            await update.effective_message.reply_text(page)
    except Exception as e:
        await update.message.reply_text(f"error: {e}")


async def _handle_pair(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    if not args:
        await update.message.reply_text("usage: /pair <invite_code> | /pair leave | /pair members")
        return
    sub = args[0]
    if sub == "leave":
        left = await bot._multiplayer.leave_session(uid)
        if not left:
            await update.message.reply_text("not in a session")
    elif sub == "members":
        session = bot._multiplayer.get_session(uid)
        if not session:
            await update.message.reply_text("not in a session")
            return
        sessions = bot._multiplayer.list_sessions()
        lines = [f"room: `{session.room_name}`"]
        for s in sessions:
            if s["room_name"] == session.room_name:
                mode = "monitor" if s["monitor_only"] else "participant"
                lines.append(f"  • user {s['user_id']} ({mode})")
        await update.message.reply_text("\n".join(lines))
    else:
        invite_code = sub
        room = args[1] if len(args) > 1 else "default"
        await bot._multiplayer.join_session(uid, chat_id, invite_code, room)


def register(app, bot):
    for cmd, handler_fn in [
        ("workflows", _handle_workflows),
        ("search", _handle_search),
        ("export", _handle_export),
        ("deploy", _handle_deploy),
        ("review", _handle_review),
        ("pair", _handle_pair),
    ]:
        fn = handler_fn
        async def make_handler(update, context, _fn=fn):
            await _fn(bot, update, context)
        app.add_handler(CommandHandler(cmd, make_handler))
