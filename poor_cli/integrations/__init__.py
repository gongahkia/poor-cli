"""External service integrations for poor-cli."""

from .base import Integration, IntegrationMessage
from .slack import SlackIntegration
from .linear import LinearIntegration

__all__ = ["Integration", "IntegrationMessage", "SlackIntegration", "LinearIntegration"]
