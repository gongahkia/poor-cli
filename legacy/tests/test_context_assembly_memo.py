from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from poor_cli.context_assembly import ContextAssemblyOrchestrator, ContextFile


class _ProviderStub:
    def __init__(self) -> None:
        self._history = []

    def get_history(self):
        return list(self._history)

    def get_capabilities(self):
        return SimpleNamespace(max_context_tokens=0)


class _CoreStub:
    def __init__(self) -> None:
        self._context_compressor = None
        self._tiered_compactor = None
        self._block_cache = None
        self._system_instruction = "sys"
        self._system_context_hash = "syshash"
        self._active_tool_groups = tuple()
        self._active_tool_names = set()
        self._active_tool_declarations = []
        self._context_dropped_files = set()
        self.provider = _ProviderStub()
        self.config = SimpleNamespace(
            model=SimpleNamespace(provider="openai", model_name="gpt-5"),
            history=SimpleNamespace(max_token_limit=10000),
        )

    def _instruction_snapshot_hash(self) -> str:
        return ""


def _run(coro):
    return asyncio.run(coro)


def test_snapshot_memo_reuses_identical_consecutive_assembly(monkeypatch):
    core = _CoreStub()
    orchestrator = ContextAssemblyOrchestrator(core)
    calls = {"assemble_user_message": 0}

    async def _fake_assemble_user_message(_request):
        calls["assemble_user_message"] += 1
        return "User request: hi", None, [], "rules"

    monkeypatch.setattr(orchestrator, "_assemble_user_message", _fake_assemble_user_message)
    monkeypatch.setattr(orchestrator, "_tool_schemas", lambda: [])
    monkeypatch.setattr(orchestrator, "_history", lambda: [])
    monkeypatch.setattr(orchestrator, "_context_files", lambda _context_result: tuple())
    monkeypatch.setattr(
        orchestrator,
        "_token_breakdown",
        lambda **_kwargs: {
            "system": 1,
            "rules": 1,
            "files": 0,
            "history": 0,
            "tools": 0,
            "messages": 1,
            "total": 3,
        },
    )
    monkeypatch.setattr(orchestrator, "_snapshot_key", lambda **_kwargs: "snapshot-key")

    first = _run(orchestrator.assemble(prompt="hi", activate_tools=False))
    second = _run(orchestrator.assemble(prompt="hi", activate_tools=False))

    assert calls["assemble_user_message"] == 1
    assert first is second


def test_snapshot_memo_invalidates_when_selected_file_changes(monkeypatch, tmp_path):
    core = _CoreStub()
    orchestrator = ContextAssemblyOrchestrator(core)
    calls = {"assemble_user_message": 0}
    target = tmp_path / "tracked.py"
    target.write_text("print('v1')\n", encoding="utf-8")

    async def _fake_assemble_user_message(_request):
        calls["assemble_user_message"] += 1
        return "User request: hi", object(), [], "rules"

    monkeypatch.setattr(orchestrator, "_assemble_user_message", _fake_assemble_user_message)
    monkeypatch.setattr(orchestrator, "_tool_schemas", lambda: [])
    monkeypatch.setattr(orchestrator, "_history", lambda: [])
    monkeypatch.setattr(
        orchestrator,
        "_context_files",
        lambda _context_result: (
            ContextFile(
                path=str(target),
                content="print('v1')\n",
                tokens=1,
                reason="selected",
                compressed=False,
            ),
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "_token_breakdown",
        lambda **_kwargs: {
            "system": 1,
            "rules": 1,
            "files": 1,
            "history": 0,
            "tools": 0,
            "messages": 1,
            "total": 4,
        },
    )
    monkeypatch.setattr(orchestrator, "_snapshot_key", lambda **_kwargs: "snapshot-key")

    _run(orchestrator.assemble(prompt="hi", activate_tools=False))
    _run(orchestrator.assemble(prompt="hi", activate_tools=False))
    assert calls["assemble_user_message"] == 1

    time.sleep(0.01)
    target.write_text("print('v2')\n", encoding="utf-8")

    _run(orchestrator.assemble(prompt="hi", activate_tools=False))
    assert calls["assemble_user_message"] == 2
