import asyncio

from bench.context_memory_gate import run_gate


def test_context_memory_gate_passes():
    result = asyncio.run(run_gate())
    assert result["ok"] is True
    assert {check["name"] for check in result["checks"]} == {
        "context_routing",
        "lod_memory",
        "egress_grep",
    }
