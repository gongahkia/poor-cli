import asyncio
import logging
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

import poor_cli.server.handlers as server_handlers
from poor_cli.server.registry import REGISTRY, ensure_handlers_loaded, register
from poor_cli.server.runtime import PoorCLIServer
from poor_cli.server.services_state import ServicesStateMixin
from poor_cli.server.types import JsonRpcMessage


KNOWN_METHODS = """
initialize
shutdown
chat
listProviders
getStartupState
switchProvider
getConfig
setConfig
getPermissions
setPermissions
setApiKey
getApiKeyStatus
startService
stopService
getServiceStatus
getServiceLogs
poor-cli/chat
poor-cli/inlineComplete
poor-cli/applyEdit
poor-cli/readFile
poor-cli/executeCommand
poor-cli/getTools
poor-cli/switchProvider
poor-cli/getProviderInfo
poor-cli/getInstructionStack
poor-cli/getStatusView
poor-cli/getTrustView
poor-cli/getDoctorReport
poor-cli/getPolicyStatus
poor-cli/getSandboxStatus
poor-cli/getMcpStatus
poor-cli/clearHistory
poor-cli/compactContext
poor-cli/previewContext
poor-cli/getContextExplain
context.snapshot
context.refresh
context.pin
context.drop
poor-cli/previewMutation
poor-cli/exec
poor-cli/listRuns
poor-cli/listWorkflows
poor-cli/getWorkflow
poor-cli/listConfigOptions
poor-cli/setConfig
poor-cli/getPermissions
poor-cli/setPermissions
poor-cli/toggleConfig
poor-cli/setApiKey
poor-cli/getApiKeyStatus
poor-cli/testApiKey
poor-cli/listProviders
poor-cli/listSessions
poor-cli/listHistory
poor-cli/searchHistory
poor-cli/listSkills
poor-cli/getSkill
poor-cli/listCustomCommands
poor-cli/getCustomCommand
poor-cli/runCustomCommand
poor-cli/createTask
poor-cli/listTasks
poor-cli/getTask
poor-cli/startTask
poor-cli/approveTask
poor-cli/cancelTask
poor-cli/retryTask
poor-cli/replayTask
poor-cli/createAutomation
poor-cli/listAutomations
poor-cli/getAutomation
poor-cli/setAutomationEnabled
poor-cli/runAutomationNow
poor-cli/runDueAutomations
poor-cli/getAutomationHistory
poor-cli/replayAutomation
poor-cli/listCheckpoints
poor-cli/createCheckpoint
poor-cli/restoreCheckpoint
poor-cli/previewCheckpoint
poor-cli/compareFiles
poor-cli/exportConversation
poor-cli/startService
poor-cli/stopService
poor-cli/getServiceStatus
poor-cli/getServiceLogs
poor-cli/cancelRequest
poor-cli/chatStreaming
poor-cli/toolStreamAck
poor-cli/cancelTool
timeline.list
timeline.cancel
timeline.retry
timeline.dismiss
plan.list
plan.advance
plan.regress
plan.block
plan.add
plan.delete
poor-cli/getSessionCost
poor-cli/listOllamaModels
poor-cli/gcCheckpoints
poor-cli/saveSession
poor-cli/mcpHealthCheck
poor-cli/restoreSession
poor-cli/getEconomySavings
poor-cli/setEconomyPreset
poor-cli/getCacheStats
poor-cli/clearSemanticCache
poor-cli/getContextPressure
poor-cli/getContextBreakdown
poor-cli/estimateCost
poor-cli/compareModelCost
poor-cli/exportCostReport
poor-cli/getTokensVisualization
poor-cli/getCostHistory
poor-cli/applyBudgetTemplate
poor-cli/listBudgetTemplates
poor-cli/createSession
poor-cli/destroySession
poor-cli/switchSession
poor-cli/forkSession
poor-cli/listMuxSessions
poor-cli/renameSession
poor-cli/getCompletion
poor-cli/semanticSearch
poor-cli/indexCodebase
poor-cli/getIndexStats
poor-cli/indexEmbeddings
poor-cli/vectorSearch
poor-cli/hybridSearch
poor-cli/createAgent
poor-cli/listAgents
poor-cli/getAgent
poor-cli/startAgent
poor-cli/cancelAgent
poor-cli/getAgentLogs
poor-cli/getAgentResult
poor-cli/listProfiles
poor-cli/applyProfile
poor-cli/getTrustStatus
poor-cli/trustRepo
poor-cli/untrustRepo
poor-cli/memoryList
poor-cli/memorySave
poor-cli/memorySearch
poor-cli/memoryDelete
poor-cli/getDockerSandboxStatus
poor-cli/watchScan
watch.status
poor-cli/previewStart
poor-cli/previewStop
poor-cli/previewStatus
poor-cli/deploy
poor-cli/deployTargets
poor-cli/deployValidate
poor-cli/deployHistory
poor-cli/getRecoverySuggestions
poor-cli/promptSave
poor-cli/promptLoad
poor-cli/promptList
poor-cli/promptDelete
poor-cli/getCommandManifest
commands.list
poor-cli/latentCompatibility
branches.tree
branches.switch
poor-cli/branchesTree
poor-cli/branchesSwitch
chat.regenerate
poor-cli/regenerateTurn
chat.switch
chat.siblings
""".split()


