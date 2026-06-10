"""JSON-RPC stdio client for the Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from typing import Any, BinaryIO, Dict, Optional


def frame_message(payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def read_framed_message(stream: BinaryIO) -> Dict[str, Any]:
    content_length: Optional[int] = None
    while True:
        line = stream.readline()
        if line == b"":
            raise EOFError("unexpected EOF while reading JSON-RPC header")
        if line in {b"\r\n", b"\n"}:
            break
        if line.lower().startswith(b"content-length:"):
            try:
                content_length = int(line.split(b":", 1)[1].strip())
            except ValueError as exc:
                raise ValueError("invalid Content-Length header") from exc
    if content_length is None or content_length <= 0:
        raise ValueError("missing Content-Length header")
    body = stream.read(content_length)
    if len(body) != content_length:
        raise EOFError("unexpected EOF while reading JSON-RPC body")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON-RPC payload must be an object")
    return payload


class JsonRpcError(RuntimeError):
    """Structured JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = int(code)
        self.message = str(message)
        self.data = data
        detail = self.message
        if data is not None:
            detail = f"{detail}\n{json.dumps(data, ensure_ascii=False, sort_keys=True)}"
        super().__init__(detail)


class BackendProcessError(RuntimeError):
    """Backend process failure."""


class StderrBuffer:
    def __init__(self, limit: int = 64 * 1024):
        self._limit = max(1024, int(limit))
        self._lock = threading.Lock()
        self._chunks = bytearray()

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._lock:
            self._chunks.extend(chunk)
            if len(self._chunks) > self._limit:
                del self._chunks[: len(self._chunks) - self._limit]

    def text(self) -> str:
        with self._lock:
            snapshot = bytes(self._chunks)
        return snapshot.decode("utf-8", errors="replace")

    def reset(self) -> None:
        with self._lock:
            self._chunks.clear()


@dataclass
class BackendConfiguration:
    repo_root: str
    python_executable: str
    provider: str = ""
    model: str = ""
    api_key: str = ""
    permission_mode: str = "default"
    sandbox_preset: str = "workspace-write"
    validate_api_key: bool = False

    @classmethod
    def detected(
        cls,
        *,
        repo_root: str = "",
        python_executable: str = "",
        provider: str = "",
        model: str = "",
        api_key: str = "",
        permission_mode: str = "default",
        sandbox_preset: str = "workspace-write",
        validate_api_key: bool = False,
    ) -> "BackendConfiguration":
        resolved_root = Path(repo_root).expanduser() if repo_root else _detect_repo_root()
        resolved_python = (
            Path(python_executable).expanduser().as_posix()
            if python_executable
            else _detect_python_executable(resolved_root)
        )
        return cls(
            repo_root=str(resolved_root),
            python_executable=resolved_python,
            provider=provider,
            model=model,
            api_key=api_key,
            permission_mode=permission_mode,
            sandbox_preset=sandbox_preset,
            validate_api_key=validate_api_key,
        )

    def launch_command(self) -> list[str]:
        return [self.python_executable, "-m", "poor_cli.server", "--stdio"]

    def initialize_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "clientCapabilities": {
                "terminalTUI": True,
                "streaming": True,
                "reviewFlows": {
                    "permissionRequests": True,
                    "planReview": True,
                },
            },
            "permissionMode": self.permission_mode,
            "sandboxPreset": self.sandbox_preset,
            "streaming": True,
            "validateApiKey": self.validate_api_key,
        }
        if self.provider.strip():
            params["provider"] = self.provider.strip()
        if self.model.strip():
            params["model"] = self.model.strip()
        if self.api_key:
            params["apiKey"] = self.api_key
        return params


