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
1. Use the appropriate tools to complete the task
2. Always read files before editing them
3. Provide clear explanations of what you're doing
4. Show relevant code snippets or file contents when helpful

Available capabilities:
- Reading and writing files
- Editing files with precision
- Searching for files (glob patterns)
- Searching within files (grep)
- Executing bash commands

Be concise but thorough. Ask for clarification if needed."""

        # Initialize model with tools
        # Using gemini-1.5-flash for fast and cost-effective responses
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            tools=self.tools if self.tools else None,
            system_instruction=system_instruction,
        )
        self.chat = self.model.start_chat(enable_automatic_function_calling=False)

    def send_message(self, message: str) -> Any:
        """Send a message and get response"""
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
