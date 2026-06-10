from __future__ import annotations

from poor_cli.tui.autocomplete import Suggestion, all_suggestions, fuzzy_match


def test_fuzzy_match_prefix_wins() -> None:
    items = [
        Suggestion("/compress", "compress context", "core"),
        Suggestion("/compare", "compare costs", "cost"),
        Suggestion("/precommit", "commit checks", "git"),
    ]

    matches = fuzzy_match("/com", items)

    assert [match.command for match in matches[:2]] == ["/compare", "/compress"]
    assert "/precommit" in [match.command for match in matches]


def test_fuzzy_match_empty_query_returns_top_n_slash_commands() -> None:
    items = [
        Suggestion("/help", "help", "core"),
        Suggestion("plain", "plain", "core"),
        Suggestion("/status", "status", "core"),
    ]

    matches = fuzzy_match("/", items, limit=1)

    assert [match.command for match in matches] == ["/help"]


def test_all_suggestions_missing_custom_command_dirs_is_graceful(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    suggestions = all_suggestions()

    assert suggestions
    assert all(suggestion.command.startswith("/") for suggestion in suggestions)
