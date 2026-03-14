from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from poor_cli.core import PoorCLICore
from poor_cli.tools_async import ToolOutcome


@pytest.mark.asyncio
async def test_plan_mode_requests_review_before_tool_execution():
    core = PoorCLICore()
    core._initialized = True
    core.provider = MagicMock()
    core.provider.format_tool_results = MagicMock(side_effect=lambda results: results)
    core.tool_registry = MagicMock()
    core.tool_registry.inspect_mutation_targets.return_value = ["/tmp/demo.py"]
    core.tool_registry.execute_tool_raw = AsyncMock(
        return_value=ToolOutcome(
            ok=True,
            operation="write_file",
            path="/tmp/demo.py",
            changed=True,
            message="done",
        )
    )
    core.config = MagicMock()
    core.config.plan_mode.enabled = True
    core.config.plan_mode.auto_plan_threshold = 1
    core.config.agentic.auto_approve_tools = []
    core.config.agentic.deny_patterns = []
    core.checkpoint_manager = None
    core._context_manager = None
    core.plan_callback = AsyncMock(return_value=False)

    response = SimpleNamespace(
        function_calls=[
            SimpleNamespace(
                id="call-1",
                name="write_file",
                arguments={"file_path": "/tmp/demo.py", "content": "x"},
            )
        ]
    )

    result = await core._handle_function_calls_events(
        response,
        iteration=0,
        max_iterations=5,
        request_id="req-1",
        user_request="update demo",
    )

    core.plan_callback.assert_awaited_once()
    core.tool_registry.execute_tool_raw.assert_not_awaited()
    assert result[0]["result"] == "Execution plan rejected by user"
