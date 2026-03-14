import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from poor_cli.audit_log import AuditEventType, AuditLogger
from poor_cli.core import PoorCLICore
from poor_cli.tools_async import ToolOutcome


@pytest.mark.asyncio
async def test_execute_tool_internal_writes_audit_entry(tmp_path: Path):
    core = PoorCLICore()
    core._initialized = True
    core.config = MagicMock()
    core.config.checkpoint.enabled = False
    core.config.plan_mode.enabled = False
    core.tool_registry = MagicMock()
    core.tool_registry.inspect_mutation_targets.return_value = [str(tmp_path / "demo.py")]
    core.tool_registry.execute_tool_raw = AsyncMock(
        return_value=ToolOutcome(
            ok=True,
            operation="write_file",
            path=str(tmp_path / "demo.py"),
            changed=True,
            message="updated",
        )
    )
    core._audit_logger = AuditLogger(audit_dir=tmp_path / "audit")
    core._hook_manager = None
    core._context_manager = None

    await core._execute_tool_internal("write_file", {"file_path": str(tmp_path / "demo.py")})

    events = core._audit_logger.query_events(event_type=AuditEventType.TOOL_EXECUTION, limit=10)
    assert len(events) == 1
    assert events[0]["event_type"] == AuditEventType.TOOL_EXECUTION.value
    details = json.loads(events[0]["details"])
    assert details["toolName"] == "write_file"
    assert details["message"] == "updated"
