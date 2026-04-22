import argparse
import asyncio
from pathlib import Path

from poor_cli.cli_app import _handle_chat_slash_command, _split_chat_slash


class FakeCore:
    def __init__(self):
        self.cleared = False
        self.switched = None

    async def clear_history(self):
        self.cleared = True

    def get_history(self):
        return [{"role": "user", "content": "hello"}]

    def build_status_view(self):
        return {"session": {"routingMode": "manual"}}

    def build_doctor_report(self):
        return {"summary": {"ok": True}}

    def get_session_cost_summary(self):
        return {"totalUsd": 0.0}

    def get_savings_summary(self, include_history=True):
        return {"includeHistory": include_history}

    def get_provider_info(self):
        return {"name": "test", "model": "stub"}

    async def switch_provider(self, provider, model=None):
        self.switched = (provider, model)

    def get_available_tools(self):
        return [{"name": "read_file"}, {"function": {"name": "bash"}}]

    async def execute_tool(self, name, args):
        return {"name": name, "args": args}


def test_split_chat_slash_preserves_rest():
    assert _split_chat_slash("/provider switch openai gpt-5") == (
        "/provider",
        "switch openai gpt-5",
    )


def test_chat_slash_clear_is_local(capsys):
    core = FakeCore()
    handled, message = asyncio.run(
        _handle_chat_slash_command(core, argparse.Namespace(), "/clear")
    )

    assert handled is True
    assert message == ""
    assert core.cleared is True
    assert "history cleared" in capsys.readouterr().out


def test_chat_slash_custom_command_renders_prompt(tmp_path, monkeypatch):
    commands = tmp_path / ".poor-cli" / "commands"
    commands.mkdir(parents=True)
    (commands / "standup.md").write_text("Summarize {{args}} from {{cwd}}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    handled, message = asyncio.run(
        _handle_chat_slash_command(FakeCore(), argparse.Namespace(), "/standup yesterday")
    )

    assert handled is False
    assert "Summarize yesterday" in message
    assert str(Path.cwd()) in message


def test_chat_slash_known_manifest_becomes_agent_request():
    handled, message = asyncio.run(
        _handle_chat_slash_command(FakeCore(), argparse.Namespace(), "/review staged diff")
    )

    assert handled is False
    assert message == "Run slash command /review with arguments: staged diff"
