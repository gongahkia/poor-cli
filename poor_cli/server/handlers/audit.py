from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from poor_cli.server.registry import register


class AuditHandlersMixin:
    async def handle_audit_export_range(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        start_time = params.get("since") or params.get("from") or params.get("startTime")
        end_time = params.get("until") or params.get("end") or params.get("endTime") or params.get("to")
        output_path = params.get("out") or params.get("outputPath") or params.get("file")
        audit_logger = getattr(self.core, "_audit_logger", None)
        if audit_logger is None:
            from ...audit_log import AuditLogger

            audit_logger = AuditLogger(audit_dir=Path.cwd() / ".poor-cli")

        if output_path:
            path = Path(str(output_path)).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            count = audit_logger.export_range(
                start_time=str(start_time) if start_time else None,
                end_time=str(end_time) if end_time else None,
                output_path=path,
            )
            return {"count": count, "path": str(path)}

        jsonl = audit_logger.export_range_to_string(
            start_time=str(start_time) if start_time else None,
            end_time=str(end_time) if end_time else None,
        )
        return {"count": len([line for line in jsonl.splitlines() if line.strip()]), "jsonl": jsonl}

    async def handle_audit_rotate_now(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        audit_logger = getattr(self.core, "_audit_logger", None)
        if audit_logger is None:
            from ...audit_log import AuditLogger

            audit_logger = AuditLogger(audit_dir=Path.cwd() / ".poor-cli")
        return audit_logger.rotate_if_needed()


@register("poor-cli/auditExportRange")
async def _rpc_poor_cli_audit_export_range(ctx, params):
    return await ctx.handle_audit_export_range(params)
