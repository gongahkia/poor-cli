"""Docker-based sandbox for command execution in ephemeral containers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

from .exceptions import setup_logger
from .sandbox import SandboxPreset, normalize_preset

logger = setup_logger(__name__)

_DOCKER_IMAGE = os.environ.get("POOR_CLI_DOCKER_SANDBOX_IMAGE", "python:3.12-slim")


def is_inside_docker() -> bool:
    """Detect if currently running inside a Docker container."""
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore")
        return "docker" in cgroup or "containerd" in cgroup or "/lxc/" in cgroup
    except (FileNotFoundError, PermissionError):
        return False


def docker_available() -> bool:
    """Check if Docker daemon is reachable."""
    if not shutil.which("docker"):
        return False
    import subprocess
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def docker_sandbox_enabled() -> bool:
    """Check if Docker sandbox mode is active (env var or auto-detect)."""
    mode = os.environ.get("POOR_CLI_SANDBOX_MODE", "").lower()
    if mode == "docker":
        return docker_available()
    return False


def docker_sandboxed_command(
    command: str,
    preset: str,
    workspace: Optional[Path] = None,
    image: Optional[str] = None,
) -> List[str]:
    """Wrap a bash command in a Docker container. Returns argv list."""
    normalized = normalize_preset(preset)
    ws = str((workspace or Path.cwd()).resolve())
    img = image or _DOCKER_IMAGE
    if normalized == SandboxPreset.FULL_ACCESS.value:
        return [
            "docker", "run", "--rm",
            "-v", f"{ws}:/workspace",
            "-w", "/workspace",
            img, "bash", "-c", command,
        ]
    if normalized in (SandboxPreset.READ_ONLY.value, SandboxPreset.REVIEW_ONLY.value):
        return [
            "docker", "run", "--rm",
            "--read-only",
            "--tmpfs", "/tmp",
            "-v", f"{ws}:/workspace:ro",
            "-w", "/workspace",
            "--network=none",
            img, "bash", "-c", command,
        ]
    # workspace-write
    return [
        "docker", "run", "--rm",
        "--tmpfs", "/tmp",
        "-v", f"{ws}:/workspace",
        "-w", "/workspace",
        "--network=none",
        img, "bash", "-c", command,
    ]
