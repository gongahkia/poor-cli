"""Refactored main bot class for Telegram frontend."""

import asyncio
import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from poor_cli.core import PoorCLICore, CoreEvent
from poor_cli.exceptions import setup_logger, ConfigurationError, log_context
from poor_cli.telegram import formatter as fmt
from poor_cli.telegram.keyboards import (
    parse_callback, provider_keyboard, model_keyboard,
    thread_keyboard, action_keyboard, heartbeat_keyboard,
)
from poor_cli.telegram.commands import register_all
from poor_cli.telegram.persistence import TelegramSessionStore
from poor_cli.telegram.threads import ThreadManager
from poor_cli.telegram.cost_tracker import CostTracker
from poor_cli.telegram.permissions import PermissionManager
from poor_cli.telegram.rate_limiter import RateLimiter
from poor_cli.telegram.heartbeat import HeartbeatScheduler
from poor_cli.telegram.skills_bridge import SkillsBridge
from poor_cli.telegram.multiplayer_bridge import MultiplayerBridge
from poor_cli.telegram.vision import detect_image, detect_photo, download_and_encode, build_vision_prompt

logger = setup_logger(__name__)

try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        CallbackQueryHandler, filters, ContextTypes,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None # type: ignore[assignment,misc]
    Application = None # type: ignore[assignment,misc]

HELP_TEXT = """poor-cli Telegram bot

core:
/start — initialize session
/clear — clear conversation history
/status — show session status
/provider — switch provider/model
/threads — list conversation threads
/thread <name> — switch/create/delete thread
/cost — show cost summary
/heartbeat — manage periodic check-ins

workspace:
/sessions — manage sessions
/tasks — manage durable tasks
/automations — manage scheduled automations
/agents — manage background agents
/checkpoints — manage checkpoints
/git — git operations
/memory — persistent memory store
/search — semantic codebase search

admin:
/config — view/edit configuration
/trust — trust/sandbox management
/doctor — health diagnostics
/context — context preview/compact
/tools — list available tools
/services — manage background services
/economy — cost optimization presets

workflows:
/workflows — list/run workflow templates
/export — export conversation
/deploy — deploy project
/review — review a PR
/pair — multiplayer pairing
/skill — manage skills
/help — show this help

send any message to chat with the AI.
upload images or documents for analysis."""