def test_tcp_endpoint_reachable_bound_method_uses_host_string(monkeypatch):
    seen = {}

    def fake_create_connection(addr, timeout):
        seen["addr"] = addr
        seen["timeout"] = timeout

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        return Conn()

    monkeypatch.setattr("socket.create_connection", fake_create_connection)

    assert ServicesStateMixin()._is_tcp_endpoint_reachable("localhost", 11434, 0.1)
    assert seen == {"addr": ("localhost", 11434), "timeout": 0.1}


def test_registry_registers_unique_methods():
    method = "poor-cli/testDuplicateRegistration"
    REGISTRY.pop(method, None)

    async def first(ctx, params):
        return None

    async def second(ctx, params):
        return None

    try:
        register(method)(first)
        with pytest.raises(RuntimeError):
            register(method)(second)
    finally:
        REGISTRY.pop(method, None)


def test_every_known_method_still_reachable():
    assert server_handlers.HandlerMixin is not None
    ensure_handlers_loaded()
    missing = sorted(set(KNOWN_METHODS) - set(REGISTRY))
    assert missing == []


def test_status_view_payload_uses_ttl_cache_and_returns_copy():
    server = PoorCLIServer()

    class CoreStub:
        def __init__(self) -> None:
            self.calls = 0

        def build_status_view(self):
            self.calls += 1
            return {
                "session": {"routingMode": "manual"},
                "trust": {},
                "provider": {},
                "context": {},
                "runs": {},
                "recovery": {},
            }

    core = CoreStub()
    server.core = core
    server._status_view_cache_ttl_ms = 1000.0
    payload = server._status_view_payload()
    payload["session"]["routingMode"] = "mutated"
    second = server._status_view_payload()
    assert core.calls == 1
    assert second["session"]["routingMode"] == "manual"


def test_server_default_session_is_lazy_until_core_access():
    server = PoorCLIServer()
    assert server._session_manager is None
    _ = server.core
    assert server._session_manager is not None
    assert server._session_manager.default_session is not None


def test_get_startup_state_does_not_force_core_session_creation():
    server = PoorCLIServer()
    assert server._session_manager is None
    payload = asyncio.run(server.handle_get_startup_state({}))
    assert isinstance(payload.get("provider"), str)
    assert isinstance(payload.get("model"), str)
    assert server._session_manager is None


def test_get_status_view_returns_stale_then_coalesces_refresh():
    server = PoorCLIServer()
    server.initialized = True

    class CoreStub:
        def __init__(self) -> None:
            self.calls = 0

        def build_status_view(self):
            self.calls += 1
            time.sleep(0.05)
            return {
                "session": {"routingMode": f"fresh-{self.calls}"},
                "trust": {},
                "provider": {},
                "context": {},
                "runs": {},
                "recovery": {},
            }

    core = CoreStub()
    server.core = core
    server._status_view_cache_ttl_ms = 250.0
    server._status_view_cache_payload = {
        "session": {"routingMode": "stale"},
        "trust": {},
        "provider": {},
        "context": {},
        "runs": {},
        "recovery": {},
    }
    server._status_view_cache_at = time.monotonic() - 1.0

    async def _run():
        started = time.perf_counter()
        first = await server.handle_get_status_view({})
        second = await server.handle_get_status_view({})
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        await asyncio.sleep(0.12)
        third = await server.handle_get_status_view({})
        return first, second, third, elapsed_ms

    first, second, third, elapsed_ms = asyncio.run(_run())

    assert first["session"]["routingMode"] == "stale"
    assert second["session"]["routingMode"] == "stale"
    assert elapsed_ms < 35.0
    assert third["session"]["routingMode"] == "fresh-1"
    assert core.calls == 1


