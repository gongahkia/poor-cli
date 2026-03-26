"""Telegram bot frontend for poor-cli."""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from .exceptions import setup_logger, ConfigurationError
from .core import PoorCLICore
from . import telegram_formatter as fmt

logger = setup_logger(__name__)

try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None
    Application = None


class PoorCLITelegramBot:
    """manages per-user PoorCLICore sessions over Telegram."""

    def __init__(
        self,
        token: str,
        allowed_users: Optional[Set[int]] = None,
        sandbox_preset: str = "review-only",
        config_path: Optional[Path] = None,
        max_sessions: int = 5,
        edit_interval: float = 1.5,
        cwd: Optional[str] = None,
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
        self._sessions: Dict[int, PoorCLICore] = {} # telegram user_id -> core
        self._app: Optional[Any] = None

    def _is_authorized(self, user_id: int) -> bool:
        if not self._allowed_users:
            return True # no whitelist = open
        return user_id in self._allowed_users

    def _get_or_create_core(self, user_id: int) -> PoorCLICore:
        if user_id not in self._sessions:
            if len(self._sessions) >= self._max_sessions:
                oldest = min(self._sessions.keys())
                del self._sessions[oldest]
                logger.info("evicted oldest session for user %d", oldest)
            core = PoorCLICore(config_path=self._config_path)
            self._sessions[user_id] = core
        return self._sessions[user_id]

    async def _ensure_initialized(self, core: PoorCLICore) -> None:
        if not core._initialized:
            await core.initialize()

    async def start(self) -> None:
        """start the Telegram bot (long-polling)."""
        builder = Application.builder().token(self._token)
        self._app = builder.build()
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("clear", self._handle_clear))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(CommandHandler("provider", self._handle_provider))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_handler(MessageHandler(filters.Document.ALL, self._handle_document))
        commands = [
            BotCommand("start", "initialize a new session"),
            BotCommand("clear", "clear conversation history"),
            BotCommand("status", "show session status"),
            BotCommand("provider", "switch provider (e.g. /provider openai gpt-5)"),
        ]
        await self._app.bot.set_my_commands(commands)
        logger.info("Telegram bot starting (allowed users: %s)", self._allowed_users or "all")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot running")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def _handle_start(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            await update.message.reply_text("⛔ not authorized")
            return
        core = self._get_or_create_core(uid)
        await self._ensure_initialized(core)
        await update.message.reply_text(
            f"👋 poor-cli ready\n"
            f"Provider: {core.config.model.provider}\n"
            f"Model: {core.config.model.model_name}\n"
            f"Send a message to start coding."
        )

    async def _handle_clear(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        if uid in self._sessions:
            core = self._sessions[uid]
            if core.provider:
                await core.provider.clear_history()
            await update.message.reply_text("🧹 history cleared")
        else:
            await update.message.reply_text("no active session")

    async def _handle_status(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        if uid in self._sessions:
            core = self._sessions[uid]
            info = core.get_provider_info() if core._initialized else {}
            await update.message.reply_text(
                f"📊 session active\n"
                f"Provider: {info.get('name', 'unknown')}\n"
                f"Model: {info.get('model', 'unknown')}\n"
                f"Sessions: {len(self._sessions)}/{self._max_sessions}"
            )
        else:
            await update.message.reply_text("no active session — send /start")

    async def _handle_provider(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        args = (context.args or []) if context else []
        if not args:
            await update.message.reply_text("usage: /provider <name> [model]")
            return
        provider_name = args[0]
        model_name = args[1] if len(args) > 1 else None
        core = self._get_or_create_core(uid)
        try:
            await core.initialize(provider_name=provider_name, model_name=model_name)
            info = core.get_provider_info()
            await update.message.reply_text(f"✅ switched to {info.get('name')} / {info.get('model')}")
        except Exception as e:
            await update.message.reply_text(f"❌ failed: {e}")

    async def _handle_message(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            await update.message.reply_text("⛔ not authorized")
            return
        prompt = update.message.text
        if not prompt:
            return
        core = self._get_or_create_core(uid)
        await self._ensure_initialized(core)
        sent = await update.message.reply_text("⏳ thinking...")
        try:
            accumulated = ""
            last_edit = 0.0
            import time
            async for event in core.send_message_events(prompt):
                etype = getattr(event, "type", "")
                if etype == "text_chunk":
                    chunk = getattr(event, "text", "")
                    accumulated = fmt.format_streaming_chunk(accumulated, chunk)
                    now = time.monotonic()
                    if now - last_edit >= self._edit_interval and accumulated.strip():
                        try:
                            await sent.edit_text(accumulated[:fmt.TELEGRAM_MSG_LIMIT])
                            last_edit = now
                        except Exception:
                            pass
                elif etype == "tool_call_start":
                    tool_name = getattr(event, "tool_name", "")
                    tool_args = getattr(event, "tool_args", {})
                    tool_msg = fmt.format_tool_call(tool_name, tool_args)
                    accumulated += f"\n{tool_msg}\n"
                elif etype == "tool_result":
                    tool_name = getattr(event, "tool_name", "")
                    result_text = getattr(event, "result", "")
                    result_msg = fmt.format_tool_result(tool_name, str(result_text))
                    accumulated += f"\n{result_msg}\n"
            # final edit
            if accumulated.strip():
                pages = fmt.paginate(accumulated)
                try:
                    await sent.edit_text(pages[0])
                except Exception:
                    pass
                for page in pages[1:]:
                    await update.message.reply_text(page)
            else:
                await sent.edit_text("(no response)")
        except Exception as e:
            logger.error("telegram message handling failed: %s", e)
            try:
                await sent.edit_text(f"❌ error: {e}")
            except Exception:
                pass

    async def _handle_document(self, update: Any, context: Any) -> None:
        uid = update.effective_user.id
        if not self._is_authorized(uid):
            return
        doc = update.message.document
        if not doc:
            return
        file = await context.bot.get_file(doc.file_id)
        content = (await file.download_as_bytearray()).decode("utf-8", errors="replace")
        caption = update.message.caption or f"analyze this file: {doc.file_name}"
        prompt = f"{caption}\n\n```\n{content[:8000]}\n```"
        update.message.text = prompt
        await self._handle_message(update, context)
