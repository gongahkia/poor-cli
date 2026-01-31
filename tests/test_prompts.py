"""
Tests for prompts module.
"""

import pytest
from poor_cli.prompts import (
    build_fim_prompt,
    get_system_instruction,
    format_prompt,
    FIM_TEMPLATE,
    FIM_CODESTRAL,
    FIM_STARCODER,
    FIM_DEEPSEEK,
    SYSTEM_INSTRUCTION_CHAT,
    SYSTEM_INSTRUCTION_INLINE,
    PROMPT_EXPLAIN_CODE,
)


class TestBuildFimPrompt:
    """Test FIM prompt building."""
    
    def test_generic_provider(self):
        """Test generic FIM prompt format."""
        prompt = build_fim_prompt(
            code_before="def hello():\n    ",
            code_after="\n\nhello()",
            instruction="complete the function",
            filename="test.py",
            language="python",
            provider="generic"
        )
        
        assert "def hello():" in prompt
        assert "hello()" in prompt
        assert "test.py" in prompt
        assert "python" in prompt
    
    def test_codestral_provider(self):
        """Test Codestral native FIM format."""
        prompt = build_fim_prompt(
            code_before="prefix",
            code_after="suffix",
            provider="codestral"
        )
        
        assert "<|fim_prefix|>prefix" in prompt
        assert "<|fim_suffix|>suffix" in prompt
        assert "<|fim_middle|>" in prompt
    
    def test_mistral_provider(self):
        """Test Mistral uses Codestral format."""
        prompt = build_fim_prompt(
            code_before="before",
            code_after="after",
            provider="mistral-codestral-latest"
        )
        
        assert "<|fim_prefix|>" in prompt
        assert "<|fim_suffix|>" in prompt
    
    def test_starcoder_provider(self):
        """Test StarCoder native FIM format."""
        prompt = build_fim_prompt(
            code_before="prefix",
            code_after="suffix",
            provider="starcoder"
        )
        
        assert "<fim_prefix>prefix" in prompt
        assert "<fim_suffix>suffix" in prompt
        assert "<fim_middle>" in prompt
    
    def test_deepseek_provider(self):
        """Test DeepSeek native FIM format."""
        prompt = build_fim_prompt(
            code_before="prefix",
            code_after="suffix",
            provider="deepseek-coder"
        )
        
        assert "<|fim▁begin|>prefix" in prompt
        assert "<|fim▁hole|>suffix" in prompt
        assert "<|fim▁end|>" in prompt
    
    def test_instruction_included(self):
        """Test that instruction is included in prompt."""
        prompt = build_fim_prompt(
            code_before="",
            code_after="",
            instruction="write a sorting function",
            provider="generic"
        )
        
        assert "sorting function" in prompt


class TestGetSystemInstruction:
    """Test system instruction retrieval."""
    
    def test_chat_instruction(self):
        """Test getting chat system instruction."""
        instruction = get_system_instruction("chat")
        
        assert len(instruction) > 0
        assert "coding" in instruction.lower() or "assistant" in instruction.lower()
    
    def test_inline_instruction(self):
        """Test getting inline system instruction."""
        instruction = get_system_instruction("inline")
        
        assert len(instruction) > 0
        assert "completion" in instruction.lower() or "code" in instruction.lower()
    
    def test_refactor_instruction(self):
        """Test getting refactor system instruction."""
        instruction = get_system_instruction("refactor")
        
        assert len(instruction) > 0
        assert "refactor" in instruction.lower()
    
    def test_unknown_returns_chat(self):
        """Test that unknown task returns chat instruction."""
        instruction = get_system_instruction("nonexistent")
        
        assert instruction == SYSTEM_INSTRUCTION_CHAT


class TestFormatPrompt:
    """Test prompt formatting."""
    
    def test_basic_formatting(self):
        """Test basic template formatting."""
        template = "Hello {name}, welcome to {place}!"
        result = format_prompt(template, name="World", place="Earth")
        
        assert result == "Hello World, welcome to Earth!"
    
    def test_missing_key_preserved(self):
        """Test that missing keys are preserved."""
        template = "Hello {name}, {missing} today"
        result = format_prompt(template, name="World")
        
        assert result == "Hello World, {missing} today"
    
    def test_code_prompt(self):
        """Test formatting code prompt."""
        result = format_prompt(
            PROMPT_EXPLAIN_CODE,
            language="python",
            code="print('hello')"
        )
        
        assert "python" in result
        assert "print('hello')" in result


class TestPromptConstants:
    """Test that prompt constants are defined correctly."""
    
    def test_fim_template_has_markers(self):
        """Test FIM template has required markers."""
        assert "<|fim_prefix|>" in FIM_TEMPLATE
        assert "<|fim_suffix|>" in FIM_TEMPLATE
        assert "{code_before}" in FIM_TEMPLATE
        assert "{code_after}" in FIM_TEMPLATE
    
    def test_system_instructions_not_empty(self):
        """Test system instructions are defined."""
        assert len(SYSTEM_INSTRUCTION_CHAT) > 100
        assert len(SYSTEM_INSTRUCTION_INLINE) > 50
