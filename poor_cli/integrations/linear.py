"""
Linear integration for poor-cli.

Syncs issues from Linear as agent tasks. Requires LINEAR_API_KEY env var.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .base import Integration, IntegrationMessage
from ..exceptions import setup_logger

logger = setup_logger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearIntegration(Integration):
    """Linear issue tracker integration."""

    def __init__(self):
        self._api_key = os.environ.get("LINEAR_API_KEY", "")
        self._connected = False
        self._session: Any = None

    @property
    def name(self) -> str:
        return "linear"

    async def connect(self) -> bool:
        if not self._api_key:
            logger.warning("LINEAR_API_KEY not set")
            return False
        try:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": self._api_key,
                    "Content-Type": "application/json",
                }
            )
            # test connection
            query = '{"query": "{ viewer { id name } }"}'
            async with self._session.post(LINEAR_API_URL, data=query) as resp:
                data = await resp.json()
                viewer = data.get("data", {}).get("viewer", {})
                if viewer.get("id"):
                    self._connected = True
                    logger.info("linear connected as %s", viewer.get("name"))
                    return True
            return False
        except ImportError:
            logger.warning("aiohttp required for Linear integration")
            return False
        except Exception as exc:
            logger.error("linear connect failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False

    async def send(self, channel: str, message: str) -> bool:
        """Post a comment on a Linear issue. Channel = issue ID."""
        if not self._connected or not self._session:
            return False
        mutation = json.dumps({
            "query": """
                mutation($issueId: String!, $body: String!) {
                    commentCreate(input: {issueId: $issueId, body: $body}) {
                        success
                    }
                }
            """,
            "variables": {"issueId": channel, "body": message},
        })
        try:
            async with self._session.post(LINEAR_API_URL, data=mutation) as resp:
                data = await resp.json()
                return bool(data.get("data", {}).get("commentCreate", {}).get("success"))
        except Exception as exc:
            logger.error("linear comment failed: %s", exc)
            return False

    async def poll(self) -> List[IntegrationMessage]:
        """Fetch assigned issues as inbound messages."""
        if not self._connected or not self._session:
            return []
        query = json.dumps({
            "query": """
                {
                    viewer {
                        assignedIssues(first: 10, filter: {state: {type: {in: ["started", "unstarted"]}}}) {
                            nodes { id identifier title description }
                        }
                    }
                }
            """
        })
        try:
            async with self._session.post(LINEAR_API_URL, data=query) as resp:
                data = await resp.json()
                issues = data.get("data", {}).get("viewer", {}).get("assignedIssues", {}).get("nodes", [])
                return [
                    IntegrationMessage(
                        source="linear",
                        channel=issue["id"],
                        author="linear",
                        content=f"{issue.get('identifier', '')}: {issue.get('title', '')}\n\n{issue.get('description', '')}",
                        metadata={"issueId": issue["id"], "identifier": issue.get("identifier", "")},
                    )
                    for issue in issues
                ]
        except Exception as exc:
            logger.error("linear poll failed: %s", exc)
            return []

    def status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connected": self._connected,
            "apiKeySet": bool(self._api_key),
        }
