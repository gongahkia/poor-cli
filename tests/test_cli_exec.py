import json
import sys
from pathlib import Path

import pytest

from poor_cli import __main__ as cli_main


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
    assert payload["instructionStack"]["sourceCount"] == 1
    assert _FakeCore.created.last_context_files == ["README.md"]
    assert _FakeCore.created.last_context_budget_tokens == 4096
    assert _FakeCore.created.shutdown_called is True
