"""Webhook mode support for Telegram bot."""

import asyncio
from typing import Any, Optional

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from telegram import Update
    from telegram.ext import Application
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


async def setup_webhook(app: Any, url: str, port: int = 8443,
                        secret_token: Optional[str] = None) -> bool:
    """configure webhook instead of polling. returns True on success."""
    if not AIOHTTP_AVAILABLE:
        logger.warning("aiohttp not installed, falling back to polling")
        return False
    try:
        webhook_url = f"{url}/webhook"
        await app.bot.set_webhook(url=webhook_url, secret_token=secret_token)
        logger.info("webhook set to %s", webhook_url)
        return True
    except Exception as e:
        logger.error("webhook setup failed: %s", e)
        return False


async def run_webhook_server(app: Any, port: int = 8443,
                             secret_token: Optional[str] = None) -> None:
    """run aiohttp server to receive webhook updates."""
    if not AIOHTTP_AVAILABLE:
        raise RuntimeError("aiohttp required for webhook mode")
    web_app = web.Application()
    web_app.router.add_get("/health", _health_check)
    web_app.router.add_post("/webhook", _make_webhook_handler(app, secret_token))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("webhook server running on port %d", port)
    try:
        await asyncio.Event().wait() # run forever
    finally:
        await runner.cleanup()


async def _health_check(request: Any) -> Any:
    return web.json_response({"status": "ok"})


def _make_webhook_handler(app: Any, secret_token: Optional[str] = None):
    async def handler(request: Any) -> Any:
        if secret_token:
            header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header_token != secret_token:
                return web.Response(status=403, text="forbidden")
        try:
            data = await request.json()
            update = Update.de_json(data, app.bot)
            await app.process_update(update)
            return web.Response(status=200, text="ok")
        except Exception as e:
            logger.error("webhook handler error: %s", e)
            return web.Response(status=500, text="error")
    return handler
