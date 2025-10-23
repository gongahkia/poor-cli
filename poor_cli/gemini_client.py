"""
Gemini API client wrapper with function calling support
"""

import os
import json
import time
from typing import Any, Dict, List, Optional
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from .exceptions import (
    APIError,
    APIConnectionError,
    APITimeoutError,
    APIRateLimitError,
    ConfigurationError,
    ValidationError,
    setup_logger,
)

# Setup logger
logger = setup_logger(__name__)


class GeminiClient:
    """Wrapper for Gemini API with function calling capabilities"""

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3,
                 retry_delay: float = 1.0):
        """
        Initialize Gemini client with API key and retry configuration

        Args:
            api_key: Gemini API key (if None, uses GEMINI_API_KEY env var)
            max_retries: Maximum number of retries for failed API calls
            retry_delay: Initial delay between retries in seconds (uses exponential backoff)

        Raises:
            ConfigurationError: If API key is not provided
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY not found. Please set it as an environment variable or pass it as an argument."
            )

        # Validate API key format (basic check)
        if not isinstance(self.api_key, str) or len(self.api_key) < 10:
            raise ConfigurationError("Invalid API key format")

        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        try:
            genai.configure(api_key=self.api_key)
            logger.info("Gemini API client configured successfully")
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}")
            raise ConfigurationError(f"Failed to configure Gemini API: {str(e)}")

        self.model = None
        self.chat = None
        self.tools = []

    def set_tools(self, tools: List[Dict[str, Any]], current_dir: Optional[str] = None):
        """
        Set available tools for function calling and initialize model

        Args:
            tools: List of tool declarations for the API
            current_dir: Current working directory for the session

        Raises:
            ConfigurationError: If model initialization fails
        """
        try:
            self.tools = tools

            # Get current working directory
            if not current_dir:
                current_dir = os.getcwd()

            # System instruction to guide the AI
            system_instruction = f"""You are an AI assistant with TOOL CALLING capabilities. You have been given tools to perform file operations and system commands.

CRITICAL: When a user asks you to write/create a file, you MUST immediately call the write_file tool. DO NOT just show the code to the user. DO NOT say "write this to a file". Actually call the tool.

CURRENT WORKING DIRECTORY: {current_dir}

MANDATORY TOOL USAGE RULES:
1. File creation/writing: IMMEDIATELY call write_file(file_path, content)
2. File editing: IMMEDIATELY call edit_file(file_path, old_text, new_text)
3. File reading: IMMEDIATELY call read_file(file_path)
4. NEVER respond with just code snippets when asked to create a file
5. NEVER say "write this to a file" - YOU must call the tool yourself

Your available tools:
- write_file(file_path, content): Creates or overwrites a file
- edit_file(file_path, old_text, new_text): Edits existing files
- read_file(file_path): Reads file contents
- glob_files(pattern): Find files matching pattern
- grep_files(pattern): Search for text in files
- bash(command): Execute shell commands

FILE PATH RULES:
- ALWAYS use ABSOLUTE paths: {current_dir}/filename
- User says "create test.py" → use path: {current_dir}/test.py
- User says "create src/main.py" → use path: {current_dir}/src/main.py

CORRECT BEHAVIOR EXAMPLES:

Example 1 - File creation:
User: "Create a hello.py file with a hello world program"
❌ WRONG: Display code and say "Save this as hello.py"
✅ CORRECT: Call write_file(file_path="{current_dir}/hello.py", content="print('Hello, World!')")

Example 2 - Code solution:
User: "Give me the solution for 3sum"
❌ WRONG: Show code and say "Write this code to a file named three_sum.py"
✅ CORRECT: First explain the solution, THEN ask "Would you like me to save this to a file?" If they say yes OR if they originally asked to "create"/"write" a file, call write_file()

Example 3 - Explicit file request:
User: "Write the quicksort algorithm to sort.py"
✅ CORRECT: Immediately call write_file(file_path="{current_dir}/sort.py", content="def quicksort(arr):...")