def test_dispatch_uses_registry_across_handler_families(monkeypatch):
    server = PoorCLIServer.__new__(PoorCLIServer)
    server.logger = logging.getLogger("test.server.dispatch")

    async def fake_chat(ctx, params):
        return {"family": "chat", "sameCtx": ctx is server, "params": params}

    async def fake_provider(ctx, params):
        return {"family": "providers", "sameCtx": ctx is server, "params": params}

    async def fake_task(ctx, params):
        return {"family": "tasks", "sameCtx": ctx is server, "params": params}

    monkeypatch.setitem(REGISTRY, "poor-cli/chat", fake_chat)
    monkeypatch.setitem(REGISTRY, "poor-cli/listProviders", fake_provider)
    monkeypatch.setitem(REGISTRY, "poor-cli/createTask", fake_task)

    async def run():
        responses = []
        for idx, method in enumerate(("poor-cli/chat", "poor-cli/listProviders", "poor-cli/createTask")):
            responses.append(
                await PoorCLIServer.dispatch(
                    server,
                    JsonRpcMessage(id=idx, method=method, params={"idx": idx}),
                )
            )
        return responses

    results = asyncio.run(run())
    assert [result.result["family"] for result in results] == ["chat", "providers", "tasks"]
    assert all(result.result["sameCtx"] is True for result in results)
    assert [result.result["params"]["idx"] for result in results] == [0, 1, 2]


def _inline_server(core):
    server = PoorCLIServer.__new__(PoorCLIServer)
    server._ensure_initialized = lambda: None
    session = SimpleNamespace(core=core)
    server._session_manager = SimpleNamespace(get_session=lambda *args, **kwargs: session)
    return server


def test_inline_complete_legacy_shape_without_count():
    class Core:
        calls = 0

        async def inline_complete(self, **kwargs):
            self.calls += 1
            yield "abc"

    server = _inline_server(Core())

    result = asyncio.run(server.handle_inline_complete({}))
    assert result == {"completion": "abc", "isPartial": False}
    assert server.core.calls == 1


def test_inline_complete_returns_ordered_candidates():
    class Core:
        calls = 0

        async def inline_complete(self, **kwargs):
            self.calls += 1
            yield f"candidate-{self.calls}"

    server = _inline_server(Core())

    result = asyncio.run(server.handle_inline_complete({"completions_count": 3}))
    assert result == {
        "completion": "candidate-1",
        "completions": ["candidate-1", "candidate-2", "candidate-3"],
        "isPartial": False,
    }


def test_inline_complete_preserves_empty_candidate_slots():
    class Core:
        calls = 0

        async def inline_complete(self, **kwargs):
            self.calls += 1
            if self.calls == 2:
                yield "middle"

    server = _inline_server(Core())

    result = asyncio.run(server.handle_inline_complete({"completions_count": 3}))
    assert result["completions"] == ["", "middle", ""]


def test_inline_complete_clamps_invalid_count_to_legacy_shape():
    class Core:
        calls = 0

        async def inline_complete(self, **kwargs):
            self.calls += 1
            yield "only"

    server = _inline_server(Core())

    result = asyncio.run(server.handle_inline_complete({"completions_count": 0}))
    assert result == {"completion": "only", "isPartial": False}
    assert server.core.calls == 1


def test_runtime_py_under_800_lines():
    runtime = Path(__file__).resolve().parents[1] / "poor_cli" / "server" / "runtime.py"
    assert sum(1 for _ in runtime.open(encoding="utf-8")) <= 800


def test_every_handler_file_under_500_lines():
    handlers = Path(__file__).resolve().parents[1] / "poor_cli" / "server" / "handlers"
    oversized = {
        path.name: sum(1 for _ in path.open(encoding="utf-8"))
        for path in handlers.glob("*.py")
        if sum(1 for _ in path.open(encoding="utf-8")) > 500
    }
    assert oversized == {}
