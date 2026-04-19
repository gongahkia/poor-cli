# ruff: noqa: F403,F405
from __future__ import annotations

import asyncio
import copy
import time
from pathlib import Path
from typing import Any, Dict, List

from ...sandbox import PRESET_DESCRIPTION
from poor_cli.server.registry import register


class StatusHandlersMixin:
    def _status_view_payload(self) -> Dict[str, Any]:
        ttl_ms = float(getattr(self, "_status_view_cache_ttl_ms", 0.0) or 0.0)
        now = time.monotonic()
        cached = getattr(self, "_status_view_cache_payload", None)
        cached_at = float(getattr(self, "_status_view_cache_at", 0.0) or 0.0)
        if isinstance(cached, dict) and ttl_ms > 0 and (now - cached_at) * 1000.0 <= ttl_ms:
            return copy.deepcopy(cached)
        payload = self.core.build_status_view()
        self._status_view_cache_payload = copy.deepcopy(payload)
        self._status_view_cache_at = now
        return payload

    async def _refresh_status_view_cache(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        payload = await loop.run_in_executor(None, self.core.build_status_view)
        self._status_view_cache_payload = copy.deepcopy(payload)
        self._status_view_cache_at = time.monotonic()
        return payload

    def _ensure_status_view_refresh_lock(self) -> asyncio.Lock:
        lock = getattr(self, "_status_view_refresh_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._status_view_refresh_lock = lock
        return lock

    def _spawn_status_view_refresh(self) -> asyncio.Task[Any]:
        task = asyncio.create_task(self._refresh_status_view_cache())
        self._status_view_refresh_task = self._track_background_task(task)

        def _clear_refresh(done_task: asyncio.Task[Any]) -> None:
            if getattr(self, "_status_view_refresh_task", None) is done_task:
                self._status_view_refresh_task = None

        task.add_done_callback(_clear_refresh)
        return task

    async def _status_view_payload_async(self, *, allow_stale: bool = True) -> Dict[str, Any]:
        ttl_ms = float(getattr(self, "_status_view_cache_ttl_ms", 0.0) or 0.0)
        now = time.monotonic()
        cached = getattr(self, "_status_view_cache_payload", None)
        cached_at = float(getattr(self, "_status_view_cache_at", 0.0) or 0.0)
        if isinstance(cached, dict) and ttl_ms > 0 and (now - cached_at) * 1000.0 <= ttl_ms:
            return copy.deepcopy(cached)

        inflight = getattr(self, "_status_view_refresh_task", None)
        if inflight is not None and inflight.done():
            self._status_view_refresh_task = None
            inflight = None

        if isinstance(cached, dict) and allow_stale:
            if inflight is None:
                self._spawn_status_view_refresh()
            return copy.deepcopy(cached)

        lock = self._ensure_status_view_refresh_lock()
        async with lock:
            now = time.monotonic()
            cached = getattr(self, "_status_view_cache_payload", None)
            cached_at = float(getattr(self, "_status_view_cache_at", 0.0) or 0.0)
            if isinstance(cached, dict) and ttl_ms > 0 and (now - cached_at) * 1000.0 <= ttl_ms:
                return copy.deepcopy(cached)
            inflight = getattr(self, "_status_view_refresh_task", None)
            if inflight is None or inflight.done():
                inflight = self._spawn_status_view_refresh()

        try:
            payload = await inflight
            return copy.deepcopy(payload)
        except Exception:
            cached = getattr(self, "_status_view_cache_payload", None)
            if isinstance(cached, dict):
                return copy.deepcopy(cached)
            raise

    def _doctor_report_payload(self) -> Dict[str, Any]:
        payload = self.core.build_doctor_report()
        payload["statusView"] = self._status_view_payload()
        return payload

    async def handle_get_instruction_stack(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the active instruction stack for the given referenced files."""
        self._ensure_initialized()
        referenced_files = params.get("referencedFiles") or params.get("files")
        if not isinstance(referenced_files, list):
            referenced_files = []
        return self.core.inspect_instruction_stack([str(path) for path in referenced_files])

    async def handle_get_policy_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return repo-local policy hook and audit status."""
        del params
        self._ensure_initialized()
        return self.core.get_policy_status()

    def _permission_rule_summary(self) -> Dict[str, Any]:
        rules = self._permission_rules.list_rules()
        counts = {"allow": 0, "deny": 0, "prompt": 0, "total": 0}
        for scoped in rules.values():
            if not isinstance(scoped, list):
                continue
            for rule in scoped:
                if not isinstance(rule, dict):
                    continue
                behavior = str(rule.get("behavior", "ask")).strip().lower()
                if behavior == "ask":
                    behavior = "prompt"
                if behavior not in counts:
                    behavior = "prompt"
                counts[behavior] += 1
                counts["total"] += 1
        return {"rules": rules, "counts": counts}

    def _policy_rule_rows(self) -> List[Dict[str, Any]]:
        summary = self._permission_rule_summary()
        rows: List[Dict[str, Any]] = []
        for scope, scoped in summary["rules"].items():
            if not isinstance(scoped, list):
                continue
            for rule in scoped:
                if not isinstance(rule, dict):
                    continue
                outcome = str(rule.get("behavior", "ask")).strip().lower()
                if outcome == "ask":
                    outcome = "prompt"
                if outcome not in {"allow", "deny", "prompt"}:
                    outcome = "prompt"
                rows.append({
                    "index": len(rows) + 1,
                    "name": str(rule.get("toolName") or rule.get("name") or "*"),
                    "scope": str(scope),
                    "outcome": outcome,
                    "source": str(rule.get("source") or scope),
                    "file": str(rule.get("file") or ""),
                    "line": int(rule.get("line") or 0),
                    "ruleContent": str(rule.get("ruleContent") or ""),
                })
        return rows

    async def handle_policy_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return effective permission rules for read-only policy UIs."""
        del params
        self._ensure_initialized()
        return {"rules": self._policy_rule_rows()}

    async def handle_policy_reload(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Re-read file-backed permission rules and return the effective list."""
        return await self.handle_policy_list(params)

    async def handle_policy_edit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve a policy row to its source location without mutating it."""
        self._ensure_initialized()
        try:
            index = int(params.get("index") or 0)
        except (TypeError, ValueError):
            index = 0
        if index > 0:
            rows = self._policy_rule_rows()
            if index <= len(rows):
                row = rows[index - 1]
                return {"file": row.get("file", ""), "line": row.get("line", 0)}
        rule = params.get("rule") if isinstance(params.get("rule"), dict) else params
        return {"file": str(rule.get("file") or ""), "line": int(rule.get("line") or 0)}

    def _audit_row_count(self) -> int:
        logger = getattr(self.core, "_audit_logger", None)
        if logger is None:
            return 0
        import sqlite3
        try:
            with sqlite3.connect(logger.db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()
            return int(row[0] if row else 0)
        except Exception:
            return 0

    def _recent_audit_events(self, limit: int) -> List[Dict[str, Any]]:
        logger = getattr(self.core, "_audit_logger", None)
        if logger is None:
            return []
        try:
            return logger.query_events(limit=limit)
        except Exception:
            return []

    def _trust_status_payload(self, audit_limit: int = 8) -> Dict[str, Any]:
        payload = self._status_view_payload()
        session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
        trust = payload.get("trust") if isinstance(payload.get("trust"), dict) else {}
        provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
        active = provider.get("active") if isinstance(provider.get("active"), dict) else {}
        recovery = payload.get("recovery") if isinstance(payload.get("recovery"), dict) else {}
        last_mutation = recovery.get("lastMutation") if isinstance(recovery.get("lastMutation"), dict) else {}
        security = trust.get("security") if isinstance(trust.get("security"), dict) else {}
        policy = self._permission_rule_summary()
        checkpoint_cfg = getattr(getattr(self.core, "config", None), "checkpoint", None)
        audit = trust.get("audit") if isinstance(trust.get("audit"), dict) else {}
        return {
            "providerName": active.get("name", ""),
            "providerModel": active.get("model", ""),
            "routingMode": session.get("routingMode", "manual"),
            "sandboxPreset": trust.get("sandboxPreset", ""),
            "permissionMode": session.get("permissionMode", self.permission_mode),
            "permissionRules": policy["rules"],
            "permissionRulesCount": policy["counts"]["total"],
            "policySummary": policy["counts"],
            "checkpointing": bool(trust.get("checkpointing", False)),
            "rollbackRetained": getattr(checkpoint_cfg, "max_checkpoints", ""),
            "lastCheckpointId": last_mutation.get("checkpointId", ""),
            "auditEnabled": bool(audit.get("enabled", False)),
            "auditPath": str(audit.get("path", "")),
            "auditRowCount": self._audit_row_count(),
            "auditEvents": self._recent_audit_events(max(1, min(int(audit_limit or 8), 50))),
            "privacyPosture": provider.get("privacyPosture", "unknown"),
            "dataLeavesMachine": provider.get("privacyPosture", "") != "local",
            "memorySources": security.get("trustedRoots", []),
        }

    async def handle_trust_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a flat trust-center payload."""
        self._ensure_initialized()
        return self._trust_status_payload(int(params.get("auditLimit", 8) or 8))

    async def handle_get_status_view(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the canonical session status payload shared across clients."""
        del params
        self._ensure_initialized()
        return await self._status_view_payload_async(allow_stale=True)

    async def handle_get_trust_view(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return the trust-center payload shared across clients."""
        del params
        self._ensure_initialized()
        payload = await self._status_view_payload_async(allow_stale=True)
        payload["view"] = "trust"
        return payload

    async def handle_audit_rotate_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run audit rotation if the installed audit logger supports it."""
        del params
        self._ensure_initialized()
        logger = getattr(self.core, "_audit_logger", None)
        before = self._audit_row_count()
        result: Any = None
        if logger is not None:
            rotate = getattr(logger, "rotate_if_needed", None) or getattr(logger, "rotate", None)
            if callable(rotate):
                try:
                    result = rotate(force=True)
                except TypeError:
                    result = rotate()
        return {
            "rotated": result is not None,
            "beforeRows": before,
            "afterRows": self._audit_row_count(),
            "result": result,
        }

    async def handle_audit_export_range(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Export audit events without changing the audit schema."""
        self._ensure_initialized()
        logger = getattr(self.core, "_audit_logger", None)
        if logger is None:
            raise RuntimeError("Audit logger unavailable")
        start = params.get("from") or params.get("since") or params.get("start") or params.get("startTime")
        end = params.get("to") or params.get("until") or params.get("end") or params.get("endTime")
        out = params.get("out") or params.get("outputPath") or params.get("path")
        if not out:
            from datetime import datetime, timezone
            out = logger.audit_dir / ("export-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + ".json")
        else:
            out = Path(str(out)).expanduser()
        export_range = getattr(logger, "export_range", None)
        if callable(export_range):
            try:
                result = export_range(start_time=start, end_time=end, output_path=out)
            except TypeError:
                result = export_range(start, end, out)
        else:
            logger.export_to_json(out, start_time=start, end_time=end)
            result = {"path": str(out)}
        return {"path": str(out), "result": result}

    async def handle_get_doctor_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return structured diagnostics with actionable remediation."""
        del params
        self._ensure_initialized()
        return self._doctor_report_payload()

    async def handle_get_sandbox_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return sandbox preset and capability summary."""
        del params
        self._ensure_initialized()
        preset = self._current_sandbox_preset()
        return {
            "sandboxPreset": preset,
            "permissionMode": self.permission_mode,
            "description": PRESET_DESCRIPTION.get(preset, ""),
            "trustedRoots": [str(root) for root in self._trusted_workspace_roots()],
        }

    async def handle_get_mcp_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return MCP connectivity and registered tool status."""
        del params
        self._ensure_initialized()
        return self.core.get_mcp_status()

    async def handle_get_startup_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return configured provider/model before full backend initialization."""
        del params
        from ...config_fast import load_runtime_model_settings

        settings = load_runtime_model_settings()
        return {
            "provider": str(settings.get("provider", "openai")),
            "model": str(settings.get("model", "")),
        }

    async def handle_mcp_health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of all registered MCP servers."""
        self._ensure_initialized()
        ensure_mcp = getattr(self.core, "_ensure_mcp_manager_initialized", None)
        if callable(ensure_mcp):
            await ensure_mcp()
        mcp = getattr(self.core, "_mcp_manager", None)
        if mcp is None:
            return {"servers": {}, "error": "No MCP servers configured"}
        try:
            results = await mcp.health_check_all()
            return {"servers": results}
        except Exception as e:
            return {"servers": {}, "error": str(e)}

    async def handle_get_docker_sandbox_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..docker_sandbox import docker_sandbox_status
        return docker_sandbox_status()

    async def handle_watch_scan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from poor_cli.file_watcher import scan_directory_for_instructions
        root = params.get("root")
        instructions = scan_directory_for_instructions(root=root)
        return {"instructions": instructions, "count": len(instructions)}

    async def handle_preview_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..preview_server import PreviewServer
        port = params.get("port", 3456)
        if not hasattr(self, "_preview_server"):
            self._preview_server = PreviewServer(port=port)
        return await self._preview_server.start()

    async def handle_preview_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(self, "_preview_server"):
            return await self._preview_server.stop()
        return {"stopped": []}

    async def handle_preview_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(self, "_preview_server"):
            return self._preview_server.status()
        return {"running": False, "mode": "none"}

    async def handle_get_command_manifest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from ...command_manifest import load_command_manifest, render_commands_markdown
            manifest = load_command_manifest()
            commands = []
            for c in manifest.commands:
                commands.append({
                    "name": c.command, "command": c.command,
                    "description": c.description, "summary": c.description,
                    "usage": c.command, "aliases": [], "category": c.category,
                    "recommended": c.recommended,
                })
            return {"commands": commands, "markdown": render_commands_markdown()}
        except Exception as e:
            return {"commands": [], "markdown": "", "error": str(e)}

    async def handle_get_recovery_suggestions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from ..error_recovery import ErrorRecoveryManager
        error_text = params.get("error", "")
        mgr = ErrorRecoveryManager()
        suggestions = mgr.get_suggestions(Exception(error_text))
        return {"suggestions": [{"title": s.title, "description": s.description, "commands": s.commands, "priority": s.priority} for s in suggestions]}

@register('getStartupState')
async def _rpc_4(ctx, params):
    return await ctx.handle_get_startup_state(params)

@register('poor-cli/getInstructionStack')
async def _rpc_24(ctx, params):
    return await ctx.handle_get_instruction_stack(params)

@register('poor-cli/getStatusView')
async def _rpc_25(ctx, params):
    return await ctx.handle_get_status_view(params)

@register('poor-cli/getTrustView')
async def _rpc_26(ctx, params):
    return await ctx.handle_get_trust_view(params)

@register('poor-cli/trustStatus')
async def _rpc_trust_status(ctx, params):
    return await ctx.handle_trust_status(params)

@register('policy.list')
async def _rpc_policy_list_dot(ctx, params):
    return await ctx.handle_policy_list(params)

@register('policy.reload')
async def _rpc_policy_reload_dot(ctx, params):
    return await ctx.handle_policy_reload(params)

@register('policy.edit')
async def _rpc_policy_edit_dot(ctx, params):
    return await ctx.handle_policy_edit(params)

@register('policy/list')
async def _rpc_policy_list_slash(ctx, params):
    return await ctx.handle_policy_list(params)

@register('policy/reload')
async def _rpc_policy_reload_slash(ctx, params):
    return await ctx.handle_policy_reload(params)

@register('policy/edit')
async def _rpc_policy_edit_slash(ctx, params):
    return await ctx.handle_policy_edit(params)

@register('poor-cli/getDoctorReport')
async def _rpc_27(ctx, params):
    return await ctx.handle_get_doctor_report(params)

@register('poor-cli/getPolicyStatus')
async def _rpc_28(ctx, params):
    return await ctx.handle_get_policy_status(params)

@register('poor-cli/getSandboxStatus')
async def _rpc_29(ctx, params):
    return await ctx.handle_get_sandbox_status(params)

@register('poor-cli/getMcpStatus')
async def _rpc_30(ctx, params):
    return await ctx.handle_get_mcp_status(params)

@register('poor-cli/mcpHealthCheck')
async def _rpc_113(ctx, params):
    return await ctx.handle_mcp_health_check(params)

@register('poor-cli/getDockerSandboxStatus')
async def _rpc_157(ctx, params):
    return await ctx.handle_get_docker_sandbox_status(params)

@register('poor-cli/watchScan')
async def _rpc_158(ctx, params):
    return await ctx.handle_watch_scan(params)

@register('poor-cli/previewStart')
async def _rpc_159(ctx, params):
    return await ctx.handle_preview_start(params)

@register('poor-cli/previewStop')
async def _rpc_160(ctx, params):
    return await ctx.handle_preview_stop(params)

@register('poor-cli/previewStatus')
async def _rpc_161(ctx, params):
    return await ctx.handle_preview_status(params)

@register('audit/rotateNow')
async def _rpc_audit_rotate_now(ctx, params):
    return await ctx.handle_audit_rotate_now(params)

@register('audit/exportRange')
async def _rpc_audit_export_range(ctx, params):
    return await ctx.handle_audit_export_range(params)

@register('poor-cli/getRecoverySuggestions')
async def _rpc_166(ctx, params):
    return await ctx.handle_get_recovery_suggestions(params)

@register('poor-cli/getCommandManifest')
async def _rpc_171(ctx, params):
    return await ctx.handle_get_command_manifest(params)

@register('commands.list')
async def _rpc_commands_list(ctx, params):
    return await ctx.handle_get_command_manifest(params)
