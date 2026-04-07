"""Cloud background agent providers for remote execution."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class CloudAgentConfig:
    """Configuration for cloud agent execution."""
    provider: str = "none" # none | fly-io | github-codespaces
    api_key: str = ""
    image: str = "" # docker image for fly-io
    region: str = "iad" # fly.io region
    machine_size: str = "shared-cpu-1x" # fly.io machine size
    max_runtime: int = 3600


@dataclass
class CloudAgentStatus:
    """Status of a cloud-running agent."""
    agent_id: str
    provider: str
    remote_id: str # provider-specific ID (fly machine ID, codespace name)
    status: str # running | completed | failed | cancelled
    output: str = ""
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class CloudAgentProvider(ABC):
    """Abstract base for cloud agent execution backends."""

    @abstractmethod
    async def launch(self, agent_id: str, prompt: str, sandbox_preset: str, max_runtime: int) -> CloudAgentStatus:
        """Launch a remote agent. Returns initial status."""
        ...

    @abstractmethod
    async def poll(self, agent_id: str, remote_id: str) -> CloudAgentStatus:
        """Poll for agent status. Returns current status."""
        ...

    @abstractmethod
    async def cancel(self, agent_id: str, remote_id: str) -> bool:
        """Cancel a running agent. Returns True if cancelled."""
        ...

    @abstractmethod
    async def get_output(self, agent_id: str, remote_id: str) -> str:
        """Retrieve agent output/result."""
        ...


class FlyIoProvider(CloudAgentProvider):
    """Run agents on Fly.io machines."""

    def __init__(self, config: CloudAgentConfig):
        self._api_key = config.api_key or os.environ.get("FLY_API_TOKEN", "")
        self._image = config.image or "ghcr.io/poor-cli/poor-cli:latest"
        self._region = config.region
        self._machine_size = config.machine_size

    async def launch(self, agent_id: str, prompt: str, sandbox_preset: str, max_runtime: int) -> CloudAgentStatus:
        import aiohttp
        if not self._api_key:
            return CloudAgentStatus(agent_id=agent_id, provider="fly-io", remote_id="", status="failed", error="FLY_API_TOKEN not set")
        machine_config = {
            "image": self._image,
            "env": {"POOR_CLI_AGENT_PROMPT": prompt, "POOR_CLI_SANDBOX_PRESET": sandbox_preset},
            "guest": {"cpu_kind": "shared", "cpus": 1, "memory_mb": 512},
            "auto_destroy": True,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.machines.dev/v1/apps/poor-cli-agents/machines",
                    json={"config": machine_config, "region": self._region},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()
                    if resp.status >= 400:
                        return CloudAgentStatus(agent_id=agent_id, provider="fly-io", remote_id="", status="failed", error=str(data))
                    remote_id = data.get("id", "")
                    return CloudAgentStatus(agent_id=agent_id, provider="fly-io", remote_id=remote_id, status="running")
        except Exception as e:
            return CloudAgentStatus(agent_id=agent_id, provider="fly-io", remote_id="", status="failed", error=str(e))

    async def poll(self, agent_id: str, remote_id: str) -> CloudAgentStatus:
        import aiohttp
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.machines.dev/v1/apps/poor-cli-agents/machines/{remote_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    state = data.get("state", "unknown")
                    status = "running" if state in ("started", "created") else "completed" if state == "stopped" else "failed"
                    return CloudAgentStatus(agent_id=agent_id, provider="fly-io", remote_id=remote_id, status=status)
        except Exception as e:
            return CloudAgentStatus(agent_id=agent_id, provider="fly-io", remote_id=remote_id, status="failed", error=str(e))

    async def cancel(self, agent_id: str, remote_id: str) -> bool:
        import aiohttp
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.machines.dev/v1/apps/poor-cli-agents/machines/{remote_id}/stop",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    return resp.status < 400
        except Exception:
            return False

    async def get_output(self, agent_id: str, remote_id: str) -> str:
        return f"[fly-io agent {remote_id}] output retrieval not yet implemented"


class GitHubCodespacesProvider(CloudAgentProvider):
    """Run agents in GitHub Codespaces."""

    def __init__(self, config: CloudAgentConfig):
        self._api_key = config.api_key or os.environ.get("GITHUB_TOKEN", "")

    async def launch(self, agent_id: str, prompt: str, sandbox_preset: str, max_runtime: int) -> CloudAgentStatus:
        if not self._api_key:
            return CloudAgentStatus(agent_id=agent_id, provider="github-codespaces", remote_id="", status="failed", error="GITHUB_TOKEN not set")
        # codespaces API requires repo context — placeholder implementation
        return CloudAgentStatus(agent_id=agent_id, provider="github-codespaces", remote_id="", status="failed", error="codespaces provider not yet fully implemented")

    async def poll(self, agent_id: str, remote_id: str) -> CloudAgentStatus:
        return CloudAgentStatus(agent_id=agent_id, provider="github-codespaces", remote_id=remote_id, status="failed", error="not implemented")

    async def cancel(self, agent_id: str, remote_id: str) -> bool:
        return False

    async def get_output(self, agent_id: str, remote_id: str) -> str:
        return "[codespaces] not implemented"


_PROVIDERS: Dict[str, type] = {
    "fly-io": FlyIoProvider,
    "github-codespaces": GitHubCodespacesProvider,
}


def get_cloud_provider(config: CloudAgentConfig) -> Optional[CloudAgentProvider]:
    """Get cloud agent provider from config. Returns None if provider is 'none'."""
    if config.provider == "none" or not config.provider:
        return None
    provider_cls = _PROVIDERS.get(config.provider)
    if not provider_cls:
        logger.warning("unknown cloud agent provider: %s", config.provider)
        return None
    return provider_cls(config)
