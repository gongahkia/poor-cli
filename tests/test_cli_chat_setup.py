from __future__ import annotations

import argparse
import asyncio

from poor_cli.cli_app import (
    _extract_inline_api_key,
    _format_chat_blocker,
    _initialize_chat_core,
)
from poor_cli.exceptions import MissingAPIKeyError


def test_format_chat_blocker_turns_missing_key_into_assistant_text() -> None:
    message = _format_chat_blocker(
        MissingAPIKeyError(
            "No API key found for provider: openai. Set environment variable: OPENAI_API_KEY"
        )
    )

    assert "I can't call the model yet" in message
    assert "OPENAI_API_KEY" in message
    assert "use api key <key>" in message


def test_extract_inline_api_key_accepts_conversational_forms() -> None:
    assert _extract_inline_api_key("use api key sk-test") == "sk-test"
    assert _extract_inline_api_key("my api key is 'sk-test'") == "sk-test"
    assert _extract_inline_api_key("OPENAI_API_KEY=sk-test") == "sk-test"
    assert _extract_inline_api_key("hello") == ""


def test_initialize_chat_core_falls_back_to_minimal_on_missing_key() -> None:
    class Core:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def initialize(self, **kwargs: object) -> None:
            self.calls.append(kwargs)
            if not kwargs.get("minimal"):
                raise MissingAPIKeyError(
                    "No API key found for provider: openai. Set environment variable: OPENAI_API_KEY"
                )

    args = argparse.Namespace(provider="openai", model=None, api_key=None)
    core = Core()
    error = asyncio.run(_initialize_chat_core(core, args))

    assert isinstance(error, MissingAPIKeyError)
    assert core.calls == [
        {"provider_name": "openai", "model_name": None, "api_key": None},
        {"provider_name": "openai", "model_name": None, "minimal": True},
    ]
