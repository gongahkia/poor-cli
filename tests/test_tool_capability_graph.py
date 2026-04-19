from __future__ import annotations

from types import SimpleNamespace

import pytest

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.enhanced_tools import EnhancedToolRegistry
from poor_cli.providers.base import FunctionCall
from poor_cli.tool_capability_graph import (
    GRAPH_FILENAME,
    PERSIST_EVERY_N_UPDATES,
    ToolCapabilityGraph,
)


def test_graph_persists_without_lockup(tmp_path):
    graph = ToolCapabilityGraph(base_dir=tmp_path)
    for idx in range(PERSIST_EVERY_N_UPDATES + 1):
        call_id = f"c{idx}"
        graph.observe_tool_call_start(
            request_id="req",
            call_id=call_id,
            tool_name="read_file",
            group="core",
            consumed_paths=["README.md"],
        )
    assert (tmp_path / GRAPH_FILENAME).exists()


def test_rank_tool_names_prefers_successful_low_latency(tmp_path):
    graph = ToolCapabilityGraph(base_dir=tmp_path)
    for idx in range(8):
        call_id = f"a{idx}"
        graph.observe_tool_call_start(request_id="ra", call_id=call_id, tool_name="read_file", group="core")
        graph.observe_tool_call_result(
            request_id="ra",
            call_id=call_id,
            tool_name="read_file",
            success=True,
            latency_ms=40.0,
        )
    for idx in range(5):
        call_id = f"b{idx}"
        graph.observe_tool_call_start(request_id="rb", call_id=call_id, tool_name="bash", group="core")
        graph.observe_tool_call_result(
            request_id="rb",
            call_id=call_id,
            tool_name="bash",
            success=False,
            latency_ms=1800.0,
        )
    ranked = graph.rank_tool_names(["bash", "read_file"])
    assert ranked[0] == "read_file"


def test_suggest_followup_groups_from_transitions(tmp_path):
    graph = ToolCapabilityGraph(base_dir=tmp_path)
    for idx in range(12):
        request_id = f"r{idx}"
        graph.observe_tool_call_start(request_id=request_id, call_id=f"{request_id}-1", tool_name="read_file", group="core")
        graph.observe_tool_call_result(
            request_id=request_id,
            call_id=f"{request_id}-1",
            tool_name="read_file",
            success=True,
            latency_ms=10.0,
            produced_paths=["README.md"],
        )
        graph.observe_tool_call_start(
            request_id=request_id,
            call_id=f"{request_id}-2",
            tool_name="grep_files",
            group="search",
            consumed_paths=["README.md"],
        )
        graph.observe_tool_call_result(
            request_id=request_id,
            call_id=f"{request_id}-2",
            tool_name="grep_files",
            success=True,
            latency_ms=22.0,
        )
    suggestions = graph.suggest_followup_groups(
        seed_groups=["core"],
        available_groups=["core", "search", "git"],
        prompt="check it",
        limit=2,
    )
    assert suggestions
    assert suggestions[0] == "search"


def test_registry_uses_graph_for_group_suggestions(tmp_path):
    graph = ToolCapabilityGraph(base_dir=tmp_path)
    for idx in range(10):
        request_id = f"w{idx}"
        graph.observe_tool_call_start(request_id=request_id, call_id=f"{request_id}-1", tool_name="read_file", group="core")
        graph.observe_tool_call_result(
            request_id=request_id,
            call_id=f"{request_id}-1",
            tool_name="read_file",
            success=True,
            latency_ms=15.0,
        )
        graph.observe_tool_call_start(request_id=request_id, call_id=f"{request_id}-2", tool_name="web_search", group="network")
        graph.observe_tool_call_result(
            request_id=request_id,
            call_id=f"{request_id}-2",
            tool_name="web_search",
            success=True,
            latency_ms=120.0,
        )

    baseline = EnhancedToolRegistry(Config())
    guided = EnhancedToolRegistry(Config(), capability_graph=graph)
    assert baseline.required_tool_groups("check this request") == ["core"]
    with_graph = guided.required_tool_groups("check this request")
    assert with_graph[0] == "core"
    assert "network" in with_graph


def test_registry_caps_graph_suggestions_by_schema_budget(tmp_path):
    graph = ToolCapabilityGraph(base_dir=tmp_path)
    for idx in range(10):
        request_id = f"b{idx}"
        graph.observe_tool_call_start(request_id=request_id, call_id=f"{request_id}-1", tool_name="read_file", group="core")
        graph.observe_tool_call_result(
            request_id=request_id,
            call_id=f"{request_id}-1",
            tool_name="read_file",
            success=True,
            latency_ms=12.0,
        )
        graph.observe_tool_call_start(request_id=request_id, call_id=f"{request_id}-2", tool_name="web_search", group="network")
        graph.observe_tool_call_result(
            request_id=request_id,
            call_id=f"{request_id}-2",
            tool_name="web_search",
            success=True,
            latency_ms=80.0,
        )

    guided = EnhancedToolRegistry(Config(), capability_graph=graph)
    core_budget = guided._schema_tokens_for_groups(["core"])
    constrained = guided.required_tool_groups("check this request", schema_token_budget=core_budget)
    unconstrained = guided.required_tool_groups("check this request", schema_token_budget=core_budget + 100000)
    assert constrained == ["core"]
    assert "network" in unconstrained


@pytest.mark.asyncio
async def test_execute_single_call_events_records_graph_file_flow(tmp_path):
    graph = ToolCapabilityGraph(base_dir=tmp_path)
    core = object.__new__(PoorCLICore)
    core.config = Config()
    core.tool_registry = EnhancedToolRegistry(Config(), capability_graph=graph)
    core._tool_capability_graph = graph
    core._mcp_manager = None
    core._active_tool_names = {"read_file", "write_file"}
    core._active_tool_groups = ("core",)
    core._permission_callback = None
    core._tool_full_outputs = {}
    core._last_file_contents = {}
    core._turn_economy = SimpleNamespace(diff_only_applied=False)
    core._audit_logger = None

    async def _execute_tool_internal(tool_name: str, arguments):
        if tool_name == "write_file":
            return "wrote"
        if tool_name == "read_file":
            return "read"
        return "ok"

    core._execute_tool_internal = _execute_tool_internal

    await core._execute_single_call_events(
        FunctionCall(id="call-1", name="write_file", arguments={"file_path": "tmp/demo.txt", "content": "x"}),
        iteration=1,
        max_iterations=4,
        request_id="req-graph",
        expected_call_count=2,
        user_request="write file",
    )
    await core._execute_single_call_events(
        FunctionCall(id="call-2", name="read_file", arguments={"file_path": "tmp/demo.txt"}),
        iteration=1,
        max_iterations=4,
        request_id="req-graph",
        expected_call_count=2,
        user_request="read file",
    )

    snapshot = graph.snapshot()
    edge = snapshot["edges"].get("write_file\x1fread_file", {})
    assert int(edge.get("transitions", 0) or 0) >= 1
    assert int(edge.get("file_flow", 0) or 0) >= 1
