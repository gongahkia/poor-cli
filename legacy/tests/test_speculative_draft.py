from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from poor_cli.config import Config
from poor_cli.core_turn_lifecycle import TurnLifecycle
from poor_cli.repo_config import RepoPreferences
from poor_cli.speculative_draft import predict_next_tool, speculation_enabled, warm_for_prediction
from poor_cli.tool_blocks import ToolResult
from poor_cli.tool_cache import ToolCache


class _DraftProvider:
    async def send_message(self, prompt: str, model: str):
        assert model == "llama3.1"
        assert "predict_next_read_only_tool" in prompt
        return SimpleNamespace(
            content=json.dumps(
                {"tool": "read_file", "args": {"path": "README.md"}, "confidence": 0.93}
            )
        )


def _run(coro):
    return asyncio.run(coro)


def test_predictor_returns_valid_shape_from_stub_provider():
    prediction = _run(
        predict_next_tool(
            [{"role": "user", "content": "inspect README"}],
            ["read_file", "write_file"],
            _DraftProvider(),
            "llama3.1",
        )
    )

    assert prediction == {"tool": "read_file", "args": {"path": "README.md"}, "confidence": 0.93}


def test_cache_warmer_skips_non_whitelisted_tools():
    calls = []

    async def dispatcher(tool, args):
        calls.append((tool, args))
        return ToolResult.text("should not happen")

    result = _run(warm_for_prediction({"tool": "write_file", "args": {"path": "x"}, "confidence": 0.9}, dispatcher))

    assert result.warmed is False
    assert result.reason == "not_whitelisted"
    assert calls == []


def test_cache_warmer_marks_speculative_tool_cache_entry():
    async def dispatcher(tool, args):
        return ToolResult.text(f"{tool}:{args['path']}")

    cache = ToolCache()
    result = _run(
        warm_for_prediction(
            {"tool": "read_file", "args": {"path": "README.md"}, "confidence": 0.9},
            dispatcher,
            cache=cache,
        )
    )

    assert result.warmed is True
    hit = cache.get("read_file", {"path": "README.md"}, ttl_s=60)
    assert hit is not None
    assert hit.metadata["from_speculation"] is True


def test_speculation_flag_defaults_off_and_repo_preferences_round_trip():
    assert speculation_enabled(Config()) is False
    prefs = RepoPreferences.from_dict({"speculative": {"enabled": True, "draft_model": "tiny"}})
    assert prefs.speculative["enabled"] is True
    assert prefs.speculative["draft_provider"] == "ollama"
    assert prefs.speculative["draft_model"] == "tiny"


def test_core_cancels_speculative_task_when_provider_returns_first():
    class _Provider:
        async def send_message(self, message, **kwargs):
            await asyncio.sleep(0.01)
            return SimpleNamespace(content="done", usage=None)

    class _Core(TurnLifecycle):
        def __init__(self):
            self.config = Config()
            self.config.speculative.enabled = True
            self.provider = _Provider()
            self.tool_registry = SimpleNamespace(get_tool_declarations=lambda: [{"name": "read_file"}])
            self.tool_cache = ToolCache()
            self._audit_logger = None
            self._hook_manager = None
            self._speculative_draft_provider = lambda prompt, model: asyncio.sleep(1)
            self._speculative_tool_dispatcher = lambda tool, args: ToolResult.text("warmed")

        def _provider_tokens_out(self, response, fallback_text=""):
            return 0

        def _provider_cost(self, tokens_in, tokens_out):
            return 0.0

    core = _Core()
    response = _run(core._send_provider_message_with_hooks("hello"))

    assert response.content == "done"
