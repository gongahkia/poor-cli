import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli import __main__ as cli_main
from poor_cli.sandbox import ToolCapability


class _FakeCore:
    created = None

    def __init__(self, config_path=None):
        self.config_path = config_path
        self.initialized_with = None
        self.shutdown_called = False
        self.permission_callback = None
        _FakeCore.created = self

    async def initialize(self, provider_name=None, model_name=None, api_key=None):
        self.initialized_with = {
            "provider": provider_name,
            "model": model_name,
            "api_key": api_key,
        }
        self.config = SimpleNamespace(
            security=SimpleNamespace(
                permission_mode="prompt",
                safe_commands=["pwd", "ls", "echo", "cat", "head", "tail", "grep", "find", "which", "whoami", "date"],
                trusted_roots=[],
                enforce_trusted_workspace=True,
            ),
            sandbox=SimpleNamespace(default_preset="workspace-write"),
        )
        self.tool_registry = SimpleNamespace(
            get_tool_capabilities=lambda tool_name: {
                "read_file": [ToolCapability.FILESYSTEM_READ.value],
                "write_file": [ToolCapability.FILESYSTEM_WRITE.value],
                "bash": [ToolCapability.PROCESS_EXECUTE.value],
            }.get(tool_name, []),
            inspect_mutation_targets=lambda tool_name, tool_args: [
                tool_args.get("file_path", "")
            ] if tool_name in {"write_file"} else [],
        )

    async def send_message_sync(
        self,
        message,
        context_files=None,
        pinned_context_files=None,
        context_budget_tokens=None,
    ):
        self.last_message = message
        self.last_context_files = context_files
        self.last_pinned_context_files = pinned_context_files
        self.last_context_budget_tokens = context_budget_tokens
        return "assistant result"

    def get_provider_info(self):
        return {"name": "gemini", "model": "gemini-2.0-flash"}

    def inspect_instruction_stack(self, referenced_files=None):
        return {"sourceCount": 1, "sources": [{"label": "Repo Root AGENTS.md"}]}

    async def shutdown(self):
        self.shutdown_called = True


def test_exec_output_format_json(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(cli_main, "PoorCLICore", _FakeCore)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "poor-cli",
            "exec",
            "--prompt",
            "summarize this",
            "--output-format",
            "json",
            "--context-file",
            "README.md",
            "--context-budget-tokens",
            "4096",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 0

    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["content"] == "assistant result"
    assert payload["provider"]["name"] == "gemini"
    assert payload["permissionMode"] == "prompt"
    assert payload["sandboxPreset"] == "workspace-write"
    assert payload["autoApprove"] is False
    assert payload["instructionStack"]["sourceCount"] == 1
    assert _FakeCore.created.last_context_files == ["README.md"]
    assert _FakeCore.created.last_context_budget_tokens == 4096
    assert _FakeCore.created.shutdown_called is True


@pytest.mark.asyncio
async def test_exec_permission_callback_denies_mutations_without_auto_approve(tmp_path: Path):
    core = _FakeCore()
    await core.initialize()
    core.config.security.trusted_roots = [str(tmp_path)]
    callback = cli_main._build_exec_permission_callback(
        core,
        allow_tools=set(),
        deny_tools=set(),
        plan_only=False,
        permission_mode="prompt",
        sandbox_preset="workspace-write",
        auto_approve=False,
    )

    decision = await callback(
        "write_file",
        {"file_path": str(tmp_path / "note.txt"), "content": "hello"},
        {"paths": [str(tmp_path / "note.txt")]},
    )

    assert decision["allowed"] is False


@pytest.mark.asyncio
async def test_exec_permission_callback_allows_mutations_with_auto_approve(tmp_path: Path):
    core = _FakeCore()
    await core.initialize()
    core.config.security.trusted_roots = [str(tmp_path)]
    callback = cli_main._build_exec_permission_callback(
        core,
        allow_tools=set(),
        deny_tools=set(),
        plan_only=False,
        permission_mode="prompt",
        sandbox_preset="workspace-write",
        auto_approve=True,
    )

    decision = await callback(
        "write_file",
        {"file_path": str(tmp_path / "note.txt"), "content": "hello"},
        {"paths": [str(tmp_path / "note.txt")]},
    )

    assert decision["allowed"] is True


@pytest.mark.asyncio
async def test_exec_permission_callback_respects_safe_process_mode():
    core = _FakeCore()
    await core.initialize()
    callback = cli_main._build_exec_permission_callback(
        core,
        allow_tools=set(),
        deny_tools=set(),
        plan_only=False,
        permission_mode="auto-safe",
        sandbox_preset="workspace-write",
        auto_approve=False,
    )

    safe_decision = await callback("bash", {"command": "pwd"}, None)
    unsafe_decision = await callback("bash", {"command": "touch demo.txt"}, None)

    assert safe_decision["allowed"] is True
    assert unsafe_decision["allowed"] is False
