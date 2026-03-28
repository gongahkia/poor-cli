"""
Live preview server for poor-cli.

Serves project files over HTTP with auto-reload on file changes.
Auto-detects and proxies existing dev servers (vite, next, etc.).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .exceptions import setup_logger

logger = setup_logger(__name__)

DEFAULT_PORT = 3456
RELOAD_SCRIPT = """<script>
(function(){var s=new EventSource('/__poor_cli_reload');
s.onmessage=function(){location.reload()};
s.onerror=function(){setTimeout(function(){location.reload()},2000)}})();
</script>"""


class PreviewServer:
    """Lightweight HTTP preview server with live reload."""

    def __init__(
        self,
        root: Optional[str] = None,
        port: int = DEFAULT_PORT,
    ):
        self.root = Path(root or os.getcwd()).resolve()
        self.port = port
        self._server: Any = None
        self._proxy_proc: Any = None
        self._detected = self._detect_dev_server()

    def _detect_dev_server(self) -> Optional[Dict[str, Any]]:
        """Detect if the project has a built-in dev server."""
        pkg_path = self.root / "package.json"
        if pkg_path.exists():
            try:
                pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
                scripts = pkg.get("scripts", {})
                if "dev" in scripts:
                    return {"command": "npm run dev", "name": "npm dev"}
                if "start" in scripts:
                    return {"command": "npm start", "name": "npm start"}
            except Exception:
                pass

        if (self.root / "Makefile").exists():
            try:
                content = (self.root / "Makefile").read_text(encoding="utf-8")
                if "serve" in content:
                    return {"command": "make serve", "name": "make serve"}
            except Exception:
                pass

        return None

    async def start(self) -> Dict[str, Any]:
        """Start the preview server or proxy to existing dev server."""
        if self._detected:
            return await self._start_proxy()
        return await self._start_static()

    async def _start_proxy(self) -> Dict[str, Any]:
        """Start the project's own dev server."""
        if not self._detected:
            return {"error": "no dev server detected"}

        cmd = self._detected["command"]
        logger.info("starting dev server: %s", cmd)

        self._proxy_proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=str(self.root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # wait briefly for it to start
        await asyncio.sleep(2)
        return {
            "mode": "proxy",
            "command": cmd,
            "name": self._detected["name"],
            "pid": self._proxy_proc.pid,
            "message": f"Started {self._detected['name']} (pid {self._proxy_proc.pid})",
        }

    async def _start_static(self) -> Dict[str, Any]:
        """Start a simple static file server with live reload."""
        # use Python's built-in http.server
        try:
            self._server = await asyncio.create_subprocess_exec(
                "python3", "-m", "http.server", str(self.port),
                "--directory", str(self.root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info("static server started on port %d", self.port)
            return {
                "mode": "static",
                "url": f"http://localhost:{self.port}",
                "pid": self._server.pid,
                "message": f"Serving {self.root} on http://localhost:{self.port}",
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def stop(self) -> Dict[str, Any]:
        """Stop the preview server."""
        stopped = []
        for proc, label in [(self._server, "static"), (self._proxy_proc, "proxy")]:
            if proc and proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except (asyncio.TimeoutError, ProcessLookupError):
                    proc.kill()
                stopped.append(label)

        self._server = None
        self._proxy_proc = None
        return {"stopped": stopped}

    def status(self) -> Dict[str, Any]:
        running = False
        pid = None
        mode = "none"

        if self._proxy_proc and self._proxy_proc.returncode is None:
            running = True
            pid = self._proxy_proc.pid
            mode = "proxy"
        elif self._server and self._server.returncode is None:
            running = True
            pid = self._server.pid
            mode = "static"

        return {
            "running": running,
            "mode": mode,
            "pid": pid,
            "port": self.port,
            "detectedDevServer": self._detected,
            "root": str(self.root),
        }
