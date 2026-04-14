from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from poor_cli.config import Config
from poor_cli.core import PoorCLICore
from poor_cli.economy import EconomySavingsTracker
from poor_cli.shell_filters import apply
from poor_cli.tools_async import FilteredToolResult, ToolRegistryAsync

FIXTURES = Path(__file__).parent / "fixtures" / "shell_filters"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_git_status_filter_reduces_tokens_by_60_percent_on_fixture() -> None:
    raw = _fixture("git_status.txt")
    result = apply("git status", raw)
    assert result.applied
    assert result.tokens_after <= result.tokens_before * 0.4


def test_git_status_filter_preserves_all_changed_paths() -> None:
    raw = _fixture("git_status.txt")
    result = apply("git status", raw)
    for path in (
        "poor-cli/tools_async.py",
        "poor-cli/shell_filters/__init__.py",
        "poor-cli/shell_filters/git.py",
        "poor-cli/config.py",
        "docs/old_rtk_notes.md",
        "tests/test_rtk_lite_git.py -> tests/test_shell_filters.py",
        "tests/fixtures/shell_filters/git_status.txt",
        "tests/fixtures/shell_filters/git_diff_stat.txt",
        "tests/fixtures/shell_filters/ls_la.txt",
    ):
        assert path in result.output


def test_unknown_command_passthrough() -> None:
    raw = "alpha\nbeta\n"
    result = apply("python script.py", raw)
    assert not result.applied
    assert result.output == raw


def test_alias_and_compound_commands_passthrough() -> None:
    raw = _fixture("git_status.txt")
    assert not apply("gs", raw).applied
    assert not apply("git status && echo done", raw).applied


def test_tiny_output_passthrough() -> None:
    raw = "On branch main\nnothing to commit, working tree clean\n"
    result = apply("git status", raw)
    assert not result.applied
    assert result.output == raw


def test_config_disables_filters() -> None:
    config = Config()
    config.rtk_lite.enabled = False
    raw = _fixture("git_status.txt")
    result = apply("git status", raw, config=config)
    assert not result.applied
    assert result.output == raw


def test_git_diff_stat_filter_preserves_paths() -> None:
    raw = _fixture("git_diff_stat.txt")
    result = apply("git diff --stat", raw)
    assert result.applied
    assert "poor-cli/config.py" in result.output
    assert "poor-cli/shell_filters/__init__.py" in result.output
    assert "4 files changed" in result.output


def test_ls_la_filter_preserves_names() -> None:
    raw = _fixture("ls_la.txt")
    result = apply("ls -la", raw)
    assert result.applied
    assert "README.md" in result.output
    assert "current -> poor-cli" in result.output


def test_shell_filter_failure_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    import poor_cli.shell_filters as shell_filters

    def boom(_: str) -> str:
        raise ValueError("boom")

    monkeypatch.setitem(shell_filters.REGISTRY, ("git", "status"), boom)
    raw = _fixture("git_status.txt")
    result = shell_filters.apply("git status", raw)
    assert not result.applied
    assert result.output == raw


def test_bash_tool_reports_reduction_in_meta_and_savings() -> None:
    registry = ToolRegistryAsync()
    tracker = EconomySavingsTracker()
    registry._core = SimpleNamespace(config=Config(), _economy_tracker=tracker)
    result = registry._filter_bash_output("git status", _fixture("git_status.txt"))
    assert isinstance(result, FilteredToolResult)
    meta = PoorCLICore._tool_result_filter_metadata(registry._core, result)
    assert meta["rtk_reduction_pct"] is not None
    assert registry.get_output_filter_stats()["tokens_saved"] > 0
    assert tracker.get_summary()["tokens_saved_by_shell_filter"] > 0
