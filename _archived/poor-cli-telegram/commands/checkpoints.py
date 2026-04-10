"""Checkpoint management commands for Telegram."""

from typing import Any
from poor_cli.telegram.keyboards import checkpoint_keyboard

try:
    from telegram.ext import CommandHandler
except ImportError:
    pass


async def _handle_checkpoints(bot, update: Any, context: Any) -> None:
    uid = update.effective_user.id
    if not bot._is_authorized(uid):
        return
    args = (context.args or []) if context else []
    tid = bot._threads.get_active_thread(uid)
    core = bot._threads.get_core(uid, tid)
    await bot._threads.ensure_initialized(core)
    cm = getattr(core, 'checkpoint_manager', None)
    if not cm:
        await update.message.reply_text("checkpoint manager not available")
        return
    if not args or args[0] == "list":
        try:
            cps = await cm.list_checkpoints() if hasattr(cm, 'list_checkpoints') else cm.list_checkpoints_sync()
            if not cps:
                await update.message.reply_text("no checkpoints")
                return
            lines = []
            for c in cps[:15]:
                desc = c.get("description", "")[:40]
                cid = c.get("checkpointId", c.get("id", "?"))
                lines.append(f"• `{cid}` — {desc or '(no description)'}")
            await update.message.reply_text("\n".join(lines), reply_markup=checkpoint_keyboard(cps))
        except Exception as e:
            await update.message.reply_text(f"error: {e}")
    elif args[0] == "create":
        desc = " ".join(args[1:]) if len(args) > 1 else ""
        try:
            cp = cm.create_checkpoint(description=desc)
            cid = cp.get("checkpointId", cp.get("id", "?")) if isinstance(cp, dict) else str(cp)
            await update.message.reply_text(f"checkpoint created: `{cid}`")
        except Exception as e:
            await update.message.reply_text(f"error: {e}")
    elif args[0] == "restore" and len(args) > 1:
        try:
            cm.restore_checkpoint(args[1])
            await update.message.reply_text(f"restored checkpoint `{args[1]}`")
        except Exception as e:
            await update.message.reply_text(f"error: {e}")
    elif args[0] == "preview" and len(args) > 1:
        try:
            preview = cm.preview_checkpoint(args[1])
            text = str(preview)[:4000] if preview else "empty checkpoint"
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"error: {e}")
    elif args[0] == "gc":
        try:
            result = cm.gc_checkpoints()
            freed = result.get("freed_bytes", 0) if isinstance(result, dict) else 0
            await update.message.reply_text(f"gc complete. freed {freed} bytes")
        except Exception as e:
            await update.message.reply_text(f"error: {e}")
    else:
        await update.message.reply_text(
            "usage: /checkpoints [list|create [desc]|restore <id>|preview <id>|gc]"
        )


def register(app, bot):
    async def handler(update, context):
        await _handle_checkpoints(bot, update, context)
    app.add_handler(CommandHandler("checkpoints", handler))
