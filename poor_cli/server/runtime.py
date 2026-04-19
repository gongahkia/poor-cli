"""
PoorCLI JSON-RPC Server runtime implementation.

This module contains JSON-RPC dispatch and stdio transport. Handler bodies
self-register from poor_cli.server.handlers.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import os
from pathlib import Path
import signal
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

from ..config import ConfigManager
from ..exceptions import (
    PermissionDeniedError,
    PoorCLIError,
    get_error_code,
    log_context,
    set_log_context,
    setup_logger,
)
from .error_formatter import _sanitize_exception_message
from .handlers import HandlerMixin
from .rate_limit import DEFAULT_RPC_RATE_LIMITS, RateLimitExceeded, RateLimiter
from .registry import REGISTRY, ensure_handler_for_method
from .transport import StdioTransport
from .types import InvalidParamsError, JsonRpcError, JsonRpcMessage

if TYPE_CHECKING:
    from ..core import PoorCLICore

logger = setup_logger(__name__)
_PERF_LOG = os.environ.get("POORCLI_SERVER_PERF_LOG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def get_audit_logger():
    from ..audit_log import get_audit_logger as _get_audit_logger

    return _get_audit_logger()


class PoorCLIServer(HandlerMixin):
    """JSON-RPC server for PoorCLI editor integrations."""

    def __init__(self):
        init_started = time.perf_counter()
        from ..session_manager import SessionManager

        self.logger = setup_logger("poor_cli.server")
        self._perf_log_enabled = _PERF_LOG

        phase_started = time.perf_counter()
        self._session_manager = SessionManager()
        self._session_manager.set_permission_callback(self._server_permission_callback)
        self._default_session_lock = threading.Lock()
        if self._perf_log_enabled:
            self.logger.info(
                "perf server_init.session_manager_ms=%.2f",
                (time.perf_counter() - phase_started) * 1000.0,
            )

        self.session_id = f"server-{uuid.uuid4().hex[:8]}"
        set_log_context(session_id=self.session_id)
        self._running = False
        self._fast_shutdown_requested = False
        self._transport = StdioTransport()
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._background_tasks: Set[asyncio.Task[Any]] = set()

        phase_started = time.perf_counter()
        self._init_handler_state()
        if self._perf_log_enabled:
            self.logger.info(
                "perf server_init.handler_state_ms=%.2f",
                (time.perf_counter() - phase_started) * 1000.0,
            )

        phase_started = time.perf_counter()
        rate_limit_policy = self._load_initial_rate_limit_policy()
        self._rate_limiter = RateLimiter(rate_limit_policy)
        self._rate_limit_policy = self._copy_rate_limit_policy(rate_limit_policy)
        if self._perf_log_enabled:
            self.logger.info(
                "perf server_init.rate_limit_ms=%.2f",
                (time.perf_counter() - phase_started) * 1000.0,
            )
            self.logger.info(
                "perf server_init.total_ms=%.2f",
                (time.perf_counter() - init_started) * 1000.0,
            )

    @property
    def core(self) -> PoorCLICore:
        """backward-compat: returns the default session's core."""
        self._ensure_default_session()
        return self._session_manager.get_session().core

    @core.setter
    def core(self, value: PoorCLICore) -> None:
        """backward-compat setter — replaces core in default session."""
        self._ensure_default_session()
        session = self._session_manager.get_session()
        session.core = value

    def _ensure_default_session(self) -> None:
        manager = getattr(self, "_session_manager", None)
        if manager is None:
            return
        if not hasattr(manager, "default_session") or not hasattr(manager, "create_session"):
            return
        if manager.default_session is not None:
            return
        lock = getattr(self, "_default_session_lock", None)
        if lock is None:
            return
        with lock:
            if manager.default_session is not None:
                return
            started = time.perf_counter()
            manager.create_session(label="default", make_default=True)
            if getattr(self, "_perf_log_enabled", False):
                self.logger.info(
                    "perf server_init.default_session_ms=%.2f",
                    (time.perf_counter() - started) * 1000.0,
                )

    async def dispatch(self, message: JsonRpcMessage) -> JsonRpcMessage:
        """Dispatch a JSON-RPC message to a registered handler."""
        with log_context(request_id=message.id):
            if not message.method:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.INVALID_REQUEST,
                        "Missing method",
                        {"error_code": "INVALID_REQUEST"},
                    ),
                )

            try:
                self._sync_rate_limiter()
                self._rate_limiter.require(message.method)
            except RateLimitExceeded as e:
                self._audit_rate_limit_exceeded(message, e.retry_after_s)
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.RATE_LIMITED,
                        "rate limited",
                        {
                            "method": message.method,
                            "retry_after_s": e.retry_after_s,
                            "error_code": "RATE_LIMITED",
                        },
                    ),
                )

            load_started = time.perf_counter()
            loaded = ensure_handler_for_method(message.method)
            if loaded and self._perf_log_enabled:
                self.logger.info(
                    "perf dispatch.handler_lazy_load method=%s elapsed_ms=%.2f",
                    message.method,
                    (time.perf_counter() - load_started) * 1000.0,
                )

            handler = REGISTRY.get(message.method)
            if not handler:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.METHOD_NOT_FOUND,
                        f"Unknown method: {message.method}",
                        {"error_code": "METHOD_NOT_FOUND"},
                    ),
                )

            try:
                result = await handler(self, message.params or {})
                return JsonRpcMessage(id=message.id, result=result)
            except InvalidParamsError as e:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.INVALID_PARAMS,
                        _sanitize_exception_message(e),
                        {"error_code": "INVALID_PARAMS"},
                    ),
                )
            except PermissionDeniedError as e:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        JsonRpcError.INTERNAL_ERROR,
                        _sanitize_exception_message(e),
                        {
                            "error_code": e.error_code,
                            "tool": e.tool_name,
                            "permission_mode": e.permission_mode,
                        },
                    ),
                )
            except PoorCLIError as e:
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        int(getattr(e, "RPC_CODE", JsonRpcError.INTERNAL_ERROR)),
                        _sanitize_exception_message(e),
                        {"error_code": e.error_code},
                    ),
                )
            except Exception as e:
                error_code = get_error_code(e)
                self.logger.exception(f"Handler error for {message.method}")
                return JsonRpcMessage(
                    id=message.id,
                    error=JsonRpcError.make_error(
                        int(getattr(e, "RPC_CODE", JsonRpcError.INTERNAL_ERROR)),
                        _sanitize_exception_message(e),
                        {"error_code": error_code},
                    ),
                )

    def _maybe_core(self) -> Optional[PoorCLICore]:
        session_manager = getattr(self, "_session_manager", None)
        if session_manager is None:
            return None
        try:
            return session_manager.get_session().core
        except Exception:
            return None

    def _load_initial_rate_limit_policy(self) -> Dict[str, Dict[str, Any]]:
        core = self._maybe_core()
        config_path = getattr(core, "_config_path", None) if core is not None else None
        try:
            return ConfigManager(config_path).load().rpc_rate_limits
        except Exception as e:
            self.logger.warning("Failed to load rpc_rate_limits; using defaults: %s", e)
            return self._copy_rate_limit_policy(DEFAULT_RPC_RATE_LIMITS)

    def _current_rate_limit_policy(self) -> Dict[str, Dict[str, Any]]:
        core = self._maybe_core()
        config = getattr(core, "config", None) if core is not None else None
        if config is not None:
            return getattr(config, "rpc_rate_limits", DEFAULT_RPC_RATE_LIMITS)
        return getattr(self, "_rate_limit_policy", self._copy_rate_limit_policy(DEFAULT_RPC_RATE_LIMITS))

    def _sync_rate_limiter(self) -> None:
        policy = self._current_rate_limit_policy()
        if not hasattr(self, "_rate_limiter"):
            self._rate_limiter = RateLimiter(policy)
            self._rate_limit_policy = self._copy_rate_limit_policy(policy)
            return
        if policy != getattr(self, "_rate_limit_policy", None):
            self._rate_limiter.configure(policy)
            self._rate_limit_policy = self._copy_rate_limit_policy(policy)

    @staticmethod
    def _copy_rate_limit_policy(policy: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(policy)

    def _audit_rate_limit_exceeded(
        self,
        message: JsonRpcMessage,
        retry_after_s: float,
    ) -> None:
        from ..audit_log import AuditEventType, AuditSeverity

        params = message.params if isinstance(message.params, dict) else {}
        client_id = (
            params.get("clientId")
            or params.get("client_id")
            or getattr(self, "session_id", "unknown")
        )
        try:
            core = self._maybe_core()
            audit_logger = getattr(core, "_audit_logger", None) if core is not None else None
            if audit_logger is None:
                audit_logger = get_audit_logger()
            audit_logger.log_event(
                event_type=AuditEventType.RPC_RATE_LIMIT_EXCEEDED,
                operation="rpc.rate_limit.exceeded",
                target=message.method,
                details={
                    "method": message.method,
                    "client_id": client_id,
                    "request_id": message.id,
                    "retry_after_s": retry_after_s,
                },
                severity=AuditSeverity.WARNING,
                success=False,
                error_message="rate limited",
            )
        except Exception as e:
            self.logger.debug("Audit logging failed for RPC rate limit: %s", e)

    async def read_message_stdio(self) -> Optional[JsonRpcMessage]:
        return await self._transport.read_message()

    async def write_message_stdio(self, message: JsonRpcMessage) -> None:
        await self._transport.write_message(message)

    async def _dispatch_and_respond(self, message: JsonRpcMessage) -> None:
        try:
            response = await self.dispatch(message)
            await self.write_message_stdio(response)
        except Exception as e:
            self.logger.exception(f"Error in background dispatch for {message.method}")
            error_code = get_error_code(e)
            error_response = JsonRpcMessage(
                id=message.id,
                error=JsonRpcError.make_error(
                    JsonRpcError.INTERNAL_ERROR,
                    _sanitize_exception_message(e),
                    {"error_code": error_code},
                ),
            )
            await self.write_message_stdio(error_response)

    async def _audit_rotation_loop(self, interval_seconds: float = 3600.0) -> None:
        while self._running:
            await asyncio.sleep(interval_seconds)
            try:
                audit_logger = getattr(self.core, "_audit_logger", None)
                if audit_logger is None:
                    from ..audit_log import AuditLogger

                    audit_logger = AuditLogger(audit_dir=Path.cwd() / ".poor-cli")
                await asyncio.to_thread(audit_logger.rotate_if_needed)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Scheduled audit rotation failed")

    async def run_stdio(self) -> None:
        self.logger.info("Starting stdio server")
        self._running = True
        self._fast_shutdown_requested = False

        loop = asyncio.get_running_loop()
        def _request_shutdown() -> None:
            self._fast_shutdown_requested = True
            self._running = False
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, _request_shutdown)

        try:
            self._track_background_task(asyncio.create_task(self._audit_rotation_loop()))
            while self._running:
                try:
                    message = await self.read_message_stdio()
                    if message is None:
                        if self._running:
                            self.logger.warning("No message received from transport")
                        else:
                            self.logger.info("EOF received, shutting down")
                        break

                    if message.method and message.id is None:
                        await self._handle_notification(message)
                        continue

                    if message.method == "poor-cli/chatStreaming":
                        task = asyncio.create_task(self._dispatch_and_respond(message))
                        self._track_background_task(task)
                        continue

                    response = await self.dispatch(message)
                    await self.write_message_stdio(response)
                except KeyboardInterrupt:
                    self.logger.info("Keyboard interrupt received")
                    break
                except Exception:
                    self.logger.exception("Error in main loop")
                    continue
        finally:
            self._running = False
            await self._shutdown_background_tasks()
            async with self._get_service_lock():
                with contextlib.suppress(Exception):
                    await self._shutdown_managed_services_locked()
            shutdown_timeout_s = 0.35 if self._fast_shutdown_requested else 6.0
            try:
                shutdown_coro = self.core.shutdown(fast=self._fast_shutdown_requested)
            except TypeError:
                shutdown_coro = self.core.shutdown()
            try:
                await asyncio.wait_for(
                    shutdown_coro,
                    timeout=shutdown_timeout_s,
                )
            except asyncio.TimeoutError:
                self.logger.warning(
                    "Core shutdown exceeded %.2fs during server stop; forcing fast exit",
                    shutdown_timeout_s,
                )
            except Exception:
                self.logger.debug("Core shutdown failed during server stop", exc_info=True)
            self.logger.info("Stdio server stopped")


class StreamingJsonRpcServer(PoorCLIServer):
    """Backward-compatible streaming server alias."""

    async def handle_chat_streaming_legacy(self, params: Dict[str, Any], request_id: int) -> None:
        self._ensure_initialized()

        message = params.get("message", "")
        context_files = params.get("contextFiles")
        pinned_context_files = params.get("pinnedContextFiles")
        context_files, pinned_context_files = self._context_apply_pins_and_drops(
            context_files or (),
            pinned_context_files or (),
        )
        context_budget_tokens = params.get("contextBudgetTokens")

        async for chunk in self.core.send_message(
            message=message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        ):
            notification = JsonRpcMessage(
                method="poor-cli/streamChunk",
                params={"requestId": request_id, "chunk": chunk, "done": False},
            )
            await self.write_message_stdio(notification)

        final = JsonRpcMessage(
            method="poor-cli/streamChunk",
            params={"requestId": request_id, "chunk": "", "done": True},
        )
        await self.write_message_stdio(final)
