#!/usr/bin/env python3
"""Test script to verify Gemini tool calling works"""

import os
import sys
from poor_cli.gemini_client import GeminiClient
from poor_cli.tools import ToolRegistry

def test_tool_calling():
    """Test if Gemini properly calls write_file tool"""

    # Initialize client and tools
    client = GeminiClient()
    tool_registry = ToolRegistry()
    tool_declarations = tool_registry.get_tool_declarations()
    client.set_tools(tool_declarations)

    # Send a message that should trigger write_file
    print("Sending message: 'Create a test.txt file with hello world'")
    response = client.send_message("Create a test.txt file with content 'Hello World'")

    # Check if function call was made
    if response.candidates[0].content.parts:
        part = response.candidates[0].content.parts[0]

        if hasattr(part, 'function_call') and part.function_call:
            print(f"✓ Tool call detected: {part.function_call.name}")
            print(f"  Arguments: {dict(part.function_call.args)}")
        elif hasattr(part, 'text'):
            print(f"✗ No tool call - got text response instead:")
            print(f"  {part.text[:200]}")
        else:
            print(f"✗ Unknown response type")
    else:
        print("✗ No response parts")

if __name__ == "__main__":
    test_tool_calling()
