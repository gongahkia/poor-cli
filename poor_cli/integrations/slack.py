"""
Slack integration for poor-cli.

Receives tasks via Slack messages mentioning @poor-cli and posts results
back to the channel. Requires SLACK_BOT_TOKEN and SLACK_APP_TOKEN env vars.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from .base import Integration, IntegrationMessage
from ..exceptions import setup_logger

logger = setup_logger(__name__)


class SlackIntegration(Integration):
    """Slack bot integration using Web API."""

    def __init__(self):
        self._token = os.environ.get("SLACK_BOT_TOKEN", "")
        self._connected = False
        self._session: Any = None

    @property
    def name(self) -> str:
        return "slack"

    async def connect(self) -> bool:
        if not self._token:
            logger.warning("SLACK_BOT_TOKEN not set")
            return False
        try:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self._token}"}
            )
            # test connection
            async with self._session.get("https://slack.com/api/auth.test") as resp:
                data = await resp.json()
                if data.get("ok"):
                    self._connected = True
                    logger.info("slack connected as %s", data.get("user"))
                    return True
                logger.warning("slack auth failed: %s", data.get("error"))
                return False
        except ImportError:
            logger.warning("aiohttp required for Slack integration")
            return False
        except Exception as exc:
            logger.error("slack connect failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False

    async def send(self, channel: str, message: str) -> bool:
        if not self._connected or not self._session:
            return False
        try:
            async with self._session.post(
                "https://slack.com/api/chat.postMessage",
                json={"channel": channel, "text": message},
            ) as resp:
                data = await resp.json()
                return data.get("ok", False)
        except Exception as exc:
            logger.error("slack send failed: %s", exc)
            return False

    async def poll(self) -> List[IntegrationMessage]:
        # Slack Socket Mode or Events API would be used in production.
        # For now, return empty — real implementation needs websocket listener.
        return []

    def status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connected": self._connected,
            "tokenSet": bool(self._token),
        }
