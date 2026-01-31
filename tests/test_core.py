"""
Tests for PoorCLICore - the headless engine.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


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
        result = await core_with_mocks.execute_tool("read_file", {"path": "test.py"})
        
        core_with_mocks.tool_registry.execute_tool.assert_called_once_with(
            "read_file", {"path": "test.py"}
        )
        assert result == "Tool executed"
    
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
    
    @pytest.mark.asyncio
    async def test_clear_history(self, core_with_mocks):
        """Test clearing history."""
        await core_with_mocks.clear_history()
        
        core_with_mocks.provider.clear_history.assert_called_once()
    
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
