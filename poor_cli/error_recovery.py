"""
Enhanced error recovery with AI-powered suggestions
"""

import re
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .exceptions import (
    APIError,
    APIRateLimitError,
    APITimeoutError,
    APIConnectionError,
    FileOperationError,
    FileNotFoundError,
    FilePermissionError,
    PathTraversalError,
    CommandExecutionError,
    ToolExecutionError,
    ValidationError,
    ConfigurationError,
    setup_logger,
)

logger = setup_logger(__name__)


@dataclass
class RecoverySuggestion:
    """A suggestion for recovering from an error"""
    title: str
    description: str
    commands: List[str]  # Commands that might help
    priority: int  # 1 = high, 2 = medium, 3 = low


class ErrorRecoveryManager:
    """Manages error recovery suggestions"""

    def __init__(self):
        self.error_patterns = self._build_error_patterns()

    def _build_error_patterns(self):
        """Build patterns for matching common errors"""
        return [
            # File not found errors
            (
                r"(?:No such file or directory|File not found|FileNotFoundError)",
                self._suggest_file_not_found
            ),
            # Permission denied errors
            (
                r"(?:Permission denied|PermissionError)",
                self._suggest_permission_denied
            ),
            # Import errors
            (
                r"(?:ModuleNotFoundError|ImportError|No module named)",
                self._suggest_import_error
            ),
            # Git errors
            (
                r"(?:not a git repository|fatal: not a git repository)",
                self._suggest_git_init
            ),
            # Network/connection errors
            (
                r"(?:Connection refused|Connection reset|ConnectionError|Network unreachable)",
                self._suggest_connection_error
            ),
            # Syntax errors
            (
                r"(?:SyntaxError|invalid syntax)",
                self._suggest_syntax_error
            ),
            # Type errors
            (
                r"(?:TypeError)",
                self._suggest_type_error
            ),
            # API key errors
            (
                r"(?:API key|authentication|invalid.*key|GEMINI_API_KEY)",
                self._suggest_api_key_error
            ),
        ]

    def get_suggestions(
        self,
        error: Exception,
        context: Optional[dict] = None
    ) -> List[RecoverySuggestion]:
        """Get recovery suggestions for an error

        Args:
            error: The exception that occurred
            context: Optional context (e.g., file paths, commands)

        Returns:
            List of recovery suggestions
        """
        suggestions = []

        # Get error message
        error_msg = str(error)
        error_type = type(error).__name__

        logger.debug(f"Finding suggestions for {error_type}: {error_msg}")

        # Try pattern matching
        for pattern, handler in self.error_patterns:
            if re.search(pattern, error_msg, re.IGNORECASE) or \
               re.search(pattern, error_type, re.IGNORECASE):
                suggestions.extend(handler(error, context))

        # Add type-specific suggestions
        if isinstance(error, APIRateLimitError):
            suggestions.extend(self._suggest_rate_limit(error, context))
        elif isinstance(error, APITimeoutError):
            suggestions.extend(self._suggest_timeout(error, context))
        elif isinstance(error, APIConnectionError):
            suggestions.extend(self._suggest_api_connection(error, context))
        elif isinstance(error, FilePermissionError):
            suggestions.extend(self._suggest_file_permission(error, context))
        elif isinstance(error, PathTraversalError):
            suggestions.extend(self._suggest_path_traversal(error, context))
        elif isinstance(error, CommandExecutionError):
            suggestions.extend(self._suggest_command_execution(error, context))
        elif isinstance(error, ConfigurationError):
            suggestions.extend(self._suggest_configuration(error, context))

        # Sort by priority
        suggestions.sort(key=lambda s: s.priority)

        # Deduplicate
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            key = (s.title, s.description)
            if key not in seen:
                seen.add(key)
                unique_suggestions.append(s)

        return unique_suggestions[:5]  # Return top 5

    def _suggest_file_not_found(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for file not found errors"""
        suggestions = []

        # Extract file path if possible
        file_path = self._extract_file_path(str(error))

        suggestions.append(RecoverySuggestion(
            title="Check file path",
            description="Verify the file path is correct and the file exists",
            commands=[
                "ls -la " + (file_path if file_path else "<directory>"),
                "find . -name " + (file_path if file_path else "<filename>")
            ],
            priority=1
        ))

        suggestions.append(RecoverySuggestion(
            title="Create the file",
            description="Create the missing file if it should exist",
            commands=["touch " + (file_path if file_path else "<file_path>")],
            priority=2
        ))

        return suggestions

    def _suggest_permission_denied(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for permission denied errors"""
        suggestions = []

        file_path = self._extract_file_path(str(error))

        suggestions.append(RecoverySuggestion(
            title="Check file permissions",
            description="View and update file permissions",
            commands=[
                "ls -l " + (file_path if file_path else "<file_path>"),
                "chmod +rw " + (file_path if file_path else "<file_path>")
            ],
            priority=1
        ))

        suggestions.append(RecoverySuggestion(
            title="Run with elevated privileges",
            description="Try running the command with sudo if appropriate",
            commands=["sudo <command>"],
            priority=3
        ))

        return suggestions

    def _suggest_import_error(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for import errors"""
        suggestions = []

        # Extract module name
        module_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", str(error))
        module = module_match.group(1) if module_match else None

        suggestions.append(RecoverySuggestion(
            title="Install missing package",
            description="Install the required Python package",
            commands=[
                "pip install " + (module if module else "<package_name>"),
                "pip install -r requirements.txt"
            ],
            priority=1
        ))

        suggestions.append(RecoverySuggestion(
            title="Check virtual environment",
            description="Ensure you're in the correct virtual environment",
            commands=["source venv/bin/activate"],
            priority=2
        ))

        return suggestions

    def _suggest_git_init(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for git repository errors"""
        return [
            RecoverySuggestion(
                title="Initialize git repository",
                description="Create a new git repository in the current directory",
                commands=["git init"],
                priority=1
            ),
            RecoverySuggestion(
                title="Navigate to git repository",
                description="Change to a directory that contains a git repository",
                commands=["cd <repository_path>"],
                priority=2
            )
        ]

    def _suggest_connection_error(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for network connection errors"""
        return [
            RecoverySuggestion(
                title="Check internet connection",
                description="Verify your internet connection is working",
                commands=["ping 8.8.8.8", "curl -I https://google.com"],
                priority=1
            ),
            RecoverySuggestion(
                title="Check firewall settings",
                description="Ensure firewall isn't blocking the connection",
                commands=[],
                priority=3
            )
        ]

    def _suggest_syntax_error(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for syntax errors"""
        return [
            RecoverySuggestion(
                title="Check Python syntax",
                description="Review the code for syntax errors (missing colons, parentheses, etc.)",
                commands=["python -m py_compile <file_path>"],
                priority=1
            )
        ]

    def _suggest_type_error(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for type errors"""
        return [
            RecoverySuggestion(
                title="Check variable types",
                description="Ensure variables are of the expected type",
                commands=[],
                priority=2
            )
        ]

    def _suggest_api_key_error(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for API key errors"""
        return [
            RecoverySuggestion(
                title="Set API key",
                description="Set your Gemini API key in the environment",
                commands=[
                    "export GEMINI_API_KEY='your-api-key'",
                    "echo 'GEMINI_API_KEY=your-api-key' > .env"
                ],
                priority=1
            ),
            RecoverySuggestion(
                title="Get API key",
                description="Get a free API key from Google AI Studio",
                commands=["Open: https://makersuite.google.com/app/apikey"],
                priority=2
            )
        ]

    def _suggest_rate_limit(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for API rate limit errors"""
        return [
            RecoverySuggestion(
                title="Wait and retry",
                description="Wait a few minutes before trying again",
                commands=[],
                priority=1
            ),
            RecoverySuggestion(
                title="Use different API key",
                description="Switch to a different API key if available",
                commands=["export GEMINI_API_KEY='alternative-key'"],
                priority=2
            )
        ]

    def _suggest_timeout(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for timeout errors"""
        return [
            RecoverySuggestion(
                title="Simplify request",
                description="Try breaking down the request into smaller parts",
                commands=[],
                priority=1
            ),
            RecoverySuggestion(
                title="Check network speed",
                description="Verify your internet connection is stable",
                commands=["speedtest"],
                priority=2
            )
        ]

    def _suggest_api_connection(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for API connection errors"""
        return [
            RecoverySuggestion(
                title="Check API status",
                description="Verify the Gemini API service is available",
                commands=["Open: https://status.cloud.google.com/"],
                priority=1
            ),
            RecoverySuggestion(
                title="Retry request",
                description="Try the request again after a short delay",
                commands=[],
                priority=2
            )
        ]

    def _suggest_file_permission(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for file permission errors"""
        file_path = self._extract_file_path(str(error))

        return [
            RecoverySuggestion(
                title="Fix file permissions",
                description="Update file permissions to allow read/write",
                commands=[
                    "chmod u+rw " + (file_path if file_path else "<file_path>"),
                    "ls -l " + (file_path if file_path else "<file_path>")
                ],
                priority=1
            )
        ]

    def _suggest_path_traversal(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for path traversal errors"""
        return [
            RecoverySuggestion(
                title="Use absolute paths",
                description="Provide an absolute path instead of relative path",
                commands=[],
                priority=1
            ),
            RecoverySuggestion(
                title="Check working directory",
                description="Verify you're in the correct directory",
                commands=["pwd", "ls -la"],
                priority=2
            )
        ]

    def _suggest_command_execution(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for command execution errors"""
        return [
            RecoverySuggestion(
                title="Check command syntax",
                description="Verify the command syntax is correct",
                commands=[],
                priority=1
            ),
            RecoverySuggestion(
                title="Check command availability",
                description="Ensure the command is installed",
                commands=["which <command>", "command -v <command>"],
                priority=2
            )
        ]

    def _suggest_configuration(self, error: Exception, context: Optional[dict]) -> List[RecoverySuggestion]:
        """Suggestions for configuration errors"""
        return [
            RecoverySuggestion(
                title="Check configuration file",
                description="Review and fix the configuration file",
                commands=["cat ~/.poor-cli/config.yaml"],
                priority=1
            ),
            RecoverySuggestion(
                title="Reset to defaults",
                description="Delete config file to use defaults",
                commands=["rm ~/.poor-cli/config.yaml"],
                priority=3
            )
        ]

    def _extract_file_path(self, error_msg: str) -> Optional[str]:
        """Extract file path from error message"""
        # Try common patterns
        patterns = [
            r"['\"]([^'\"]+)['\"]",  # Quoted paths
            r":\s+([^\s:]+)",  # After colon
            r"file\s+([^\s]+)",  # After "file"
        ]

        for pattern in patterns:
            match = re.search(pattern, error_msg)
            if match:
                path = match.group(1)
                # Validate it looks like a path
                if '/' in path or '\\' in path or '.' in path:
                    return path

        return None

    def format_suggestions(self, suggestions: List[RecoverySuggestion]) -> str:
        """Format suggestions for display

        Args:
            suggestions: List of suggestions

        Returns:
            Formatted string for display
        """
        if not suggestions:
            return "No recovery suggestions available."

        output = ["Recovery Suggestions:\n"]

        for i, suggestion in enumerate(suggestions, 1):
            output.append(f"{i}. {suggestion.title}")
            output.append(f"   {suggestion.description}")

            if suggestion.commands:
                output.append("   Try:")
                for cmd in suggestion.commands:
                    output.append(f"     $ {cmd}")

            output.append("")  # Blank line

        return "\n".join(output)