class PoorCLITelegramBot:
    """manages per-user PoorCLICore sessions over Telegram with persistence."""

    def __init__(
        self,
        token: str,
        allowed_users: Optional[Set[int]] = None,
        sandbox_preset: str = "review-only",
        config_path: Optional[Path] = None,
        max_sessions: int = 20,
        edit_interval: float = 1.5,
        cwd: Optional[str] = None,
        db_path: Optional[Path] = None,
        webhook_url: Optional[str] = None,
        webhook_port: int = 8443,
    ):
        if not TELEGRAM_AVAILABLE:
            raise ConfigurationError(
                "Telegram bot requires 'python-telegram-bot>=21.0'. "
                "Install with: pip install 'poor-cli[telegram]'"
            )
        self._token = token
        self._allowed_users: Set[int] = allowed_users or set()
        self._sandbox_preset = sandbox_preset
        self._config_path = config_path
        self._max_sessions = max_sessions
        self._edit_interval = edit_interval
        self._cwd = cwd or str(Path.cwd())
        self._webhook_url = webhook_url
        self._webhook_port = webhook_port
        self._app: Optional[Any] = None
        self._store = TelegramSessionStore(db_path=db_path)
        self._threads = ThreadManager(self._store, config_path=config_path)
        self._costs = CostTracker(self._store)
        self._permissions = PermissionManager()
        self._rate_limiter = RateLimiter()
        self._heartbeat = HeartbeatScheduler(self._heartbeat_callback)
        self._skills = SkillsBridge()
        self._multiplayer = MultiplayerBridge(self._mp_send_callback)
        self._start_time: float = 0.0
        self._log_file: Optional[str] = None

    def _is_authorized(self, user_id: int) -> bool:
        if not self._allowed_users:
            return True
        return user_id in self._allowed_users

    async def start(self) -> None:
        """start the Telegram bot (long-polling or webhook)."""
        builder = Application.builder().token(self._token)
        self._app = builder.build()
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("clear", self._handle_clear))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(CommandHandler("provider", self._handle_provider))
        self._app.add_handler(CommandHandler("threads", self._handle_threads))
        self._app.add_handler(CommandHandler("thread", self._handle_thread))
        self._app.add_handler(CommandHandler("cost", self._handle_cost))
        self._app.add_handler(CommandHandler("skill", self._handle_skill))
        self._app.add_handler(CommandHandler("heartbeat", self._handle_heartbeat))
        self._app.add_handler(CommandHandler("help", self._handle_help))
        register_all(self._app, self)
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))
        self._app.add_handler(MessageHandler(filters.Document.ALL, self._handle_document))
        commands = [
            BotCommand("start", "initialize session"),
            BotCommand("clear", "clear history"),
            BotCommand("status", "session status"),
            BotCommand("provider", "switch provider/model"),
            BotCommand("threads", "list threads"),
            BotCommand("thread", "switch/create/delete thread"),
            BotCommand("cost", "cost summary"),
            BotCommand("skill", "manage skills"),
            BotCommand("heartbeat", "periodic check-ins"),
            BotCommand("sessions", "manage sessions"),
            BotCommand("tasks", "manage tasks"),
            BotCommand("automations", "manage automations"),
            BotCommand("agents", "manage agents"),
            BotCommand("checkpoints", "manage checkpoints"),
            BotCommand("git", "git operations"),
            BotCommand("memory", "memory store"),
            BotCommand("config", "configuration"),
            BotCommand("trust", "trust/sandbox"),
            BotCommand("doctor", "diagnostics"),
            BotCommand("context", "context preview"),
            BotCommand("tools", "list tools"),
            BotCommand("search", "codebase search"),
            BotCommand("workflows", "workflow templates"),
            BotCommand("export", "export conversation"),
            BotCommand("deploy", "deploy project"),
            BotCommand("review", "review PR"),
            BotCommand("pair", "multiplayer pair"),
            BotCommand("economy", "cost presets"),
            BotCommand("services", "manage services"),
            BotCommand("help", "show help"),
        ]
        await self._app.bot.set_my_commands(commands)
        logger.info("bot starting | allowed_users=%s sandbox=%s max_sessions=%d",
                     self._allowed_users or "all", self._sandbox_preset, self._max_sessions)
        await self._app.initialize()
        await self._app.start()
        self._start_time = time.monotonic()
        if self._webhook_url:
            from poor_cli.telegram.webhook import setup_webhook, run_webhook_server
            logger.info("attempting webhook setup: url=%s port=%d", self._webhook_url, self._webhook_port)
            ok = await setup_webhook(self._app, self._webhook_url, self._webhook_port)
            if ok:
                logger.info("webhook active at %s:%d", self._webhook_url, self._webhook_port)
                await run_webhook_server(self._app, self._webhook_port)
                return
            logger.warning("webhook setup failed, falling back to long-polling")
        await self._app.updater.start_polling()
        logger.info("bot running (long-polling)")

    async def stop(self) -> None:
        await self._heartbeat.shutdown()
        await self._multiplayer.shutdown()
        if self._app:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        self._store.close_all()

    # ── command handlers ──

    async def _handle_start(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        uname = getattr(update.effective_user, 'username', None) or str(uid)
        if not self._is_authorized(uid):
            logger.warning("unauthorized /start from user %d (@%s)", uid, uname)
            await update.message.reply_text("not authorized")
            return
        logger.info("user %d (@%s) /start", uid, uname)
        tid = self._threads.get_active_thread(uid)
        core = self._threads.get_core(uid, tid)
        try:
            await self._threads.ensure_initialized(core)
        except Exception as e:
            logger.error("provider init failed for user %d: %s\n%s", uid, e, traceback.format_exc())
            await update.message.reply_text(
                f"failed to initialize provider: {e}\n"
                "check your API keys and try /provider to switch"
            )
            return
        self._threads.update_session_meta(uid, tid, core)
        info = core.get_provider_info() if core._initialized else {}
        await update.message.reply_text(
            f"poor-cli ready\n"
            f"provider: {info.get('name', 'unknown')}\n"
            f"model: {info.get('model', 'unknown')}\n"
            f"thread: {tid}\n"
            f"send a message to start coding."
        )

    async def _handle_clear(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        tid = self._threads.get_active_thread(uid)
        core = self._threads.get_core(uid, tid)
        if core.provider:
            await core.provider.clear_history()
        self._permissions.reset_auto_approve(uid)
        await update.message.reply_text("history cleared")

    async def _handle_status(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        tid = self._threads.get_active_thread(uid)
        core = self._threads.get_core(uid, tid)
        info = core.get_provider_info() if core._initialized else {}
        thread_count = self._threads.get_thread_count(uid)
        cost = self._costs.get_session_cost(uid)
        uptime_s = time.monotonic() - self._start_time if self._start_time else 0
        uptime_m = int(uptime_s // 60)
        await update.message.reply_text(
            f"session active (uptime: {uptime_m}m)\n"
            f"provider: {info.get('name', 'unknown')}\n"
            f"model: {info.get('model', 'unknown')}\n"
            f"thread: {tid}\n"
            f"threads: {thread_count}\n"
            f"{fmt.format_cost(cost)}\n"
            f"use /doctor for full diagnostics"
        )

    async def _handle_provider(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        args = (context.args or []) if context else []
        if not args:
            await update.message.reply_text("select provider:", reply_markup=provider_keyboard())
            return
        provider_name = args[0]
        model_name = args[1] if len(args) > 1 else None
        tid = self._threads.get_active_thread(uid)
        core = self._threads.get_core(uid, tid)
        logger.info("provider_switch user=%d provider=%s model=%s", uid, provider_name, model_name)
        try:
            await core.initialize(provider_name=provider_name, model_name=model_name)
            self._threads.update_session_meta(uid, tid, core)
            info = core.get_provider_info()
            await update.message.reply_text(f"switched to {info.get('name')} / {info.get('model')}")
        except Exception as e:
            logger.error("provider_switch_failed user=%d provider=%s: %s\n%s",
                         uid, provider_name, e, traceback.format_exc())
            await update.message.reply_text(
                f"failed to switch provider: {e}\n\n"
                "common causes:\n"
                "• missing API key (check env vars)\n"
                "• invalid model name\n"
                "• provider service down"
            )

    async def _handle_threads(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        threads = self._threads.list_threads(uid)
        text = fmt.format_thread_list(threads)
        kb = thread_keyboard(threads) if threads else None
        await update.message.reply_text(text, reply_markup=kb)

    async def _handle_thread(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        args = (context.args or []) if context else []
        if not args:
            await update.message.reply_text("usage: /thread <name> | /thread delete <name>")
            return
        if args[0] == "delete" and len(args) > 1:
            name = args[1]
            if self._threads.archive_thread(uid, name):
                await update.message.reply_text(f"deleted thread `{name}`")
            else:
                await update.message.reply_text(f"thread `{name}` not found")
            return
        name = args[0]
        if self._threads.switch_thread(uid, name):
            await update.message.reply_text(f"switched to thread `{name}`")
        else:
            tid = self._threads.create_thread(uid, name)
            await update.message.reply_text(f"created and switched to thread `{tid}`")

    async def _handle_heartbeat(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        chat_id = update.effective_chat.id
        args = (context.args or []) if context else []
        if not args:
            await update.message.reply_text(
                "heartbeat: periodic AI check-ins\n"
                "usage: /heartbeat start [interval_min] [prompt] | /heartbeat stop",
                reply_markup=heartbeat_keyboard(uid),
            )
            return
        sub = args[0]
        if sub == "start":
            interval = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
            prompt = " ".join(args[2:]) if len(args) > 2 else None
            self._heartbeat.schedule_heartbeat(uid, chat_id, interval_minutes=interval, prompt=prompt)
            await update.message.reply_text(f"heartbeat started (every {interval}m)")
        elif sub == "stop":
            self._heartbeat.cancel_heartbeat(uid)
            await update.message.reply_text("heartbeat stopped")

    async def _handle_cost(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        session_cost = self._costs.get_session_cost(uid)
        total_cost = self._costs.get_user_total_cost(uid)
        await update.message.reply_text(
            f"session: {fmt.format_cost(session_cost)}\n"
            f"total: {fmt.format_cost(total_cost)}"
        )

    async def _handle_skill(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        args = (context.args or []) if context else []
        await self._skills.handle_skill_command(update, context, args)

    async def _handle_help(self, update: Any, context: Any) -> None:
        await update.message.reply_text(HELP_TEXT)

    # ── message handler ──

    async def _handle_message(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            await update.message.reply_text("not authorized")
            return
        if not self._rate_limiter.check_rate(uid):
            wait = self._rate_limiter.get_wait_time(uid)
            logger.info("rate limited user %d (wait %.0fs)", uid, wait)
            await update.message.reply_text(f"rate limited. wait {wait:.0f}s")
            return
        prompt = update.message.text
        if not prompt:
            return
        tid = self._threads.get_active_thread(uid)
        core = self._threads.get_core(uid, tid)
        request_id = uuid.uuid4().hex[:12]
        with log_context(session_id=f"{uid}:{tid}", request_id=request_id):
            logger.info("msg from user %d thread=%s len=%d", uid, tid, len(prompt))
            try:
                await self._threads.ensure_initialized(core)
            except Exception as e:
                logger.error("provider init failed: %s\n%s", e, traceback.format_exc())
                await update.message.reply_text(
                    f"provider initialization failed: {e}\ntry /provider to switch"
                )
                return
            self._threads.update_session_meta(uid, tid, core)
            self._threads.evict_lru(self._max_sessions)
            self._skills.set_core(core)
            await self._stream_response(update, core, prompt, uid, tid)

    async def _handle_photo(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        if not self._rate_limiter.check_rate(uid):
            return
        photos = update.message.photo
        if not photos:
            return
        largest = photos[-1] # highest res
        b64, mime = await download_and_encode(context.bot, largest.file_id)
        caption = update.message.caption or "analyze this image"
        prompt = build_vision_prompt([(b64, mime)], caption)
        tid = self._threads.get_active_thread(uid)
        core = self._threads.get_core(uid, tid)
        await self._threads.ensure_initialized(core)
        await self._stream_response(update, core, prompt, uid, tid)

    async def _handle_document(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        if not self._rate_limiter.check_rate(uid):
            return
        doc = update.message.document
        if not doc:
            return
        if detect_image(doc):
            b64, mime = await download_and_encode(context.bot, doc.file_id)
            caption = update.message.caption or "analyze this image"
            prompt = build_vision_prompt([(b64, mime)], caption)
        else:
            file = await context.bot.get_file(doc.file_id)
            content = (await file.download_as_bytearray()).decode("utf-8", errors="replace")
            caption = update.message.caption or f"analyze this file: {doc.file_name}"
            prompt = f"{caption}\n\n```\n{content[:8000]}\n```"
        tid = self._threads.get_active_thread(uid)
        core = self._threads.get_core(uid, tid)
        await self._threads.ensure_initialized(core)
        await self._stream_response(update, core, prompt, uid, tid)

    # ── callback query handler ──

    async def _handle_callback(self, update: Any, context: Any) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        uid = query.from_user.id
        if not self._is_authorized(uid):
            return
        data = parse_callback(query.data or "")
        action = data.get("action", "")
        value = data.get("value", "")
        extra = data.get("extra", "")
        if action == "perm":
            if value == "approve":
                await self._permissions.handle_permission_response(extra, True)
                await query.edit_message_text("approved")
            elif value == "deny":
                await self._permissions.handle_permission_response(extra, False)
                await query.edit_message_text("denied")
            elif value == "approve_all":
                await self._permissions.handle_permission_response(extra, True, approve_all=True)
                await query.edit_message_text("approved all future requests")
        elif action == "provider":
            if value == "back":
                await query.edit_message_text("select provider:", reply_markup=provider_keyboard())
            else:
                from poor_cli.telegram.keyboards import model_keyboard
                await query.edit_message_text(f"select model for {value}:", reply_markup=model_keyboard(value))
        elif action == "model":
            provider = value
            model = extra
            tid = self._threads.get_active_thread(uid)
            core = self._threads.get_core(uid, tid)
            try:
                await core.initialize(provider_name=provider, model_name=model)
                self._threads.update_session_meta(uid, tid, core)
                await query.edit_message_text(f"switched to {provider}/{model}")
            except Exception as e:
                await query.edit_message_text(f"failed: {e}")
        elif action == "thread":
            if value == "new":
                tid = self._threads.create_thread(uid)
                await query.edit_message_text(f"created thread `{tid}`")
            else:
                if self._threads.switch_thread(uid, value):
                    await query.edit_message_text(f"switched to thread `{value}`")
                else:
                    await query.edit_message_text(f"thread `{value}` not found")
        elif action == "action":
            if value == "cost":
                cost = self._costs.get_session_cost(uid)
                await query.edit_message_text(fmt.format_cost(cost))
            elif value == "retry":
                await query.edit_message_text("send your message again to retry")
            elif value == "cancel":
                await query.edit_message_text("request cancelled")
            elif value == "export":
                tid = self._threads.get_active_thread(uid)
                core = self._threads.get_core(uid, tid)
                try:
                    export = core.export_conversation(format="markdown") if hasattr(core, 'export_conversation') else None
                    if export:
                        content = export.get("content", str(export)) if isinstance(export, dict) else str(export)
                        await query.edit_message_text(content[:4000])
                    else:
                        await query.edit_message_text("nothing to export")
                except Exception as e:
                    await query.edit_message_text(f"export error: {e}")
        elif action == "sess":
            from poor_cli.telegram.commands.sessions import _handle_session_callback
            await _handle_session_callback(self, query, data)
        elif action == "task":
            from poor_cli.telegram.commands.tasks import _handle_task_callback
            await _handle_task_callback(self, query, data)
        elif action == "gitcmd":
            sub = value
            tid = self._threads.get_active_thread(uid)
            core = self._threads.get_core(uid, tid)
            await self._threads.ensure_initialized(core)
            result = ""
            try:
                cmd_map = {"status": "/git status", "log": "/git log --oneline -n 10",
                           "diff": "/git diff", "branches": "/git branch -a"}
                async for event in core.send_message_events(cmd_map.get(sub, "/git status")):
                    if event.type == "text_chunk":
                        result += event.data.get("chunk", "")
                    elif event.type == "done":
                        break
                await query.edit_message_text(result[:4000] or "no output")
            except Exception as e:
                await query.edit_message_text(f"error: {e}")
        elif action == "econ":
            preset = value
            tid = self._threads.get_active_thread(uid)
            core = self._threads.get_core(uid, tid)
            if hasattr(core, 'config') and core.config:
                core.config.economy_preset = preset
            await query.edit_message_text(f"economy: {preset}")
        elif action == "auto":
            tid = self._threads.get_active_thread(uid)
            core = self._threads.get_core(uid, tid)
            await self._threads.ensure_initialized(core)
            cmd = f"/automations {value} {extra}".strip()
            result = ""
            try:
                async for event in core.send_message_events(cmd):
                    if event.type == "text_chunk":
                        result += event.data.get("chunk", "")
                    elif event.type == "done":
                        break
                await query.edit_message_text(result[:4000] or f"automation {value} done")
            except Exception as e:
                await query.edit_message_text(f"error: {e}")
        elif action == "agent":
            tid = self._threads.get_active_thread(uid)
            core = self._threads.get_core(uid, tid)
            await self._threads.ensure_initialized(core)
            cmd = f"/agents {value} {extra}".strip()
            result = ""
            try:
                async for event in core.send_message_events(cmd):
                    if event.type == "text_chunk":
                        result += event.data.get("chunk", "")
                    elif event.type == "done":
                        break
                await query.edit_message_text(result[:4000] or f"agent {value} done")
            except Exception as e:
                await query.edit_message_text(f"error: {e}")
        elif action == "cp":
            tid = self._threads.get_active_thread(uid)
            core = self._threads.get_core(uid, tid)
            await self._threads.ensure_initialized(core)
            if value == "gc":
                cm = getattr(core, 'checkpoint_manager', None)
                if cm:
                    try:
                        result = cm.gc_checkpoints()
                        freed = result.get("freed_bytes", 0) if isinstance(result, dict) else 0
                        await query.edit_message_text(f"gc complete. freed {freed} bytes")
                    except Exception as e:
                        await query.edit_message_text(f"error: {e}")
                else:
                    await query.edit_message_text("checkpoint manager not available")
            elif value == "restore" and extra:
                cm = getattr(core, 'checkpoint_manager', None)
                if cm:
                    try:
                        cm.restore_checkpoint(extra)
                        await query.edit_message_text(f"restored checkpoint `{extra}`")
                    except Exception as e:
                        await query.edit_message_text(f"error: {e}")
                else:
                    await query.edit_message_text("checkpoint manager not available")
            elif value == "preview" and extra:
                cm = getattr(core, 'checkpoint_manager', None)
                if cm:
                    try:
                        preview = cm.preview_checkpoint(extra)
                        await query.edit_message_text(str(preview)[:4000])
                    except Exception as e:
                        await query.edit_message_text(f"error: {e}")
                else:
                    await query.edit_message_text("checkpoint manager not available")
        elif action == "skill":
            info = self._skills.get_skill_info(value)
            if info:
                await query.edit_message_text(f"skill: {info['name']}\n{info.get('description', '')}")
        elif action == "hb":
            if value == "pause":
                self._heartbeat.pause_heartbeat(uid)
                await query.edit_message_text("heartbeat paused")
            elif value == "resume":
                self._heartbeat.resume_heartbeat(uid)
                await query.edit_message_text("heartbeat resumed")
            elif value == "cancel":
                self._heartbeat.cancel_heartbeat(uid)
                await query.edit_message_text("heartbeat cancelled")

    # ── streaming response ──

    async def _stream_response(self, update: Any, core: PoorCLICore,
                                prompt: str, user_id: int, thread_id: str) -> None:
        sent = await update.effective_message.reply_text("thinking...")
        t0 = time.monotonic()
        try:
            accumulated = ""
            last_edit = 0.0
            tool_count = 0
            async for event in core.send_message_events(prompt):
                etype = event.type
                if etype == "text_chunk":
                    chunk = event.data.get("chunk", "")
                    accumulated = fmt.format_streaming_chunk(accumulated, chunk)
                    now = time.monotonic()
                    if now - last_edit >= self._edit_interval and accumulated.strip():
                        try:
                            await sent.edit_text(accumulated[:fmt.TELEGRAM_MSG_LIMIT])
                            last_edit = now
                        except Exception:
                            pass
                elif etype == "thinking_chunk":
                    pass # silent
                elif etype == "tool_call_start":
                    tool_name = event.data.get("toolName", "")
                    tool_args = event.data.get("toolArgs", {})
                    tool_count += 1
                    logger.debug("tool_call user=%d tool=%s args=%s", user_id, tool_name, list(tool_args.keys()))
                    tool_msg = fmt.format_tool_call(tool_name, tool_args)
                    accumulated += f"\n{tool_msg}\n"
                elif etype == "tool_result":
                    tool_name = event.data.get("toolName", "")
                    result_text = event.data.get("toolResult", "")
                    success = not event.data.get("isError", False)
                    if not success:
                        logger.warning("tool_error user=%d tool=%s result=%s", user_id, tool_name, str(result_text)[:200])
                    result_msg = fmt.format_tool_result(tool_name, str(result_text), success=success)
                    accumulated += f"\n{result_msg}\n"
                elif etype == "permission_request":
                    prompt_id = event.data.get("promptId", str(uuid.uuid4()))
                    tool_name = event.data.get("toolName", "")
                    tool_args = event.data.get("toolArgs", {})
                    logger.info("permission_request user=%d tool=%s", user_id, tool_name)
                    approved = await self._permissions.handle_permission_request(
                        update, None, tool_name, tool_args, prompt_id, user_id,
                    )
                    if not approved:
                        logger.info("permission_denied user=%d tool=%s", user_id, tool_name)
                        accumulated += f"\n❌ `{tool_name}` denied\n"
                elif etype == "cost_update":
                    self._costs.track_cost(user_id, thread_id, event.data)
                elif etype == "progress":
                    phase = event.data.get("phase", "")
                    msg = event.data.get("message", "")
                    if phase and msg:
                        try:
                            await sent.edit_text(f"[{phase}] {msg}")
                        except Exception:
                            pass
                elif etype == "error":
                    err_msg = event.data.get("message", "unknown error")
                    err_code = event.data.get("code", "")
                    logger.error("stream_error user=%d code=%s msg=%s", user_id, err_code, err_msg)
                    accumulated += f"\n❌ error: {err_msg}\n"
                elif etype == "done":
                    break
            elapsed = time.monotonic() - t0
            logger.info("response_done user=%d thread=%s tools=%d time=%.1fs len=%d",
                        user_id, thread_id, tool_count, elapsed, len(accumulated))
            if accumulated.strip():
                pages = fmt.paginate(accumulated)
                try:
                    await sent.edit_text(pages[0])
                except Exception:
                    pass
                for page in pages[1:]:
                    await update.effective_message.reply_text(page)
            else:
                await sent.edit_text("(no response)")
        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error("stream_failed user=%d thread=%s time=%.1fs error=%s\n%s",
                         user_id, thread_id, elapsed, e, traceback.format_exc())
            try:
                await sent.edit_text(f"error: {e}")
            except Exception:
                pass

    # ── callbacks for subsystems ──

    async def _heartbeat_callback(self, user_id: int, chat_id: int, prompt: str) -> None:
        """called by HeartbeatScheduler to run a heartbeat prompt."""
        tid = self._threads.get_active_thread(user_id)
        core = self._threads.get_core(user_id, tid)
        await self._threads.ensure_initialized(core)
        try:
            result = ""
            async for event in core.send_message_events(prompt):
                if event.type == "text_chunk":
                    result += event.data.get("chunk", "")
                elif event.type == "done":
                    break
            if result.strip() and self._app:
                pages = fmt.paginate(f"💓 heartbeat:\n{result}")
                for page in pages:
                    await self._app.bot.send_message(chat_id=chat_id, text=page)
        except Exception as e:
            logger.error("heartbeat failed for user %d: %s", user_id, e)

    async def _mp_send_callback(self, chat_id: int, text: str) -> None:
        """called by MultiplayerBridge to send messages."""
        if self._app:
            await self._app.bot.send_message(chat_id=chat_id, text=text)
