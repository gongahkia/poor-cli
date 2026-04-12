# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *


class ServicesStateMixin:
    def _ensure_service_controls_available(self) -> None:
        """Disallow service lifecycle controls from nested multiplayer room engines."""
        if self._embedded_multiplayer_room:
            raise InvalidParamsError(
                "Service controls are unavailable inside multiplayer room sessions"
            )

    def _normalize_service_name(raw_name: Any) -> str:
        """Normalize and validate user-provided service names."""
        service_name = str(raw_name or "").strip().lower()
        if not service_name:
            raise InvalidParamsError("Missing service name")

        if not all(ch.isalnum() or ch in {"-", "_", "."} for ch in service_name):
            raise InvalidParamsError(
                "Service name must contain only letters, numbers, '-', '_' or '.'"
            )
        return service_name

    def _parse_service_command(raw_command: Any) -> List[str]:
        """Parse a command (string or argv list) into argv parts."""
        if raw_command is None:
            return []

        parts: List[str]
        if isinstance(raw_command, str):
            command_text = raw_command.strip()
            if not command_text:
                return []
            try:
                parts = shlex.split(command_text)
            except ValueError as error:
                raise InvalidParamsError(f"Invalid command syntax: {error}") from error
        elif isinstance(raw_command, list):
            parts = [str(item).strip() for item in raw_command if str(item).strip()]
        else:
            raise InvalidParamsError("command must be a string or a list of argv tokens")

        if not parts:
            raise InvalidParamsError("command cannot be empty")
        return parts

    def _service_default_command(service_name: str) -> Optional[List[str]]:
        """Return built-in command defaults for known local services."""
        if service_name == "ollama":
            return ["ollama", "serve"]
        return None

    def _render_command_display(command_parts: List[str]) -> str:
        """Render argv parts to a user-facing shell-safe display string."""
        return " ".join(shlex.quote(part) for part in command_parts)

    def _resolve_service_executable(
        command_name: str,
        service_name: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a command to an executable path, with service-specific fallbacks."""
        if not command_name:
            return None

        command_path = Path(command_name).expanduser()
        if "/" in command_name or command_path.is_absolute():
            if command_path.exists():
                return str(command_path)
            return None

        resolved = shutil.which(command_name)
        if resolved:
            return resolved

        # GUI-launched apps on macOS often lack Homebrew PATH entries.
        # Keep this narrowly scoped to Ollama so other services remain explicit.
        if (service_name or "").strip().lower() == "ollama" or command_name == "ollama":
            fallback_candidates: List[str] = []

            env_override = os.environ.get("OLLAMA_BIN") or os.environ.get("OLLAMA_PATH")
            if env_override:
                fallback_candidates.append(env_override)

            if sys.platform == "darwin":
                fallback_candidates.extend(
                    ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama"]
                )
            elif os.name == "nt":
                fallback_candidates.extend(
                    [
                        r"C:\\Program Files\\Ollama\\ollama.exe",
                        r"C:\\Program Files (x86)\\Ollama\\ollama.exe",
                    ]
                )
            else:
                fallback_candidates.extend(
                    ["/usr/local/bin/ollama", "/usr/bin/ollama", "/snap/bin/ollama"]
                )

            for candidate in fallback_candidates:
                candidate_path = Path(candidate).expanduser()
                if candidate_path.is_file() and os.access(candidate_path, os.X_OK):
                    return str(candidate_path)

        return None

    def _ollama_base_url(self) -> str:
        """Resolve configured Ollama base URL with a safe default."""
        default_base_url = "http://localhost:11434"
        if self.core.config is None:
            return default_base_url

        provider_cfg = self.core.config.model.providers.get("ollama")
        if provider_cfg is None:
            return default_base_url
        return str(provider_cfg.base_url or default_base_url).strip() or default_base_url

    def _is_tcp_endpoint_reachable(host: str, port: int, timeout_seconds: float = 0.8) -> bool:
        """Cheap TCP readiness check used for local service health probes."""
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds):
                return True
        except OSError:
            return False

    def _is_ollama_reachable(self, base_url: Optional[str] = None) -> bool:
        """Check whether the configured Ollama endpoint is accepting TCP connections."""
        target_url = (base_url or self._ollama_base_url()).strip()
        parsed = urlparse(target_url)
        host = parsed.hostname or "localhost"
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        return self._is_tcp_endpoint_reachable(host, port)

    def _list_ollama_models(self, base_url: Optional[str] = None) -> List[str]:
        """Fetch installed Ollama models from /api/tags."""
        target_url = (base_url or self._ollama_base_url()).rstrip("/")
        if not target_url:
            return []

        request = Request(f"{target_url}/api/tags", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception:
            return []

        models: List[str] = []
        for entry in payload.get("models", []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                models.append(name.strip())

        deduped: List[str] = []
        seen = set()
        for model in models:
            if model in seen:
                continue
            seen.add(model)
            deduped.append(model)
        return deduped

    async def _stop_managed_service_locked(
        self,
        service: ManagedServiceRuntime,
        timeout_seconds: float = 5.0,
    ) -> bool:
        """Stop a managed service process and close log handles (lock must be held)."""
        was_running = service.process.returncode is None

        if was_running:
            self._signal_managed_service_process(service, signal.SIGTERM)
            try:
                await asyncio.wait_for(service.process.wait(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                self._signal_managed_service_process(service, signal.SIGKILL)
                with contextlib.suppress(Exception):
                    await service.process.wait()

        if service.process.returncode is not None:
            service.last_exit_code = service.process.returncode

        if getattr(service, "log_handle", None) is not None:
            with contextlib.suppress(Exception):
                service.log_handle.flush()
                service.log_handle.close()
            service.log_handle = None

        return was_running

    async def _shutdown_managed_services_locked(self) -> None:
        """Stop every managed service (lock must be held)."""
        for service in self._managed_services.values():
            with contextlib.suppress(Exception):
                await self._stop_managed_service_locked(service)
        self._managed_services.clear()

    def _refresh_managed_service_locked(
        self,
        service_name: str,
    ) -> Optional[ManagedServiceRuntime]:
        """Sync cached service runtime state with the underlying process."""
        service = self._managed_services.get(service_name)
        if service is None:
            return None
        if service.process.returncode is None:
            return service

        service.last_exit_code = service.process.returncode
        if getattr(service, "log_handle", None) is not None:
            with contextlib.suppress(Exception):
                service.log_handle.flush()
                service.log_handle.close()
            service.log_handle = None
        return service

    def _service_payload_locked(
        self,
        service_name: str,
        *,
        created: bool = False,
        stopped: bool = False,
        message: str = "",
    ) -> Dict[str, Any]:
        """Build stable status payload for a managed/external service."""
        managed = self._refresh_managed_service_locked(service_name)
        managed_running = False

        payload: Dict[str, Any] = {
            "service": service_name,
            "running": False,
            "managed": managed is not None,
            "managedRunning": False,
            "external": False,
            "created": created,
            "stopped": stopped,
            "message": message,
        }

        default_command = self._service_default_command(service_name)
        command_for_availability = (
            managed.command if managed is not None else (default_command or [])
        )
        executable_path = (
            self._resolve_service_executable(
                command_for_availability[0],
                service_name=service_name,
            )
            if command_for_availability
            else None
        )
        payload["available"] = executable_path is not None
        if executable_path is not None:
            payload["executable"] = executable_path

        if managed is not None:
            managed_running = managed.process.returncode is None
            if managed.process.returncode is not None and managed.last_exit_code is None:
                managed.last_exit_code = managed.process.returncode

            payload.update(
                {
                    "managedRunning": managed_running,
                    "running": managed_running,
                    "pid": managed.process.pid if managed_running else None,
                    "command": managed.command_display,
                    "cwd": managed.cwd,
                    "logPath": str(managed.log_path),
                    "startedAt": managed.started_at,
                    "exitCode": managed.last_exit_code,
                }
            )
        elif default_command is not None:
            payload["command"] = self._render_command_display(default_command)
            payload["logPath"] = str(self._service_logs_dir / f"{service_name}.log")

        if service_name == "ollama":
            base_url = self._ollama_base_url()
            healthy = self._is_ollama_reachable(base_url)
            external = healthy and not managed_running
            payload["baseUrl"] = base_url
            payload["healthy"] = healthy
            payload["external"] = external
            payload["running"] = managed_running or external

        return payload

    def _tail_log_file(log_path: Path, line_count: int) -> str:
        """Read the last N lines from a text log file."""
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            tail = deque(handle, maxlen=max(line_count, 1))
        return "".join(tail).strip()

    def _service_log_rotation_threshold_bytes() -> int:
        """Maximum managed service log size before rotating on next launch."""
        return 5 * 1024 * 1024

    def _rotate_service_log_if_needed(self, log_path: Path) -> None:
        threshold_bytes = int(self._service_log_rotation_threshold_bytes())
        if threshold_bytes <= 0 or not log_path.exists():
            return

        with contextlib.suppress(OSError):
            if log_path.stat().st_size < threshold_bytes:
                return

        rotated_path = log_path.with_name(f"{log_path.name}.1")
        with contextlib.suppress(OSError):
            rotated_path.unlink()
        with contextlib.suppress(OSError):
            log_path.replace(rotated_path)

    def _normalize_service_cwd(self, cwd_path: Path, raw_cwd: str) -> str:
        resolved = cwd_path.resolve()
        if not resolved.is_dir():
            raise InvalidParamsError(f"cwd is not a directory: {raw_cwd}")
        if self._trusted_workspace_enabled() and not self._path_is_trusted(str(resolved)):
            raise InvalidParamsError(
                f"cwd falls outside trusted workspace roots: {resolved}"
            )
        return str(resolved)

    def _signal_managed_service_process(service: ManagedServiceRuntime, sig: int) -> bool:
        process = service.process
        pid = getattr(process, "pid", None)

        if pid is not None and int(pid) > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(int(pid), sig)
                return True
            except PermissionError:
                return True
            except OSError:
                pass

        try:
            if sig == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        except ProcessLookupError:
            return False
        return True

    async def handle_start_service(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start a managed local background service.

        Params:
            name: Service identifier (e.g. ollama)
            command: Optional command string or argv array
            cwd: Optional working directory
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        service_name = self._normalize_service_name(params.get("name"))
        command_parts = self._parse_service_command(params.get("command"))
        cwd_value: Optional[str] = None

        raw_cwd = params.get("cwd")
        if raw_cwd not in (None, ""):
            cwd_path = self._resolve_path(str(raw_cwd))
            cwd_value = self._normalize_service_cwd(cwd_path, str(raw_cwd))

        async with self._get_service_lock():
            existing = self._refresh_managed_service_locked(service_name)
            if existing is not None and existing.process.returncode is None:
                return self._service_payload_locked(
                    service_name,
                    created=False,
                    stopped=False,
                    message="Service is already running.",
                )

            if not command_parts:
                if existing is not None and existing.command:
                    command_parts = list(existing.command)
                else:
                    default_command = self._service_default_command(service_name)
                    if default_command is not None:
                        command_parts = list(default_command)

            if not command_parts:
                raise InvalidParamsError(
                    "Missing command. Usage: /service start <name> <command...>"
                )

            if cwd_value is None and existing is not None and existing.cwd:
                cwd_value = self._normalize_service_cwd(Path(existing.cwd), existing.cwd)

            executable_path = self._resolve_service_executable(
                command_parts[0],
                service_name=service_name,
            )
            if executable_path is None:
                raise InvalidParamsError(
                    f"Command not found for service '{service_name}': {command_parts[0]}"
                )
            command_parts[0] = executable_path

            if (
                service_name == "ollama"
                and self._is_ollama_reachable()
                and (existing is None or existing.process.returncode is not None)
            ):
                return self._service_payload_locked(
                    service_name,
                    created=False,
                    stopped=False,
                    message="Ollama is already running (external to poor-cli).",
                )

            self._service_logs_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._service_logs_dir / f"{service_name}.log"
            self._rotate_service_log_if_needed(log_path)

            if existing is not None and getattr(existing, "log_handle", None) is not None:
                with contextlib.suppress(Exception):
                    existing.log_handle.flush()
                    existing.log_handle.close()

            log_handle = open(log_path, "ab")
            try:
                spawn_kwargs = {
                    "stdout": log_handle,
                    "stderr": asyncio.subprocess.STDOUT,
                    "cwd": cwd_value,
                }
                if hasattr(os, "killpg"):
                    spawn_kwargs["start_new_session"] = True
                process = await asyncio.create_subprocess_exec(
                    *command_parts,
                    **spawn_kwargs,
                )
            except Exception:
                with contextlib.suppress(Exception):
                    log_handle.close()
                raise

            runtime = ManagedServiceRuntime(
                name=service_name,
                command=list(command_parts),
                command_display=self._render_command_display(command_parts),
                cwd=cwd_value,
                process=process,
                log_path=log_path,
                log_handle=log_handle,
                started_at=datetime.now().isoformat(),
            )
            self._managed_services[service_name] = runtime

            # Catch immediate launch failures and surface actionable output.
            await asyncio.sleep(0.15)
            if process.returncode is not None:
                runtime.last_exit_code = process.returncode
                await self._stop_managed_service_locked(runtime, timeout_seconds=0.1)
                raise PoorCLIError(
                    f"Service '{service_name}' exited immediately with code "
                    f"{runtime.last_exit_code}. Check logs: {log_path}"
                )

            message = "Service started."
            if service_name == "ollama":
                # Ollama can take a few seconds before port 11434 accepts requests.
                # Wait briefly so `/ollama start` is reliably usable right away.
                warmed_up = False
                for _ in range(40):  # ~8 seconds
                    if self._is_ollama_reachable():
                        warmed_up = True
                        break
                    if process.returncode is not None:
                        runtime.last_exit_code = process.returncode
                        await self._stop_managed_service_locked(runtime, timeout_seconds=0.1)
                        raise PoorCLIError(
                            f"Service '{service_name}' exited during startup with code "
                            f"{runtime.last_exit_code}. Check logs: {log_path}"
                        )
                    await asyncio.sleep(0.2)
                if not warmed_up:
                    message = (
                        "Service started, but Ollama is still warming up. "
                        "Run `/ollama status` and retry shortly."
                    )

            return self._service_payload_locked(
                service_name,
                created=True,
                stopped=False,
                message=message,
            )

    async def handle_stop_service(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stop a managed local background service.

        Params:
            name: Service identifier
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        service_name = self._normalize_service_name(params.get("name"))

        async with self._get_service_lock():
            service = self._managed_services.get(service_name)
            if service is None:
                payload = self._service_payload_locked(
                    service_name,
                    created=False,
                    stopped=False,
                    message="Service is not managed by poor-cli.",
                )
                if service_name == "ollama" and payload.get("external"):
                    payload["message"] = (
                        "Ollama is running externally and cannot be stopped by poor-cli."
                    )
                return payload

            was_running = await self._stop_managed_service_locked(service)
            return self._service_payload_locked(
                service_name,
                created=False,
                stopped=was_running,
                message="Service stopped." if was_running else "Service was already stopped.",
            )

    async def handle_get_service_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get service status for one service or all known services.

        Params:
            name: Optional service identifier filter
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        requested_name = str(params.get("name", "")).strip()
        async with self._get_service_lock():
            if requested_name:
                service_name = self._normalize_service_name(requested_name)
                return self._service_payload_locked(service_name)

            names = set(self._managed_services.keys())
            names.add("ollama")
            return {
                "services": [
                    self._service_payload_locked(service_name)
                    for service_name in sorted(names)
                ]
            }

    async def handle_get_service_logs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return tail logs for a managed local service.

        Params:
            name: Service identifier
            lines: Optional number of tail lines (default 80, max 500)
        """
        self._ensure_initialized()
        self._ensure_service_controls_available()

        service_name = self._normalize_service_name(params.get("name"))
        raw_lines = params.get("lines", 80)
        try:
            line_count = int(raw_lines)
        except (TypeError, ValueError) as error:
            raise InvalidParamsError("lines must be an integer") from error
        line_count = max(1, min(line_count, 500))

        async with self._get_service_lock():
            payload = self._service_payload_locked(service_name)
            service = self._managed_services.get(service_name)
            if service is not None:
                log_path = service.log_path
            elif service_name == "ollama":
                log_path = self._service_logs_dir / "ollama.log"
            else:
                raise InvalidParamsError(f"Unknown service: {service_name}")

        exists = log_path.is_file()
        content = ""
        if exists:
            content = self._tail_log_file(log_path, line_count)

        return {
            "service": service_name,
            "lines": line_count,
            "logPath": str(log_path),
            "exists": exists,
            "content": content,
            "status": payload,
        }
