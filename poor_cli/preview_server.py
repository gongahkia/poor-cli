"""
Live preview server for poor-cli.

Serves project files over HTTP with auto-reload on file changes.
Auto-detects and proxies existing dev servers (vite, next, etc.).
Uses a custom asyncio HTTP handler with SSE-based live reload.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set
from urllib.parse import unquote, urlparse

from .exceptions import setup_logger

logger = setup_logger(__name__)

DEFAULT_PORT = 3456
RELOAD_SCRIPT = """<script>
(function(){var s=new EventSource('/__poor_cli_reload');
s.onmessage=function(){location.reload()};
s.onerror=function(){setTimeout(function(){location.reload()},2000)}})();
</script>"""
WATCH_EXTENSIONS: Set[str] = {".html", ".css", ".js", ".htm", ".json", ".svg", ".ts", ".jsx", ".tsx"}
HTML_CONTENT_TYPES = {"text/html"}


class _ReloadState:
    """Shared reload state between file watcher and SSE clients."""
    def __init__(self):
        self._version: int = 0
        self._waiters: list[asyncio.Event] = []
    def bump(self):
        self._version += 1
        for w in self._waiters:
            w.set()
    @property
    def version(self) -> int:
        return self._version
    async def wait_for_change(self, known_version: int) -> int:
        if self._version > known_version:
            return self._version
        event = asyncio.Event()
        self._waiters.append(event)
        try:
            await event.wait()
        finally:
            self._waiters.remove(event)
        return self._version


class PreviewServer:
    """Lightweight HTTP preview server with SSE live reload."""

    def __init__(self, root: Optional[str] = None, port: int = DEFAULT_PORT):
        self.root = Path(root or os.getcwd()).resolve()
        self.port = port
        self._server: Any = None
        self._proxy_proc: Any = None
        self._detected = self._detect_dev_server()
        self._watch_task: Any = None
        self._reload_state = _ReloadState()

    def _detect_dev_server(self) -> Optional[Dict[str, Any]]:
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
        if self._detected:
            return await self._start_proxy()
        return await self._start_static()

    async def _start_proxy(self) -> Dict[str, Any]:
        if not self._detected:
            return {"error": "no dev server detected"}
        cmd = self._detected["command"]
        logger.info("starting dev server: %s", cmd)
        self._audit_log("preview_server:start", str(self.root), {"mode": "proxy", "command": cmd})
        self._proxy_proc = await asyncio.create_subprocess_shell(
            cmd, cwd=str(self.root),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(2)
        return {
            "mode": "proxy", "command": cmd,
            "name": self._detected["name"], "pid": self._proxy_proc.pid,
            "message": f"Started {self._detected['name']} (pid {self._proxy_proc.pid})",
        }

    async def _start_static(self) -> Dict[str, Any]:
        try:
            self._server = await asyncio.start_server(
                self._handle_connection, "127.0.0.1", self.port,
            )
            logger.info("static server started on port %d", self.port)
            self._audit_log("preview_server:start", str(self.root), {"mode": "static", "port": self.port})
            self._watch_task = asyncio.ensure_future(self._watch_files())
            return {
                "mode": "static",
                "url": f"http://localhost:{self.port}",
                "message": f"Serving {self.root} on http://localhost:{self.port}",
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a single HTTP connection."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            if not request_line:
                writer.close()
                return
            request_str = request_line.decode("utf-8", errors="replace").strip()
            parts = request_str.split()
            if len(parts) < 2:
                writer.close()
                return
            method, raw_path = parts[0], parts[1]
            # consume headers
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break
            path = unquote(urlparse(raw_path).path)
            if path == "/__poor_cli_reload":
                await self._handle_sse(writer)
                return
            if method.upper() != "GET":
                await self._send_response(writer, 405, "text/plain", b"Method Not Allowed")
                return
            await self._serve_file(writer, path)
        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as exc:
            logger.debug("connection handler error: %s", exc)
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_sse(self, writer: asyncio.StreamWriter):
        """Serve Server-Sent Events for live reload."""
        header = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n"
        )
        writer.write(header.encode())
        await writer.drain()
        known = self._reload_state.version
        try:
            while True:
                new_version = await asyncio.wait_for(
                    self._reload_state.wait_for_change(known), timeout=30,
                )
                known = new_version
                writer.write(f"data: reload {known}\n\n".encode())
                await writer.drain()
        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass # client disconnected or keepalive timeout

    async def _serve_file(self, writer: asyncio.StreamWriter, path: str):
        """Serve a static file, injecting reload script into HTML."""
        if path == "/":
            path = "/index.html"
        file_path = (self.root / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(self.root)):
            await self._send_response(writer, 403, "text/plain", b"Forbidden")
            return
        if not file_path.is_file():
            await self._send_response(writer, 404, "text/plain", b"Not Found")
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        content_type = content_type or "application/octet-stream"
        try:
            body = file_path.read_bytes()
        except OSError:
            await self._send_response(writer, 500, "text/plain", b"Read Error")
            return
        if content_type in HTML_CONTENT_TYPES: # inject reload script before </body>
            text = body.decode("utf-8", errors="replace")
            if "</body>" in text.lower():
                idx = text.lower().rfind("</body>")
                text = text[:idx] + RELOAD_SCRIPT + text[idx:]
            else:
                text += RELOAD_SCRIPT
            body = text.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        await self._send_response(writer, 200, content_type, body)

    @staticmethod
    async def _send_response(writer: asyncio.StreamWriter, status: int, content_type: str, body: bytes):
        status_text = {200: "OK", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 500: "Internal Server Error"}.get(status, "Unknown")
        header = (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(header.encode() + body)
        await writer.drain()
        writer.close()

    async def stop(self) -> Dict[str, Any]:
        stopped = []
        if self._server:
            self._server.close()
            stopped.append("static")
        for proc, label in [(self._proxy_proc, "proxy")]:
            if proc and proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except (asyncio.TimeoutError, ProcessLookupError):
                    proc.kill()
                stopped.append(label)
        self._server = None
        self._proxy_proc = None
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
        self._audit_log("preview_server:stop", details={"stopped": stopped})
        return {"stopped": stopped}

    def status(self) -> Dict[str, Any]:
        running = False
        mode = "none"
        if self._proxy_proc and self._proxy_proc.returncode is None:
            running = True
            mode = "proxy"
        elif self._server and self._server.is_serving():
            running = True
            mode = "static"
        return {
            "running": running, "mode": mode, "port": self.port,
            "detectedDevServer": self._detected, "root": str(self.root),
            "reloadVersion": self._reload_state.version,
        }

    async def health(self) -> Dict[str, Any]:
        s = self.status()
        return {"healthy": s["running"], **s}

    def _audit_log(self, operation: str, target: str = "", details: dict = None) -> None:
        try:
            from .audit_log import get_audit_logger, AuditEventType
            get_audit_logger().log_event(AuditEventType.TOOL_EXECUTION, operation=operation, target=target, details=details)
        except Exception:
            pass

    async def _watch_files(self) -> None:
        mtimes: Dict[str, float] = {}
        while True:
            changed = False
            try:
                for f in self.root.rglob("*"):
                    if f.is_file() and f.suffix in WATCH_EXTENSIONS:
                        try:
                            mt = f.stat().st_mtime
                            key = str(f)
                            if key not in mtimes or mtimes[key] < mt:
                                mtimes[key] = mt
                                changed = True
                        except OSError:
                            pass
            except Exception:
                pass
            if changed:
                self._reload_state.bump()
            await asyncio.sleep(1)