def _detect_repo_root() -> Path:
    candidates = []
    explicit = os.environ.get("POOR_CLI_REPO", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    cwd = Path.cwd()
    candidates.extend([cwd, cwd.parent, cwd.parent.parent])
    source = Path(__file__).resolve()
    for _ in range(8):
        source = source.parent
        candidates.append(source)
    for candidate in candidates:
        if (candidate / "pyproject.toml").exists():
            return candidate.resolve()
    return cwd.resolve()


def _detect_python_executable(repo_root: Path) -> str:
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists() and os.access(venv_python, os.X_OK):
        return str(venv_python)
    return sys.executable


class BackendProcess:
    """Owns the server subprocess."""

    def __init__(self, configuration: BackendConfiguration):
        self._configuration = configuration
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._stderr_buffer = StderrBuffer()
        self._stderr_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def update_configuration(self, configuration: BackendConfiguration) -> None:
        with self._lock:
            changed = self._configuration != configuration
        if changed:
            self.stop()
        with self._lock:
            self._configuration = configuration

    @property
    def configuration(self) -> BackendConfiguration:
        with self._lock:
            return self._configuration

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self) -> bool:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return False
            configuration = self._configuration
        repo_root = Path(configuration.repo_root).expanduser()
        if not repo_root.exists():
            raise BackendProcessError(f"Repository root does not exist: {repo_root}")
        self._stderr_buffer.reset()
        try:
            process = subprocess.Popen(
                configuration.launch_command(),
                cwd=str(repo_root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise BackendProcessError(f"Failed to launch backend: {exc}") from exc
        with self._lock:
            self._process = process
        self._stderr_thread = threading.Thread(
            target=self._consume_stderr,
            name="poor-cli-tui-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        return True

    def _consume_stderr(self) -> None:
        stream = self.stderr
        if stream is None:
            return
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            self._stderr_buffer.append(chunk)

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def throw_if_exited(self) -> None:
        with self._lock:
            process = self._process
        if process is None:
            raise BackendProcessError("Backend process is not running.")
        returncode = process.poll()
        if returncode is not None:
            stderr = self._stderr_buffer.text()
            message = f"Backend exited with code {returncode}."
            if stderr:
                message = f"{message}\n{stderr}"
            raise BackendProcessError(message)

    @property
    def stdin(self) -> Optional[BinaryIO]:
        with self._lock:
            if self._process is None:
                return None
            return self._process.stdin

    @property
    def stdout(self) -> Optional[BinaryIO]:
        with self._lock:
            if self._process is None:
                return None
            return self._process.stdout

    @property
    def stderr(self) -> Optional[BinaryIO]:
        with self._lock:
            if self._process is None:
                return None
            return self._process.stderr

    @property
    def stderr_text(self) -> str:
        return self._stderr_buffer.text()


@dataclass
class _PendingResponse:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Optional[BaseException] = None

    def resolve(self, result: Any) -> None:
        self.result = result
        self.event.set()

    def reject(self, error: BaseException) -> None:
        self.error = error
        self.event.set()


class JsonRpcClient:
    """Threaded stdio JSON-RPC client."""

    def __init__(self, configuration: BackendConfiguration):
        self._backend = BackendProcess(configuration)
        self.notifications: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._next_id = 1
        self._pending: Dict[int, _PendingResponse] = {}
        self._state_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._reader_generation = 0
        self._closed_reason: Optional[BaseException] = None

    def update_configuration(self, configuration: BackendConfiguration) -> None:
        self._backend.update_configuration(configuration)

    def is_running(self) -> bool:
        return self._backend.is_running()

    def start(self) -> None:
        self._closed_reason = None
        started_new_process = self._backend.start()
        self._backend.throw_if_exited()
        with self._state_lock:
            needs_reader = (
                started_new_process
                or self._reader_thread is None
                or not self._reader_thread.is_alive()
            )
            if needs_reader:
                self._reader_generation += 1
                generation = self._reader_generation
                self._reader_thread = threading.Thread(
                    target=self._reader_loop,
                    args=(generation,),
                    name=f"poor-cli-tui-rpc-reader-{generation}",
                    daemon=True,
                )
                self._reader_thread.start()

    def close(self) -> None:
        self._backend.stop()
        self._fail_pending(BackendProcessError("Backend connection closed."))

    def initialize(self) -> Dict[str, Any]:
        return self.call("initialize", self._backend.configuration.initialize_params(), timeout=60.0)

    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        auto_start: bool = True,
        timeout: Optional[float] = None,
    ) -> Any:
        if auto_start:
            self.start()
        else:
            self._backend.throw_if_exited()
        request_id, pending = self._reserve_request()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        try:
            self._write_payload(request)
        except BaseException as exc:
            self._release_request(request_id)
            raise exc
        if not pending.event.wait(timeout):
            self._release_request(request_id)
            raise TimeoutError(f"Timed out waiting for JSON-RPC response: {method}")
        if pending.error is not None:
            raise pending.error
        return pending.result

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        self.start()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        self._write_payload(payload)

    def shutdown_if_running(self) -> None:
        if not self.is_running():
            self.close()
            return
        try:
            self.call("shutdown", {}, auto_start=False, timeout=3.0)
        except BaseException:
            pass
        self.close()

    def _reserve_request(self) -> tuple[int, _PendingResponse]:
        with self._state_lock:
            if self._closed_reason is not None:
                raise self._closed_reason
            request_id = self._next_id
            self._next_id += 1
            pending = _PendingResponse()
            self._pending[request_id] = pending
            return request_id, pending

    def _release_request(self, request_id: int) -> None:
        with self._state_lock:
            self._pending.pop(request_id, None)

    def _write_payload(self, payload: Dict[str, Any]) -> None:
        self._backend.throw_if_exited()
        stream = self._backend.stdin
        if stream is None:
            raise BackendProcessError("Backend stdin is unavailable.")
        encoded = frame_message(payload)
        with self._write_lock:
            stream.write(encoded)
            stream.flush()

    def _reader_loop(self, generation: int) -> None:
        stream = self._backend.stdout
        if stream is None:
            should_fail = False
            with self._state_lock:
                should_fail = generation == self._reader_generation
            if should_fail:
                self._fail_pending(BackendProcessError("Backend stdout is unavailable."))
            return
        try:
            while True:
                payload = read_framed_message(stream)
                self._dispatch_payload(payload)
        except BaseException as exc:
            reason: BaseException = exc
            if isinstance(exc, EOFError):
                stderr = self._backend.stderr_text.strip()
                message = "Backend connection closed."
                if stderr:
                    message = f"{message}\n{stderr}"
                reason = BackendProcessError(message)
            with self._state_lock:
                if generation != self._reader_generation:
                    return
                self._closed_reason = reason
            self._fail_pending(reason)

    def _dispatch_payload(self, payload: Dict[str, Any]) -> None:
        if "method" in payload and "id" not in payload:
            self.notifications.put(payload)
            return
        request_id = payload.get("id")
        if not isinstance(request_id, int):
            return
        with self._state_lock:
            pending = self._pending.pop(request_id, None)
        if pending is None:
            return
        if "error" in payload and isinstance(payload["error"], dict):
            error = payload["error"]
            pending.reject(
                JsonRpcError(
                    code=int(error.get("code", -32603)),
                    message=str(error.get("message", "JSON-RPC error")),
                    data=error.get("data"),
                )
            )
            return
        pending.resolve(payload.get("result"))

    def _fail_pending(self, error: BaseException) -> None:
        with self._state_lock:
            pending_items = list(self._pending.values())
            self._pending.clear()
        for pending in pending_items:
            pending.reject(error)
