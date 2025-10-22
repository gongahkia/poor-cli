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

    def set_tools(self, tools: List[Dict[str, Any]], current_dir: Optional[str] = None):
        """Set available tools for function calling"""
        self.tools = tools

        # Get current working directory
        if not current_dir:
            current_dir = os.getcwd()

        # System instruction to guide the AI
        system_instruction = f"""You are an AI assistant with access to tools for file operations. You MUST use these tools - do not just talk about using them.

CURRENT WORKING DIRECTORY: {current_dir}

CRITICAL RULES - YOU MUST FOLLOW THESE:
1. When a user asks you to create/write a file, you MUST call the write_file tool
2. When a user asks you to edit a file, you MUST call the edit_file tool
3. When a user asks to read a file, you MUST call the read_file tool
4. NEVER just describe what you would do - ACTUALLY DO IT using the tools

Your tools:
- write_file(file_path, content): Creates or overwrites a file. Always use ABSOLUTE paths.
- edit_file(file_path, old_text, new_text): Edits existing files. Always use ABSOLUTE paths.
- read_file(file_path): Reads file contents. Always use ABSOLUTE paths.
- glob_files(pattern): Find files
- grep_files(pattern): Search in files
- bash(command): Execute shell commands

FILE PATH RULES:
- ALWAYS create files in the current working directory: {current_dir}
- When user says "create file.cpp", use path: {current_dir}/file.cpp
- When user says "create foo/bar.py", use path: {current_dir}/foo/bar.py
- NEVER call bash("pwd") - the current directory is already provided above
- Just construct the absolute path directly by combining current directory with filename

WORKFLOW EXAMPLE:
User: "Create a hello.py file"
You MUST: Call write_file(file_path="{current_dir}/hello.py", content="print('Hello')")
You MUST NOT: Just say "I'll create the file" or describe the code
You MUST NOT: Call bash("pwd") first

Be concise. Execute tools immediately when asked."""

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
