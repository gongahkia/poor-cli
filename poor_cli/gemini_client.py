"""
Gemini API client wrapper with function calling support
"""

import os
import json
from typing import Any, Dict, List, Optional
import google.generativeai as genai


class GeminiClient:
    """Wrapper for Gemini API with function calling capabilities"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini client with API key"""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not found. Please set it as an environment variable."
            )

        genai.configure(api_key=self.api_key)
        self.model = None
        self.chat = None
        self.tools = []

    def set_tools(self, tools: List[Dict[str, Any]]):
        """Set available tools for function calling"""
        self.tools = tools

        # System instruction to guide the AI
        system_instruction = """You are an AI assistant with access to various tools for file operations, code analysis, and system commands.

When a user asks you to perform tasks:
1. ALWAYS use the appropriate tools to complete the task
2. When asked to "write", "create", or provide code/functions, ALWAYS use write_file tool to create the actual file
3. Always read files before editing them using read_file
4. When modifying existing files, use edit_file instead of write_file to preserve other content
5. Provide clear explanations of what you're doing

Available capabilities:
- Reading and writing files (use write_file for new files)
- Editing files with precision (use edit_file for modifications)
- Searching for files (glob patterns with glob_files)
- Searching within files (grep with grep_files)
- Executing bash commands (use bash tool)

IMPORTANT: When users ask for code or functions, don't just show them - CREATE THE FILE using write_file.
Use absolute paths when writing files. The current working directory is available via bash("pwd") if needed.

Be concise but thorough. Ask for clarification if needed."""

        # Initialize model with tools
        # Using gemini-2.5-flash for fast and cost-effective responses
        self.model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            tools=self.tools if self.tools else None,
            system_instruction=system_instruction,
        )
        self.chat = self.model.start_chat(enable_automatic_function_calling=False)

    def send_message(self, message) -> Any:
        """Send a message and get response (accepts str or Content objects)"""
        if not self.chat:
            self.set_tools([])

        response = self.chat.send_message(message)
        return response

    def send_message_with_tools(self, message: str, tool_results: Optional[List[Dict]] = None):
        """Send message with optional tool results from previous call"""
        if not self.chat:
            self.set_tools([])

        if tool_results:
            # Send tool results back to continue conversation
            response = self.chat.send_message(tool_results)
        else:
            response = self.chat.send_message(message)

        return response

    def get_history(self) -> List:
        """Get conversation history"""
        if self.chat:
            return self.chat.history
        return []
