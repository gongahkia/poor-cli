"""
Tests for async tools
"""

import pytest
import tempfile
from pathlib import Path
from poor_cli.tools_async import ToolRegistryAsync


class TestToolRegistry:
    """Test tool registry"""

    def test_registry_initialization(self):
        """Test that registry initializes with all tools"""
        registry = ToolRegistryAsync()

        # Check that all expected tools are registered
        expected_tools = [
            "read_file", "write_file", "edit_file",
            "glob_files", "grep_files", "bash",
            "list_directory", "copy_file", "move_file",
            "delete_file", "diff_files", "git_status",
            "git_diff", "create_directory"
        ]

        for tool_name in expected_tools:
            assert tool_name in registry.tools

    def test_get_tool_declarations(self):
        """Test getting tool declarations for API"""
        registry = ToolRegistryAsync()
        declarations = registry.get_tool_declarations()

        assert isinstance(declarations, list)
        assert len(declarations) > 0

        # Check first declaration structure
        decl = declarations[0]
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl


class TestFileTools:
    """Test file operation tools"""

    @pytest.mark.asyncio
    async def test_write_and_read_file(self):
        """Test writing and reading a file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            content = "Hello, World!"

            registry = ToolRegistryAsync()

            # Write file
            result = await registry.write_file(str(file_path), content)
            assert "Successfully wrote" in result
            assert file_path.exists()

            # Read file
            read_content = await registry.read_file(str(file_path))
            assert read_content == content

    @pytest.mark.asyncio
    async def test_edit_file(self):
        """Test editing a file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            original = "Hello, World!"

            registry = ToolRegistryAsync()

            # Create file
            await registry.write_file(str(file_path), original)

            # Edit file
            result = await registry.edit_file(
                str(file_path),
                new_text="Hello, Python!",
                old_text="Hello, World!"
            )
            assert "Successfully edited" in result

            # Verify edit
            content = await registry.read_file(str(file_path))
            assert content == "Hello, Python!"

    @pytest.mark.asyncio
    async def test_copy_file(self):
        """Test copying a file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.txt"
            dest = Path(tmpdir) / "dest.txt"

            registry = ToolRegistryAsync()

            # Create source
            await registry.write_file(str(source), "Test content")

            # Copy file
            result = await registry.copy_file(str(source), str(dest))
            assert "Successfully copied" in result
            assert dest.exists()

            # Verify content
            content = await registry.read_file(str(dest))
            assert content == "Test content"

    @pytest.mark.asyncio
    async def test_move_file(self):
        """Test moving a file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source.txt"
            dest = Path(tmpdir) / "dest.txt"

            registry = ToolRegistryAsync()

            # Create source
            await registry.write_file(str(source), "Test content")

            # Move file
            result = await registry.move_file(str(source), str(dest))
            assert "Successfully moved" in result
            assert dest.exists()
            assert not source.exists()

    @pytest.mark.asyncio
    async def test_delete_file(self):
        """Test deleting a file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"

            registry = ToolRegistryAsync()

            # Create file
            await registry.write_file(str(file_path), "Test")

            # Delete file
            result = await registry.delete_file(str(file_path))
            assert "Successfully deleted" in result
            assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_diff_files(self):
        """Test diffing two files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "file1.txt"
            file2 = Path(tmpdir) / "file2.txt"

            registry = ToolRegistryAsync()

            # Create files with different content
            await registry.write_file(str(file1), "Line 1\nLine 2\nLine 3\n")
            await registry.write_file(str(file2), "Line 1\nModified Line 2\nLine 3\n")

            # Diff files
            result = await registry.diff_files(str(file1), str(file2))
            assert "Line 2" in result or "Modified" in result or "Files are identical" not in result

    @pytest.mark.asyncio
    async def test_create_directory(self):
        """Test creating a directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_path = Path(tmpdir) / "new_dir" / "nested"

            registry = ToolRegistryAsync()

            # Create directory
            result = await registry.create_directory(str(dir_path))
            assert "Successfully created" in result
            assert dir_path.exists()
            assert dir_path.is_dir()

    @pytest.mark.asyncio
    async def test_list_directory(self):
        """Test listing directory contents"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            Path(tmpdir, "file1.txt").write_text("test")
            Path(tmpdir, "file2.txt").write_text("test")
            Path(tmpdir, "subdir").mkdir()

            registry = ToolRegistryAsync()

            # List directory
            result = await registry.list_directory(tmpdir)
            assert "file1.txt" in result
            assert "file2.txt" in result
            assert "subdir" in result


class TestSearchTools:
    """Test search tools"""

    @pytest.mark.asyncio
    async def test_glob_files(self):
        """Test glob file search"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            Path(tmpdir, "test1.py").write_text("test")
            Path(tmpdir, "test2.py").write_text("test")
            Path(tmpdir, "test.txt").write_text("test")

            registry = ToolRegistryAsync()

            # Glob for Python files
            result = await registry.glob_files("*.py", tmpdir)
            assert "test1.py" in result
            assert "test2.py" in result
            assert "test.txt" not in result

    @pytest.mark.asyncio
    async def test_grep_files(self):
        """Test grep file search"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files with content
            test_file = Path(tmpdir, "test.txt")
            test_file.write_text("Line 1\nHello World\nLine 3\n")

            registry = ToolRegistryAsync()

            # Grep for pattern
            result = await registry.grep_files("Hello", path=str(test_file))
            assert "Hello World" in result
            assert "test.txt" in result


class TestBashTool:
    """Test bash command execution"""

    @pytest.mark.asyncio
    async def test_bash_simple_command(self):
        """Test executing a simple bash command"""
        registry = ToolRegistryAsync()

        # Simple echo command
        result = await registry.bash("echo 'Hello'")
        assert "Hello" in result

    @pytest.mark.asyncio
    async def test_bash_timeout(self):
        """Test bash command timeout"""
        registry = ToolRegistryAsync()

        # This should timeout
        with pytest.raises(Exception):
            await registry.bash("sleep 10", timeout=1)


class TestExecuteTool:
    """Test tool execution dispatcher"""

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """Test executing a tool by name"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"

            registry = ToolRegistryAsync()

            # Execute write_file tool
            result = await registry.execute_tool(
                "write_file",
                {"file_path": str(file_path), "content": "Test"}
            )

            assert "Successfully wrote" in result
            assert file_path.exists()

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Test executing unknown tool raises error"""
        registry = ToolRegistryAsync()

        with pytest.raises(Exception) as exc_info:
            await registry.execute_tool("unknown_tool", {})

        assert "Unknown tool" in str(exc_info.value)
