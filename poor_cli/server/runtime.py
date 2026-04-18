"""
PoorCLI JSON-RPC Server runtime implementation.

This module contains JSON-RPC dispatch and stdio transport. Handler bodies
self-register from poor_cli.server.handlers.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
from functools import partial
from pathlib import Path
import signal
import uuid
from typing import Any, Callable, Dict, Optional, Set

from ..audit_log import AuditEventType, AuditSeverity, get_audit_logger
from ..config import ConfigManager
from ..core import PoorCLICore
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
from .registry import REGISTRY
from .transport import StdioTransport
from .types import InvalidParamsError, JsonRpcError, JsonRpcMessage

logger = setup_logger(__name__)


class PoorCLIServer(HandlerMixin):
    """JSON-RPC server for PoorCLI editor integrations."""

    def __init__(self):
        from ..session_manager import SessionManager

        self._session_manager = SessionManager()
        self._session_manager.create_session(label="default", make_default=True)
        self._session_manager.set_permission_callback(self._server_permission_callback)
        self.logger = setup_logger("poor_cli.server")
        self.session_id = f"server-{uuid.uuid4().hex[:8]}"
        set_log_context(session_id=self.session_id)
        self._running = False
        self._fast_shutdown_requested = False
        self._transport = StdioTransport()
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._background_tasks: Set[asyncio.Task[Any]] = set()
        self._init_handler_state()
        rate_limit_policy = self._load_initial_rate_limit_policy()
        self._rate_limiter = RateLimiter(rate_limit_policy)
        self._rate_limit_policy = self._copy_rate_limit_policy(rate_limit_policy)
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            method: partial(handler, self) for method, handler in REGISTRY.items()
        }

    @property
    def core(self) -> PoorCLICore:
        """backward-compat: returns the default session's core."""
        return self._session_manager.get_session().core

    @core.setter
    def core(self, value: PoorCLICore) -> None:
        """backward-compat setter — replaces core in default session."""
        session = self._session_manager.get_session()
        session.core = value

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
                await asyncio.wait_for(self.core.shutdown(), timeout=shutdown_timeout_s)
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
