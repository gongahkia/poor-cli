"""
Tests for PoorCLICore - the headless engine.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from types import SimpleNamespace

from poor_cli.tools_async import ToolOutcome


@pytest.fixture
def mock_config():
    """Create a mock config object."""
    config = MagicMock()
    config.model.provider = "gemini"
    config.model.model_name = "gemini-pro"
    config.model.providers = {"gemini": MagicMock(default_model="gemini-pro")}
    config.checkpoint.enabled = False
    config.history.auto_save = False
    return config


@pytest.fixture
def mock_provider():
    """Create a mock provider."""
    provider = AsyncMock()
    provider.capabilities = MagicMock(
        supports_streaming=True,
        supports_function_calling=True,
        supports_vision=False
    )
    provider.initialize = AsyncMock()
    provider.send_message = AsyncMock()
    provider.send_message_stream = AsyncMock()
    provider.clear_history = AsyncMock()
    provider.get_history = MagicMock(return_value=[])
    return provider


@pytest.fixture
def mock_tool_registry():
    """Create a mock tool registry."""
    registry = AsyncMock()
    registry.get_tool_declarations = MagicMock(return_value=[
        {"name": "read_file", "description": "Read a file"},
        {"name": "write_file", "description": "Write a file"},
    ])
    registry.execute_tool = AsyncMock(return_value="Tool executed")
    registry.execute_tool_raw = AsyncMock(return_value="Tool executed")
    registry.inspect_mutation_targets = MagicMock(return_value=[])
    return registry


class TestPoorCLICoreInit:
    """Test PoorCLICore initialization."""
    
    def test_create_instance(self):
        """Test creating a PoorCLICore instance."""
        from poor_cli.core import PoorCLICore
        
        core = PoorCLICore()
        
        assert core.provider is None
        assert core.tool_registry is None
        assert core.config is None
        assert not core._initialized
    
    def test_create_instance_with_config_path(self, tmp_path):
        """Test creating instance with custom config path."""
        from poor_cli.core import PoorCLICore
        
        config_path = tmp_path / "config.yaml"
        core = PoorCLICore(config_path=config_path)
        
        assert core._config_path == config_path

    def test_create_instance_with_history_adapter(self):
        """Test injecting a custom history adapter."""
        from poor_cli.core import PoorCLICore

        adapter = MagicMock()
        core = PoorCLICore(history_adapter=adapter)

        assert core.history_adapter is adapter


class TestPoorCLICoreNotInitialized:
    """Test error handling when core is not initialized."""
    
    @pytest.mark.asyncio
    async def test_send_message_raises_error(self):
        """Test that send_message raises error when not initialized."""
        from poor_cli.core import PoorCLICore
        from poor_cli.exceptions import PoorCLIError
        
        core = PoorCLICore()
        
        with pytest.raises(PoorCLIError, match="not initialized"):
            async for _ in core.send_message("test"):
                pass
    
    @pytest.mark.asyncio
    async def test_send_message_sync_raises_error(self):
        """Test that send_message_sync raises error when not initialized."""
        from poor_cli.core import PoorCLICore
        from poor_cli.exceptions import PoorCLIError
        
        core = PoorCLICore()
        
        with pytest.raises(PoorCLIError, match="not initialized"):
            await core.send_message_sync("test")
    
    @pytest.mark.asyncio
    async def test_execute_tool_raises_error(self):
        """Test that execute_tool raises error when not initialized."""
        from poor_cli.core import PoorCLICore
        from poor_cli.exceptions import PoorCLIError
        
        core = PoorCLICore()
        
        with pytest.raises(PoorCLIError, match="not initialized"):
            await core.execute_tool("test", {})


class TestPoorCLICoreWithMocks:
    """Test PoorCLICore with mocked dependencies."""
    
    @pytest.fixture
    def core_with_mocks(self, mock_config, mock_provider, mock_tool_registry):
        """Create a PoorCLICore with mocked dependencies."""
        from poor_cli.core import PoorCLICore
        
        core = PoorCLICore()
        core.provider = mock_provider
        core.tool_registry = mock_tool_registry
        core.config = mock_config
        core._initialized = True
        core._config_manager = MagicMock()
        core._context_manager = MagicMock()
        
        return core
    
    @pytest.mark.asyncio
    async def test_execute_tool(self, core_with_mocks):
        """Test executing a tool."""
        outcome = ToolOutcome(
            ok=True,
            operation="write_file",
            path="/tmp/test.py",
            changed=True,
            diff="--- /tmp/test.py\n+++ /tmp/test.py\n",
            message="Created /tmp/test.py",
        )
        core_with_mocks.tool_registry.execute_tool_raw = AsyncMock(return_value=outcome)

        result = await core_with_mocks.execute_tool(
            "write_file", {"file_path": "/tmp/test.py"}
        )

        core_with_mocks.tool_registry.execute_tool_raw.assert_awaited_once_with(
            "write_file", {"file_path": "/tmp/test.py"}
        )
        payload = json.loads(result)
        assert payload["operation"] == "write_file"
        assert payload["path"] == "/tmp/test.py"
        assert payload["changed"] is True

    @pytest.mark.asyncio
    async def test_execute_tool_raw_preserves_tool_outcome(self, core_with_mocks):
        outcome = ToolOutcome(
            ok=True,
            operation="edit_file",
            path="/tmp/test.py",
            changed=True,
            diff="--- /tmp/test.py\n+++ /tmp/test.py\n",
            message="Edited /tmp/test.py",
        )
        core_with_mocks.tool_registry.execute_tool_raw = AsyncMock(return_value=outcome)

        result = await core_with_mocks.execute_tool_raw(
            "edit_file",
            {"file_path": "/tmp/test.py", "old_text": "a", "new_text": "b"},
        )

        assert result is outcome
    
    def test_get_available_tools(self, core_with_mocks):
        """Test getting available tools."""
        tools = core_with_mocks.get_available_tools()
        
        assert len(tools) == 2
        assert tools[0]["name"] == "read_file"
        assert tools[1]["name"] == "write_file"
    
    def test_get_provider_info(self, core_with_mocks):
        """Test getting provider info."""
        info = core_with_mocks.get_provider_info()
        
        assert info["name"] == "gemini"
        assert info["model"] == "gemini-pro"
        assert "capabilities" in info
        assert info["supported_clients"] == ["cli", "neovim"]
    
    @pytest.mark.asyncio
    async def test_clear_history(self, core_with_mocks):
        """Test clearing history."""
        core_with_mocks.history_adapter = MagicMock()
        await core_with_mocks.clear_history()
        
        core_with_mocks.provider.clear_history.assert_called_once()
        core_with_mocks.history_adapter.clear_history.assert_called_once()
    
    def test_get_history_empty(self, core_with_mocks):
        """Test getting empty history."""
        history = core_with_mocks.get_history()
        
        assert history == []
    
    def test_set_system_instruction(self, core_with_mocks):
        """Test setting system instruction."""
        core_with_mocks.set_system_instruction("You are a helpful assistant.")
        
        assert core_with_mocks._system_instruction == "You are a helpful assistant."
    
    def test_permission_callback_property(self, core_with_mocks):
        """Test permission callback property."""
        callback = MagicMock()
        
        core_with_mocks.permission_callback = callback
        
        assert core_with_mocks.permission_callback == callback

    @pytest.mark.asyncio
    async def test_create_checkpoint_uses_thread_offload(self, core_with_mocks):
        from poor_cli.core import PoorCLICore

        checkpoint = MagicMock()
        checkpoint.checkpoint_id = "cp_123"
        checkpoint.created_at = "2026-03-14T10:00:00"
        checkpoint.description = "Manual checkpoint"
        checkpoint.operation_type = "manual"
        checkpoint.tags = ["manual"]
        checkpoint.get_file_count.return_value = 2
        checkpoint.get_total_size.return_value = 128

        manager = MagicMock()
        manager.create_checkpoint.return_value = checkpoint
        core_with_mocks.checkpoint_manager = manager

        with patch("poor_cli.core.asyncio.to_thread", new=AsyncMock(return_value=checkpoint)) as mock_to_thread:
            payload = await core_with_mocks.create_checkpoint(
                ["/tmp/a.py", "/tmp/b.py"],
                "Manual checkpoint",
            )

        mock_to_thread.assert_awaited_once_with(
            manager.create_checkpoint,
            ["/tmp/a.py", "/tmp/b.py"],
            "Manual checkpoint",
        )
        assert payload == {
            "checkpoint_id": "cp_123",
            "created_at": "2026-03-14T10:00:00",
            "description": "Manual checkpoint",
            "operation_type": "manual",
            "file_count": 2,
            "total_size_bytes": 128,
            "tags": ["manual"],
        }

    @pytest.mark.asyncio
    async def test_restore_checkpoint_uses_thread_offload(self, core_with_mocks):
        checkpoint = MagicMock()
        checkpoint.checkpoint_id = "cp_123"
        checkpoint.created_at = "2026-03-14T10:00:00"
        checkpoint.description = "Manual checkpoint"
        checkpoint.operation_type = "manual"
        checkpoint.tags = ["manual"]
        checkpoint.get_file_count.return_value = 2
        checkpoint.get_total_size.return_value = 128

        manager = MagicMock()
        manager.get_checkpoint.return_value = checkpoint
        core_with_mocks.checkpoint_manager = manager

        with patch("poor_cli.core.asyncio.to_thread", new=AsyncMock(return_value=2)) as mock_to_thread:
            payload = await core_with_mocks.restore_checkpoint("cp_123")

        mock_to_thread.assert_awaited_once_with(manager.restore_checkpoint, "cp_123")
        assert payload == {
            "checkpoint_id": "cp_123",
            "created_at": "2026-03-14T10:00:00",
            "description": "Manual checkpoint",
            "operation_type": "manual",
            "file_count": 2,
            "total_size_bytes": 128,
            "tags": ["manual"],
            "restored_files": 2,
        }

    @pytest.mark.asyncio
    async def test_apply_edit_outcome_uses_structured_tool_result(self, core_with_mocks):
        outcome = ToolOutcome(
            ok=True,
            operation="edit_file",
            path="/tmp/demo.py",
            changed=True,
            diff="--- /tmp/demo.py\n+++ /tmp/demo.py\n",
            checkpoint_id="cp_123",
            message="Edited /tmp/demo.py",
        )
        core_with_mocks.tool_registry.execute_tool_raw = AsyncMock(return_value=outcome)

        result = await core_with_mocks.apply_edit_outcome(
            file_path="/tmp/demo.py",
            old_text="old",
            new_text="new",
        )

        assert result is outcome
        core_with_mocks.tool_registry.execute_tool_raw.assert_awaited_once_with(
            "edit_file",
            {"file_path": "/tmp/demo.py", "old_text": "old", "new_text": "new"},
        )

    @pytest.mark.asyncio
    async def test_send_message_sync_uses_shared_context_builder(self, core_with_mocks):
        core_with_mocks.provider.send_message = AsyncMock(
            return_value=SimpleNamespace(content="done", function_calls=[], metadata={})
        )
        core_with_mocks._build_context_message = AsyncMock(return_value="context prompt")

        result = await core_with_mocks.send_message_sync(
            "review this",
            context_files=["/tmp/a.py"],
            pinned_context_files=["/tmp/b.py"],
            context_budget_tokens=3200,
        )

        core_with_mocks._build_context_message.assert_awaited_once_with(
            "review this",
            context_files=["/tmp/a.py"],
            pinned_context_files=["/tmp/b.py"],
            context_budget_tokens=3200,
        )
        core_with_mocks.provider.send_message.assert_awaited_once_with("context prompt")
        assert "done" in result

    @pytest.mark.asyncio
    async def test_send_message_events_uses_shared_context_builder(self, core_with_mocks):
        async def fake_stream(_message):
            yield SimpleNamespace(content="chunk", function_calls=None, metadata={})

        core_with_mocks.provider.send_message_stream = fake_stream
        core_with_mocks._build_context_message = AsyncMock(return_value="context prompt")

        events = [
            event
            async for event in core_with_mocks.send_message_events(
                "review this",
                context_files=["/tmp/a.py"],
                pinned_context_files=["/tmp/b.py"],
                context_budget_tokens=2048,
                request_id="req-1",
            )
        ]

        core_with_mocks._build_context_message.assert_awaited_once_with(
            "review this",
            context_files=["/tmp/a.py"],
            pinned_context_files=["/tmp/b.py"],
            context_budget_tokens=2048,
        )
        assert any(event.type == "text_chunk" for event in events)

    @pytest.mark.asyncio
    async def test_preview_context_passes_paths_and_budget_to_context_manager(self, core_with_mocks):
        core_with_mocks._context_manager.preview_context = AsyncMock(
            return_value={"files": [], "totalTokens": 0, "truncated": False, "message": "ok"}
        )

        result = await core_with_mocks.preview_context(
            message="inspect",
            context_files=["/tmp/a.py"],
            pinned_context_files=["/tmp/b.py"],
            context_budget_tokens=4096,
        )

        assert result["message"] == "ok"
        core_with_mocks._context_manager.preview_context.assert_awaited_once_with(
            message="inspect",
            explicit_files=["/tmp/a.py"],
            pinned_files=["/tmp/b.py"],
            repo_root=str(Path.cwd()),
            max_tokens=4096,
            max_files=12,
        )

    @pytest.mark.asyncio
    async def test_preview_mutation_uses_tool_registry_preview(self, core_with_mocks):
        core_with_mocks.tool_registry.preview_mutation = AsyncMock(
            return_value=ToolOutcome(
                ok=True,
                operation="edit_file",
                path="/tmp/demo.py",
                changed=True,
                diff="--- /tmp/demo.py\n+++ /tmp/demo.py\n",
                message="Preview edit /tmp/demo.py",
                metadata={"changed_paths": ["/tmp/demo.py"], "preview": True},
            )
        )

        result = await core_with_mocks.preview_mutation(
            "edit_file",
            {"file_path": "/tmp/demo.py", "old_text": "old", "new_text": "new"},
        )

        core_with_mocks.tool_registry.preview_mutation.assert_awaited_once_with(
            "edit_file",
            {"file_path": "/tmp/demo.py", "old_text": "old", "new_text": "new"},
        )
        assert result["operation"] == "edit_file"
        assert result["paths"] == ["/tmp/demo.py"]
        assert result["changed"] is True
        assert result["diff"].startswith("--- /tmp/demo.py")

    @pytest.mark.asyncio
    async def test_streaming_tool_events_use_real_tool_outcome_diff(self, core_with_mocks):
        outcome = ToolOutcome(
            ok=True,
            operation="edit_file",
            path="/tmp/demo.py",
            changed=True,
            diff="--- /tmp/demo.py\n+++ /tmp/demo.py\n@@ -1 +1 @@\n-old\n+new\n",
            message="Edited /tmp/demo.py",
        )
        core_with_mocks.provider.format_tool_results = MagicMock(return_value="formatted")
        core_with_mocks.tool_registry.execute_tool_raw = AsyncMock(return_value=outcome)

        response = SimpleNamespace(
            function_calls=[
                SimpleNamespace(
                    id="call-1",
                    name="edit_file",
                    arguments={
                        "file_path": "/tmp/demo.py",
                        "old_text": "old",
                        "new_text": "new",
                    },
                )
            ]
        )

        result = await core_with_mocks._handle_function_calls_events(
            response,
            iteration=1,
            max_iterations=5,
            request_id="req-1",
        )

        assert result == "formatted"
        tool_event = next(
            event for event in core_with_mocks._pending_events if event.type == "tool_result"
        )
        assert tool_event.data["diff"].startswith("--- /tmp/demo.py")
        assert tool_event.data["paths"] == ["/tmp/demo.py"]
        assert tool_event.data["changed"] is True

    @pytest.mark.asyncio
    async def test_permission_callback_receives_preview_payload_for_mutations(self, core_with_mocks):
        preview = ToolOutcome(
            ok=True,
            operation="edit_file",
            path="/tmp/demo.py",
            changed=True,
            diff="--- /tmp/demo.py\n+++ /tmp/demo.py\n",
            message="Preview edit /tmp/demo.py",
            metadata={"changed_paths": ["/tmp/demo.py"], "preview": True},
        )
        core_with_mocks.provider.format_tool_results = MagicMock(return_value="formatted")
        core_with_mocks.tool_registry.preview_mutation = AsyncMock(return_value=preview)
        core_with_mocks.permission_callback = AsyncMock(return_value=False)

        response = SimpleNamespace(
            function_calls=[
                SimpleNamespace(
                    id="call-1",
                    name="edit_file",
                    arguments={
                        "file_path": "/tmp/demo.py",
                        "old_text": "old",
                        "new_text": "new",
                    },
                )
            ]
        )

        result = await core_with_mocks._handle_function_calls_events(
            response,
            iteration=1,
            max_iterations=5,
            request_id="req-1",
        )

        assert result == "formatted"
        core_with_mocks.permission_callback.assert_awaited_once()
        preview_payload = core_with_mocks.permission_callback.await_args.args[2]
        assert preview_payload["requestId"] == "req-1"
        assert preview_payload["paths"] == ["/tmp/demo.py"]
        assert preview_payload["diff"].startswith("--- /tmp/demo.py")

    @pytest.mark.asyncio
    async def test_permission_callback_can_scope_patch_execution_to_selected_paths(self, core_with_mocks):
        preview = ToolOutcome(
            ok=True,
            operation="apply_patch_unified",
            path="/tmp",
            changed=True,
            diff="--- a/demo.py\n+++ b/demo.py\n",
            message="Patch preview ready",
            metadata={
                "paths": ["/tmp/demo.py", "/tmp/other.py"],
                "changed_paths": ["/tmp/demo.py", "/tmp/other.py"],
                "preview": True,
            },
        )
        outcome = ToolOutcome(
            ok=True,
            operation="apply_patch_unified",
            path="/tmp",
            changed=True,
            diff="--- /tmp/other.py\n+++ /tmp/other.py\n",
            message="Patch applied successfully",
            metadata={"changed_paths": ["/tmp/other.py"]},
        )
        core_with_mocks.provider.format_tool_results = MagicMock(return_value="formatted")
        core_with_mocks.tool_registry.preview_mutation = AsyncMock(return_value=preview)
        core_with_mocks.tool_registry.execute_tool_raw = AsyncMock(return_value=outcome)
        core_with_mocks.tool_registry.narrow_mutation_arguments = MagicMock(
            return_value={"patch": "filtered patch", "path": "/tmp"}
        )
        core_with_mocks.tool_registry.inspect_mutation_targets = MagicMock(
            side_effect=[
                ["/tmp/demo.py", "/tmp/other.py"],
                ["/tmp/other.py"],
                ["/tmp/other.py"],
            ]
        )
        core_with_mocks.permission_callback = AsyncMock(
            return_value={"allowed": True, "approvedPaths": ["/tmp/other.py"]}
        )

        response = SimpleNamespace(
            function_calls=[
                SimpleNamespace(
                    id="call-1",
                    name="apply_patch_unified",
                    arguments={
                        "patch": "full patch",
                        "path": "/tmp",
                    },
                )
            ]
        )

        result = await core_with_mocks._handle_function_calls_events(
            response,
            iteration=1,
            max_iterations=5,
            request_id="req-1",
        )

        assert result == "formatted"
        core_with_mocks.tool_registry.narrow_mutation_arguments.assert_called_once_with(
            "apply_patch_unified",
            {"patch": "full patch", "path": "/tmp"},
            ["/tmp/other.py"],
            [],
        )
        core_with_mocks.tool_registry.execute_tool_raw.assert_awaited_once_with(
            "apply_patch_unified",
            {"patch": "filtered patch", "path": "/tmp"},
        )

    @pytest.mark.asyncio
    async def test_permission_callback_can_scope_patch_execution_to_selected_hunks(self, core_with_mocks):
        preview = ToolOutcome(
            ok=True,
            operation="apply_patch_unified",
            path="/tmp",
            changed=True,
            diff="--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-old\n+new\n",
            message="Patch preview ready",
            metadata={
                "paths": ["/tmp/demo.py"],
                "changed_paths": ["/tmp/demo.py"],
                "preview": True,
            },
        )
        outcome = ToolOutcome(
            ok=True,
            operation="apply_patch_unified",
            path="/tmp",
            changed=True,
            diff="--- /tmp/demo.py\n+++ /tmp/demo.py\n@@ -4 +4 @@\n-old\n+new\n",
            message="Patch applied successfully",
            metadata={"changed_paths": ["/tmp/demo.py"]},
        )
        core_with_mocks.provider.format_tool_results = MagicMock(return_value="formatted")
        core_with_mocks.tool_registry.preview_mutation = AsyncMock(return_value=preview)
        core_with_mocks.tool_registry.execute_tool_raw = AsyncMock(return_value=outcome)
        core_with_mocks.tool_registry.narrow_mutation_arguments = MagicMock(
            return_value={"patch": "filtered hunk patch", "path": "/tmp"}
        )
        core_with_mocks.tool_registry.inspect_mutation_targets = MagicMock(
            side_effect=[
                ["/tmp/demo.py"],
                ["/tmp/demo.py"],
            ]
        )
        core_with_mocks.permission_callback = AsyncMock(
            return_value={
                "allowed": True,
                "approvedChunks": [{"path": "/tmp/demo.py", "index": 1}],
            }
        )

        response = SimpleNamespace(
            function_calls=[
                SimpleNamespace(
                    id="call-1",
                    name="apply_patch_unified",
                    arguments={
                        "patch": "full patch",
                        "path": "/tmp",
                    },
                )
            ]
        )

        result = await core_with_mocks._handle_function_calls_events(
            response,
            iteration=1,
            max_iterations=5,
            request_id="req-1",
        )

        assert result == "formatted"
        core_with_mocks.tool_registry.narrow_mutation_arguments.assert_called_once_with(
            "apply_patch_unified",
            {"patch": "full patch", "path": "/tmp"},
            [],
            [{"path": "/tmp/demo.py", "index": 1}],
        )
        core_with_mocks.tool_registry.execute_tool_raw.assert_awaited_once_with(
            "apply_patch_unified",
            {"patch": "filtered hunk patch", "path": "/tmp"},
        )


class TestBuildFimPrompt:
    """Test FIM prompt building."""
    
    def test_build_fim_prompt_basic(self):
        """Test building a basic FIM prompt."""
        from poor_cli.core import PoorCLICore
        
        core = PoorCLICore()
        core.config = MagicMock()
        core.config.model.model_name = "generic"
        
        prompt = core.build_fim_prompt(
            code_before="def hello():\n    print(",
            code_after=")\n",
            instruction="",
            file_path="test.py",
            language="python"
        )
        
        assert "test.py" in prompt or "python" in prompt.lower()
        assert "print(" in prompt
    
    def test_build_fim_prompt_with_instruction(self):
        """Test FIM prompt with custom instruction."""
        from poor_cli.core import PoorCLICore
        
        core = PoorCLICore()
        core.config = MagicMock()
        core.config.model.model_name = "generic"
        
        prompt = core.build_fim_prompt(
            code_before="",
            code_after="",
            instruction="Generate a greeting",
            file_path="test.py",
            language="python"
        )
        
        assert "greeting" in prompt.lower() or "Generate" in prompt


class TestConfidenceOutput:
    """Test confidence score normalization for chat responses."""

    def test_ensure_confidence_line_appends_default_when_missing(self):
        from poor_cli.core import PoorCLICore

        core = PoorCLICore()
        final_text, appended = core._ensure_confidence_line("Here is the fix.")

        assert "Here is the fix." in final_text
        assert appended == "\n\nConfidence: Moderate (50%)"
        assert final_text.endswith("Confidence: Moderate (50%)")

    def test_ensure_confidence_line_uses_model_reported_percentage(self):
        from poor_cli.core import PoorCLICore

        core = PoorCLICore()
        final_text, appended = core._ensure_confidence_line(
            "Applied changes with confidence 88% after validation."
        )

        assert appended == "\n\nConfidence: Very High (88%)"
        assert final_text.endswith("Confidence: Very High (88%)")

    def test_ensure_confidence_line_avoids_duplicate_when_already_normalized(self):
        from poor_cli.core import PoorCLICore

        core = PoorCLICore()
        response = "Done.\n\nConfidence: High (73%)"
        final_text, appended = core._ensure_confidence_line(response)

        assert appended == ""
        assert final_text == response

    def test_ensure_confidence_line_avoids_duplicate_when_trailing_confidence_exists(self):
        from poor_cli.core import PoorCLICore

        core = PoorCLICore()
        response = "Applied updates.\n\nConfidence: Very High (81-100%)"
        final_text, appended = core._ensure_confidence_line(response)

        assert appended == ""
        assert final_text == response
