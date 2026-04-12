import asyncio
import logging
from pathlib import Path

import pytest

import poor_cli.server.handlers as server_handlers
from poor_cli.server.registry import REGISTRY, register
from poor_cli.server.runtime import PoorCLIServer
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
poor-cli/startHostServer
poor-cli/getHostServerStatus
poor-cli/getCollabSummary
poor-cli/stopHostServer
poor-cli/listHostMembers
poor-cli/removeHostMember
poor-cli/setHostMemberRole
poor-cli/setHostLobby
poor-cli/approveHostMember
poor-cli/denyHostMember
poor-cli/rotateHostToken
poor-cli/revokeHostToken
poor-cli/handoffHostMember
poor-cli/setHostPreset
poor-cli/listHostActivity
poor-cli/startService
poor-cli/stopService
poor-cli/getServiceStatus
poor-cli/getServiceLogs
poor-cli/cancelRequest
poor-cli/chatStreaming
poor-cli/pairStart
poor-cli/suggestText
poor-cli/peerMessage
poor-cli/passDriver
poor-cli/addAgendaItem
poor-cli/listAgenda
poor-cli/resolveAgendaItem
poor-cli/setHandRaised
poor-cli/nextDriver
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
poor-cli/latentCompatibility
""".split()


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
    missing = sorted(set(KNOWN_METHODS) - set(REGISTRY))
    assert missing == []


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
