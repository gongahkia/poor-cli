"""Base integration interface for external services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class IntegrationMessage:
    """Inbound message from an external service."""
    source: str # slack, linear, github, etc.
    channel: str # channel/project identifier
    author: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_prompt(self) -> str:
        return f"[{self.source}/{self.channel}] {self.author}: {self.content}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "channel": self.channel,
            "author": self.author,
            "content": self.content,
            "metadata": self.metadata,
        }


class Integration(ABC):
    """Abstract base for external service integrations."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the external service. Returns True on success."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the external service."""
        ...

    @abstractmethod
    async def send(self, channel: str, message: str) -> bool:
        """Send a message to the external service."""
        ...

    @abstractmethod
    async def poll(self) -> List[IntegrationMessage]:
        """Poll for new inbound messages."""
        ...

    def status(self) -> Dict[str, Any]:
        return {"name": self.name, "connected": False}