IMPORTANT: Only call write_file if the user:
1. Explicitly asks to "create", "write", "save" a file, OR
2. Confirms they want to save code after you show it

If the user just asks for a solution/code without mentioning a file, show the code first and ask if they want it saved."""

            # Initialize model with tools
            # Using gemini-2.5-flash for fast and cost-effective responses
            self.model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                tools=self.tools if self.tools else None,
                system_instruction=system_instruction,
            )
            self.chat = self.model.start_chat(enable_automatic_function_calling=False)
            logger.info(f"Model initialized with {len(self.tools)} tools")

        except Exception as e:
            logger.error(f"Failed to initialize model: {e}")
            raise ConfigurationError(f"Failed to initialize model: {str(e)}")

    def _send_with_retry(self, message) -> Any:
        """
        Send message with retry logic for handling transient failures

        Args:
            message: Message to send (str or Content object)

        Returns:
            API response

        Raises:
            APIError: If all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Sending message (attempt {attempt + 1}/{self.max_retries})")
                response = self.chat.send_message(message)
                logger.debug("Message sent successfully")
                return response

            except google_exceptions.ResourceExhausted as e:
                # Rate limit error - should retry with backoff
                last_exception = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Rate limit exceeded, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")

                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    raise APIRateLimitError(
                        "Rate limit exceeded. Please try again later.",
                        str(e)
                    )

            except google_exceptions.DeadlineExceeded as e:
                # Timeout error - should retry
                last_exception = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Request timeout, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")

                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    raise APITimeoutError(
                        "Request timed out after multiple retries",
                        str(e)
                    )

            except (google_exceptions.ServiceUnavailable,
                    google_exceptions.InternalServerError) as e:
                # Service error - should retry
                last_exception = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Service unavailable, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")

                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    raise APIConnectionError(
                        "Service unavailable after multiple retries",
                        str(e)
                    )

            except google_exceptions.InvalidArgument as e:
                # Invalid request - should not retry
                logger.error(f"Invalid request: {e}")
                raise ValidationError(f"Invalid API request: {str(e)}")

            except google_exceptions.PermissionDenied as e:
                # Permission error - should not retry
                logger.error(f"Permission denied: {e}")
                raise APIError(
                    "Permission denied. Check your API key and permissions.",
                    str(e)
                )

            except Exception as e:
                # Unknown error
                last_exception = e
                logger.error(f"Unexpected error during API call: {type(e).__name__}: {e}")

                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    raise APIError(
                        f"API call failed after {self.max_retries} retries",
                        str(e)
                    )

        # This should not be reached, but just in case
        if last_exception:
            raise APIError("API call failed", str(last_exception))

    def send_message(self, message) -> Any:
        """
        Send a message and get response with retry logic

        Args:
            message: Message to send (str or Content objects)

        Returns:
            API response

        Raises:
            APIError: If the API call fails
            ConfigurationError: If client is not properly configured
        """
        if not self.chat:
            logger.warning("Chat not initialized, initializing with empty tools")
            self.set_tools([])

        try:
            return self._send_with_retry(message)
        except (APIError, ValidationError, ConfigurationError) as e:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            # Wrap any unexpected exceptions
            logger.exception("Unexpected error in send_message")
            raise APIError(f"Unexpected error: {type(e).__name__}", str(e))

    def send_message_with_tools(self, message: str, tool_results: Optional[List[Dict]] = None):
        """
        Send message with optional tool results from previous call

        Args:
            message: Message to send
            tool_results: Optional tool results from previous call

        Returns:
            API response

        Raises:
            APIError: If the API call fails
        """
        if tool_results:
            # Send tool results back to continue conversation
            return self.send_message(tool_results)
        else:
            return self.send_message(message)

    def get_history(self) -> List:
        """
        Get conversation history

        Returns:
            List of conversation messages, or empty list if no chat
        """
        try:
            if self.chat:
                return self.chat.history
            return []
        except Exception as e:
            logger.warning(f"Failed to get conversation history: {e}")
            return []
