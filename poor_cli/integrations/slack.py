"""
Slack integration for poor-cli.

Receives tasks via Slack messages mentioning @poor-cli and posts results
back to the channel. Uses conversations.history API for polling.
Requires SLACK_BOT_TOKEN env var.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from .base import Integration, IntegrationMessage
from ..exceptions import setup_logger

logger = setup_logger(__name__)

SLACK_API = "https://slack.com/api"


class SlackIntegration(Integration):
    """Slack bot integration using Web API with conversations.history polling."""

    def __init__(self, channels: Optional[List[str]] = None):
        self._token = os.environ.get("SLACK_BOT_TOKEN", "")
        self._connected = False
        self._session: Any = None
        self._bot_user_id: str = ""
        self._channels = channels or [] # channel IDs to poll
        self._last_poll_ts: Dict[str, str] = {} # channel -> oldest_unread ts

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
            async with self._session.get(f"{SLACK_API}/auth.test") as resp:
                data = await resp.json()
                if data.get("ok"):
                    self._connected = True
                    self._bot_user_id = data.get("user_id", "")
                    logger.info("slack connected as %s (id=%s)", data.get("user"), self._bot_user_id)
                    # auto-discover channels if none configured
                    if not self._channels:
                        self._channels = await self._discover_channels()
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
                f"{SLACK_API}/chat.postMessage",
                json={"channel": channel, "text": message},
            ) as resp:
                data = await resp.json()
                return data.get("ok", False)
        except Exception as exc:
            logger.error("slack send failed: %s", exc)
            return False

    async def poll(self) -> List[IntegrationMessage]:
        """Poll channels for new messages mentioning the bot."""
        if not self._connected or not self._session:
            return []
        messages: List[IntegrationMessage] = []
        for channel_id in self._channels:
            try:
                params: Dict[str, Any] = {"channel": channel_id, "limit": 20}
                oldest = self._last_poll_ts.get(channel_id)
                if oldest:
                    params["oldest"] = oldest
                async with self._session.get(
                    f"{SLACK_API}/conversations.history", params=params,
                ) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        logger.debug("slack poll %s failed: %s", channel_id, data.get("error"))
                        continue
                    for msg in data.get("messages", []):
                        ts = msg.get("ts", "")
                        text = msg.get("text", "")
                        user = msg.get("user", "")
                        # skip bot's own messages
                        if user == self._bot_user_id:
                            continue
                        # only process messages mentioning the bot
                        if self._bot_user_id and f"<@{self._bot_user_id}>" not in text:
                            continue
                        # strip the mention prefix
                        clean_text = text.replace(f"<@{self._bot_user_id}>", "").strip()
                        if not clean_text:
                            continue
                        messages.append(IntegrationMessage(
                            source="slack",
                            channel=channel_id,
                            author=user,
                            content=clean_text,
                            metadata={"ts": ts, "thread_ts": msg.get("thread_ts", "")},
                        ))
                        # track latest timestamp
                        if not oldest or ts > oldest:
                            self._last_poll_ts[channel_id] = ts
            except Exception as exc:
                logger.error("slack poll error for %s: %s", channel_id, exc)
        return messages

    async def _discover_channels(self) -> List[str]:
        """Find channels the bot is a member of."""
        if not self._session:
            return []
        try:
            async with self._session.get(
                f"{SLACK_API}/conversations.list",
                params={"types": "public_channel,private_channel", "limit": 100},
            ) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    return []
                channels = []
                for ch in data.get("channels", []):
                    if ch.get("is_member"):
                        channels.append(ch["id"])
                logger.info("discovered %d slack channels", len(channels))
                return channels
        except Exception as exc:
            logger.error("slack channel discovery failed: %s", exc)
            return []

    def status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connected": self._connected,
            "tokenSet": bool(self._token),
            "botUserId": self._bot_user_id,
            "channels": self._channels,
        }
