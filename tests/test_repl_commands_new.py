from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from poor_cli.repl_commands import handle_slash_command


@pytest.mark.asyncio
async def test_commit_command_generates_and_executes_commit_message():
    repl = SimpleNamespace(
        tool_registry=SimpleNamespace(
            bash=AsyncMock(side_effect=["diff --git a/a.py b/a.py", "Committed"]),
        ),
        provider=SimpleNamespace(
            send_message=AsyncMock(return_value=SimpleNamespace(content="feat: add change")),
        ),
        console=MagicMock(),
    )

    with patch("poor_cli.repl_commands.Confirm.ask", return_value=True):
        await handle_slash_command(repl, "/commit")

    assert repl.tool_registry.bash.await_count == 2
    repl.provider.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_review_command_with_file_uses_read_file():
    repl = SimpleNamespace(
        tool_registry=SimpleNamespace(
            read_file=AsyncMock(return_value="print('hello')"),
            bash=AsyncMock(),
        ),
        process_request=AsyncMock(),
        console=MagicMock(),
    )

    await handle_slash_command(repl, "/review app.py")

    repl.tool_registry.read_file.assert_awaited_once_with(file_path="app.py")
    repl.process_request.assert_awaited_once()
    assert repl.process_request.await_args.kwargs["request_origin"] == "structured_command"


@pytest.mark.asyncio
async def test_test_command_with_file_uses_structured_command_origin():
    repl = SimpleNamespace(
        tool_registry=SimpleNamespace(
            read_file=AsyncMock(return_value="def add(a, b): return a + b"),
        ),
        process_request=AsyncMock(),
        console=MagicMock(),
    )

    await handle_slash_command(repl, "/test calc.py")

    repl.tool_registry.read_file.assert_awaited_once_with(file_path="calc.py")
    repl.process_request.assert_awaited_once()
    assert repl.process_request.await_args.kwargs["request_origin"] == "structured_command"


@pytest.mark.asyncio
async def test_test_command_requires_file_argument():
    repl = SimpleNamespace(console=MagicMock())

    await handle_slash_command(repl, "/test")

    repl.console.print.assert_called_once()


@pytest.mark.asyncio
async def test_broke_command_sets_poor_mode():
    repl = SimpleNamespace(
        response_mode="rich",
        console=MagicMock(),
    )

    await handle_slash_command(repl, "/broke")

    assert repl.response_mode == "poor"
    printed = repl.console.print.call_args.args[0].lower()
    assert "poor" in printed


@pytest.mark.asyncio
async def test_my_treat_command_sets_rich_mode():
    repl = SimpleNamespace(
        response_mode="poor",
        console=MagicMock(),
    )

    await handle_slash_command(repl, "/my-treat")

    assert repl.response_mode == "rich"
    printed = repl.console.print.call_args.args[0].lower()
    assert "rich" in printed


@pytest.mark.asyncio
async def test_image_command_queues_valid_image(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"png")
    repl = SimpleNamespace(
        pending_images=[],
        console=MagicMock(),
    )

    await handle_slash_command(repl, f"/image {image}")

    assert str(image) in repl.pending_images


@pytest.mark.asyncio
async def test_watch_and_unwatch_commands_manage_task(tmp_path):
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    repl = SimpleNamespace(
        console=MagicMock(),
        _watch_task=None,
        process_request=AsyncMock(),
    )

    async def fake_watch_mode(_repl, _directory, _prompt):
        await asyncio.sleep(0.01)

    import asyncio

    with patch("poor_cli.watch.run_watch_mode", side_effect=fake_watch_mode):
        await handle_slash_command(repl, f"/watch {watch_dir}")
        assert repl._watch_task is not None
        await handle_slash_command(repl, "/unwatch")
        assert repl._watch_task is None
