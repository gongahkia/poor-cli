from pathlib import Path

from poor_cli.core import PoorCLICore
from poor_cli.core_agent_loop import AgentLoop
from poor_cli.core_tool_dispatch import ToolDispatcher
from poor_cli.core_turn_lifecycle import TurnLifecycle


ROOT = Path(__file__).resolve().parents[1]


def test_agent_loop_importable() -> None:
    assert hasattr(AgentLoop, "send_message_events")
    assert hasattr(AgentLoop, "send_message")


def test_tool_dispatch_importable() -> None:
    assert hasattr(ToolDispatcher, "execute_tool")
    assert hasattr(ToolDispatcher, "_execute_tool_internal")


def test_turn_lifecycle_importable() -> None:
    assert hasattr(TurnLifecycle, "build_status_view")
    assert hasattr(TurnLifecycle, "create_checkpoint")


def test_core_py_under_3000_lines() -> None:
    assert len((ROOT / "poor_cli" / "core.py").read_text(encoding="utf-8").splitlines()) <= 3000


def test_poor_cli_core_public_surface_unchanged() -> None:
    expected = {
        "send_message_events",
        "send_message",
        "send_message_sync",
        "execute_tool",
        "execute_tool_raw",
        "build_status_view",
        "create_checkpoint",
        "restore_checkpoint",
        "switch_provider",
    }
    assert expected <= set(dir(PoorCLICore))
