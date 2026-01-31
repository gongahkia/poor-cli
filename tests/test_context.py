"""
Tests for context module.
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from poor_cli.context import (
    ContextManager,
    FileContext,
    ContextResult,
    get_context_manager,
    CHARS_PER_TOKEN,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        (Path(tmpdir) / "main.py").write_text("""
import utils
from helper import process

def main():
    data = utils.load()
    result = process(data)
    return result
""")
        
        (Path(tmpdir) / "utils.py").write_text("""
def load():
    return {"key": "value"}

def save(data):
    pass
""")
        
        (Path(tmpdir) / "helper.py").write_text("""
def process(data):
    return data
""")
        
        (Path(tmpdir) / "test.js").write_text("""
import { helper } from './helper';
const result = helper.run();
""")
        
        yield tmpdir


@pytest.fixture
def context_manager():
    """Create a fresh ContextManager instance."""
    return ContextManager(
        max_tokens=1000,
        max_files=5,
        max_file_size=10000,
        cache_ttl=60
    )


class TestFileContext:
    """Test FileContext dataclass."""
    
    def test_tokens_estimate(self):
        """Test token estimation."""
        content = "a" * 400  # 400 chars
        
        ctx = FileContext(
            path="/test.py",
            content=content,
            size=400,
            modified_time=0,
            language="python"
        )
        
        expected_tokens = 400 // CHARS_PER_TOKEN
        assert ctx.tokens_estimate == expected_tokens


class TestContextManager:
    """Test ContextManager class."""
    
    def test_init_defaults(self):
        """Test initialization with defaults."""
        cm = ContextManager()
        
        assert cm.max_tokens > 0
        assert cm.max_files > 0
        assert cm.max_file_size > 0
        assert cm.cache_ttl > 0
    
    def test_detect_language_python(self, context_manager):
        """Test language detection for Python."""
        lang = context_manager._detect_language("/path/to/file.py")
        assert lang == "python"
    
    def test_detect_language_javascript(self, context_manager):
        """Test language detection for JavaScript."""
        lang = context_manager._detect_language("/path/to/file.js")
        assert lang == "javascript"
    
    def test_detect_language_typescript(self, context_manager):
        """Test language detection for TypeScript."""
        lang = context_manager._detect_language("/path/to/file.ts")
        assert lang == "typescript"
    
    def test_detect_language_unknown(self, context_manager):
        """Test language detection for unknown extension."""
        lang = context_manager._detect_language("/path/to/file.xyz")
        assert lang == "text"
    
    def test_is_binary_true(self, context_manager):
        """Test binary file detection."""
        assert context_manager._is_binary("/test.png")
        assert context_manager._is_binary("/test.jpg")
        assert context_manager._is_binary("/test.exe")
        assert context_manager._is_binary("/test.zip")
    
    def test_is_binary_false(self, context_manager):
        """Test non-binary file detection."""
        assert not context_manager._is_binary("/test.py")
        assert not context_manager._is_binary("/test.js")
        assert not context_manager._is_binary("/test.md")
    
    def test_mark_file_edited(self, context_manager):
        """Test marking file as recently edited."""
        context_manager.mark_file_edited("/path/to/file.py")
        
        resolved = str(Path("/path/to/file.py").resolve())
        assert resolved in context_manager._recent_edits
    
    def test_clear_cache(self, context_manager):
        """Test cache clearing."""
        context_manager._cache["test"] = ("content", 0)
        
        context_manager.clear_cache()
        
        assert len(context_manager._cache) == 0


class TestContextManagerGather:
    """Test context gathering functionality."""
    
    @pytest.mark.asyncio
    async def test_gather_single_file(self, context_manager, temp_dir):
        """Test gathering context from a single file."""
        main_path = os.path.join(temp_dir, "main.py")
        
        result = await context_manager.gather_context(
            primary_file=main_path,
            include_imports=False
        )
        
        assert isinstance(result, ContextResult)
        assert len(result.files) >= 1
        assert result.files[0].path == str(Path(main_path).resolve())
    
    @pytest.mark.asyncio
    async def test_gather_with_imports(self, context_manager, temp_dir):
        """Test gathering context including imports."""
        main_path = os.path.join(temp_dir, "main.py")
        
        result = await context_manager.gather_context(
            primary_file=main_path,
            working_directory=temp_dir,
            include_imports=True
        )
        
        # Should include main.py and potentially utils.py, helper.py
        assert len(result.files) >= 1
    
    @pytest.mark.asyncio
    async def test_gather_with_additional_files(self, context_manager, temp_dir):
        """Test gathering context with additional files."""
        main_path = os.path.join(temp_dir, "main.py")
        utils_path = os.path.join(temp_dir, "utils.py")
        
        result = await context_manager.gather_context(
            primary_file=main_path,
            additional_files=[utils_path],
            include_imports=False
        )
        
        paths = [f.path for f in result.files]
        assert str(Path(main_path).resolve()) in paths
        assert str(Path(utils_path).resolve()) in paths
    
    @pytest.mark.asyncio
    async def test_gather_respects_token_limit(self, temp_dir):
        """Test that gathering respects token limits."""
        # Create a context manager with very low token limit
        cm = ContextManager(max_tokens=50, max_files=10)
        
        main_path = os.path.join(temp_dir, "main.py")
        result = await cm.gather_context(primary_file=main_path)
        
        assert result.total_tokens <= 50 or result.truncated
    
    @pytest.mark.asyncio
    async def test_gather_nonexistent_file(self, context_manager):
        """Test gathering context for nonexistent file."""
        result = await context_manager.gather_context(
            primary_file="/nonexistent/path/file.py"
        )
        
        assert len(result.files) == 0


class TestContextManagerFormat:
    """Test context formatting."""
    
    def test_format_empty_context(self, context_manager):
        """Test formatting empty context."""
        result = ContextResult(
            files=[],
            total_tokens=0,
            truncated=False,
            message="No files"
        )
        
        formatted = context_manager.format_context_for_prompt(result)
        
        assert formatted == ""
    
    def test_format_with_files(self, context_manager):
        """Test formatting context with files."""
        files = [
            FileContext(
                path="/test.py",
                content="print('hello')",
                size=15,
                modified_time=0,
                language="python"
            )
        ]
        result = ContextResult(
            files=files,
            total_tokens=10,
            truncated=False,
            message="1 file"
        )
        
        formatted = context_manager.format_context_for_prompt(result)
        
        assert "```python" in formatted
        assert "print('hello')" in formatted
        assert "/test.py" in formatted


class TestGetContextManager:
    """Test singleton context manager."""
    
    def test_returns_instance(self):
        """Test that get_context_manager returns an instance."""
        cm = get_context_manager()
        
        assert isinstance(cm, ContextManager)
    
    def test_returns_same_instance(self):
        """Test that get_context_manager returns the same instance."""
        cm1 = get_context_manager()
        cm2 = get_context_manager()
        
        assert cm1 is cm2
