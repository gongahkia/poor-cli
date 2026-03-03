"""Tests for prompt_toolkit-based input completion behavior."""

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from poor_cli.enhanced_input import CommandCompleter, EnhancedInputManager


def _command_completions(text: str):
    completer = CommandCompleter()
    document = Document(text=text, cursor_position=len(text))
    event = CompleteEvent(completion_requested=False)
    return list(completer.get_completions(document, event))


def test_bare_slash_shows_recommended_commands_only():
    completions = _command_completions("/")
    completion_texts = [completion.text for completion in completions]

    assert completion_texts
    assert "/help" in completion_texts
    assert "/review" in completion_texts
    assert "/quit" not in completion_texts

    recommended = {
        spec.command for spec in CommandCompleter.COMMAND_SPECS if spec.recommended
    }
    assert set(completion_texts).issubset(recommended)


def test_prefix_filters_to_matching_supported_commands():
    completions = _command_completions("/pro")
    assert [completion.text for completion in completions] == ["/provider", "/providers"]


def test_extract_command_token_ignores_leading_whitespace():
    assert CommandCompleter.extract_command_token("   /review app.py") == "/review"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/", True),
        ("/re", True),
        ("/review app.py", False),
        ("hello world", False),
    ],
)
def test_live_completion_only_enabled_for_command_token(text, expected):
    assert EnhancedInputManager.should_show_live_completions(text) is expected
