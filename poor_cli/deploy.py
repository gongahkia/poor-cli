"""
Cloud deployment integration for poor-cli.

Detects project type and available deployment CLIs, then deploys
via Vercel, Netlify, Fly.io, Railway, or Cloudflare Pages.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class DeployTarget:
    """A detected deployment target."""
    name: str
    cli_command: str
    available: bool
    config_file: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cliCommand": self.cli_command,
            "available": self.available,
            "configFile": self.config_file,
            "description": self.description,
        }


@dataclass
class DeployResult:
    """Result of a deployment."""
    target: str
    success: bool
    url: str = ""
    message: str = ""
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "success": self.success,
            "url": self.url,
            "message": self.message,
        }


def detect_deploy_targets(root: Optional[str] = None) -> List[DeployTarget]:
    """Detect available deployment targets based on config files and CLIs."""
    root_path = Path(root or ".").resolve()
    targets = []

    # vercel
    targets.append(DeployTarget(
        name="vercel",
        cli_command="vercel",
        available=shutil.which("vercel") is not None,
        config_file="vercel.json" if (root_path / "vercel.json").exists() else "",
        description="Vercel (serverless, static, Next.js)",
    ))

    # netlify
    targets.append(DeployTarget(
        name="netlify",
        cli_command="netlify",
        available=shutil.which("netlify") is not None,
        config_file="netlify.toml" if (root_path / "netlify.toml").exists() else "",
        description="Netlify (static sites, serverless functions)",
    ))

    # fly.io
    targets.append(DeployTarget(
        name="fly",
        cli_command="fly",
        available=shutil.which("fly") is not None or shutil.which("flyctl") is not None,
        config_file="fly.toml" if (root_path / "fly.toml").exists() else "",
        description="Fly.io (containers, full-stack apps)",
    ))

    # railway
    targets.append(DeployTarget(
        name="railway",
        cli_command="railway",
        available=shutil.which("railway") is not None,
        config_file="railway.json" if (root_path / "railway.json").exists() else "",
        description="Railway (full-stack, databases)",
    ))

    # cloudflare pages
    targets.append(DeployTarget(
        name="cloudflare",
        cli_command="wrangler",
        available=shutil.which("wrangler") is not None,
        config_file="wrangler.toml" if (root_path / "wrangler.toml").exists() else "",
        description="Cloudflare Pages/Workers",
    ))

    return targets


async def deploy(
    target: Optional[str] = None,
    root: Optional[str] = None,
    prod: bool = False,
    timeout: int = 120,
) -> DeployResult:
    """
    Deploy the project using the detected or specified target.

    Args:
        target: Deployment target name (vercel, netlify, fly, etc.).
                If None, auto-detects based on config files.
        root: Project root directory.
        prod: If True, deploy to production.
        timeout: Command timeout in seconds.
    """
    root_path = Path(root or ".").resolve()
    targets = detect_deploy_targets(str(root_path))

    if target:
        matched = [t for t in targets if t.name == target]
        if not matched:
            return DeployResult(target=target, success=False,
                                message=f"unknown deploy target: {target}")
        chosen = matched[0]
    else:
        # auto-detect: prefer targets with config files
        configured = [t for t in targets if t.config_file and t.available]
        available = [t for t in targets if t.available]
        chosen = (configured or available or [None])[0]
        if not chosen:
            return DeployResult(target="none", success=False,
                                message="no deployment CLI found. Install vercel, netlify, fly, railway, or wrangler.")

    if not chosen.available:
        return DeployResult(
            target=chosen.name, success=False,
            message=f"{chosen.cli_command} CLI not found. Install it first.",
        )

    cmd = _build_deploy_command(chosen, prod)
    logger.info("deploying via %s: %s", chosen.name, cmd)

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(root_path),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        success = proc.returncode == 0
        url = _extract_url(stdout_str + stderr_str)
        return DeployResult(
            target=chosen.name,
            success=success,
            url=url,
            message=f"deployed to {chosen.name}" if success else f"deploy failed (exit {proc.returncode})",
            stdout=stdout_str,
            stderr=stderr_str,
        )
    except asyncio.TimeoutError:
        return DeployResult(target=chosen.name, success=False,
                            message=f"deploy timed out after {timeout}s")
    except Exception as exc:
        return DeployResult(target=chosen.name, success=False, message=str(exc))


def _build_deploy_command(target: DeployTarget, prod: bool) -> str:
    if target.name == "vercel":
        return f"vercel {'--prod' if prod else ''} --yes"
    if target.name == "netlify":
        return f"netlify deploy {'--prod' if prod else ''}"
    if target.name == "fly":
        cli = "flyctl" if shutil.which("flyctl") else "fly"
        return f"{cli} deploy"
    if target.name == "railway":
        return "railway up"
    if target.name == "cloudflare":
        return "wrangler pages deploy"
    return f"{target.cli_command} deploy"


def _extract_url(output: str) -> str:
    """Extract deployment URL from CLI output."""
    import re
    patterns = [
        re.compile(r'https?://[^\s<>"\']+\.vercel\.app[^\s<>"\']*'),
        re.compile(r'https?://[^\s<>"\']+\.netlify\.app[^\s<>"\']*'),
        re.compile(r'https?://[^\s<>"\']+\.fly\.dev[^\s<>"\']*'),
        re.compile(r'https?://[^\s<>"\']+\.railway\.app[^\s<>"\']*'),
        re.compile(r'https?://[^\s<>"\']+\.pages\.dev[^\s<>"\']*'),
        re.compile(r'https?://[^\s<>"\']+\.workers\.dev[^\s<>"\']*'),
    ]
    for pattern in patterns:
        match = pattern.search(output)
        if match:
            return match.group(0)
    return ""
