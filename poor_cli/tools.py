"""
Tool implementations for poor-cli
"""

import os
import subprocess
import glob as glob_module
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import (
    ToolExecutionError,
    CommandExecutionError,
    ValidationError,
    validate_file_path,
    safe_read_file,
    safe_write_file,
    setup_logger,
    FileNotFoundError as PoorFileNotFoundError,
    FilePermissionError,
    FileOperationError,
    PathTraversalError,
)

# Setup logger
logger = setup_logger(__name__)


class ToolRegistry:
    """Registry for all available tools"""

    def __init__(self):
        self.tools = {}
        self._register_tools()

    def _register_tools(self):
        """Register all available tools"""
        self.tools = {
            "read_file": {
                "function": self.read_file,
                "declaration": {
                    "name": "read_file",
                    "description": "Read contents of a file from the filesystem",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file_path": {
                                "type": "STRING",
                                "description": "Absolute path to the file to read"
                            },
                            "start_line": {
                                "type": "INTEGER",
                                "description": "Optional starting line number (1-indexed)"
                            },
                            "end_line": {
                                "type": "INTEGER",
                                "description": "Optional ending line number (1-indexed)"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            "write_file": {
                "function": self.write_file,
                "declaration": {
                    "name": "write_file",
                    "description": "REQUIRED: Use this to actually create/write a file. Call this whenever the user asks to create, write, or generate a file. Do NOT just describe the content - call this function to create the actual file.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file_path": {
                                "type": "STRING",
                                "description": "Absolute path to the file to write"
                            },
                            "content": {
                                "type": "STRING",
                                "description": "Content to write to the file"
                            }
                        },
                        "required": ["file_path", "content"]
                    }
                }
            },
            "edit_file": {
                "function": self.edit_file,
                "declaration": {
                    "name": "edit_file",
                    "description": "Edit a file by replacing specific text or lines",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file_path": {
                                "type": "STRING",
                                "description": "Absolute path to the file to edit"
                            },
                            "old_text": {
                                "type": "STRING",
                                "description": "Text to find and replace (for string replacement mode)"
                            },
                            "new_text": {
                                "type": "STRING",
                                "description": "Text to replace with"
                            },
                            "start_line": {
                                "type": "INTEGER",
                                "description": "Starting line number for line-based editing (1-indexed)"
                            },
                            "end_line": {
                                "type": "INTEGER",
                                "description": "Ending line number for line-based editing (1-indexed)"
                            }
                        },
                        "required": ["file_path", "new_text"]
                    }
                }
            },
            "glob_files": {
                "function": self.glob_files,
                "declaration": {
                    "name": "glob_files",
                    "description": "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.js')",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "pattern": {
                                "type": "STRING",
                                "description": "Glob pattern to match files"
                            },
                            "path": {
                                "type": "STRING",
                                "description": "Directory to search in (defaults to current directory)"
                            }
                        },
                        "required": ["pattern"]
                    }
                }
            },
            "grep_files": {
                "function": self.grep_files,
                "declaration": {
                    "name": "grep_files",
                    "description": "Search for pattern in files using regex",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "pattern": {
                                "type": "STRING",
                                "description": "Regex pattern to search for"
                            },
                            "path": {
                                "type": "STRING",
                                "description": "File or directory to search in (defaults to current directory)"
                            },
                            "file_pattern": {
                                "type": "STRING",
                                "description": "Glob pattern to filter files (e.g., '*.py')"
                            },
                            "case_sensitive": {
                                "type": "BOOLEAN",
                                "description": "Whether search is case sensitive (default: true)"
                            }
                        },
                        "required": ["pattern"]
                    }
                }
            },
            "bash": {
                "function": self.bash,
                "declaration": {
                    "name": "bash",
                    "description": "Execute a bash command and return output",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "command": {
                                "type": "STRING",
                                "description": "The bash command to execute"
                            },
                            "timeout": {
                                "type": "INTEGER",
                                "description": "Optional timeout in seconds (default: 120)"
                            }
                        },
                        "required": ["command"]
                    }
                }
            }
        }

    def get_tool_declarations(self) -> List[Dict]:
        """Get all tool declarations for Gemini API"""
        return [tool["declaration"] for tool in self.tools.values()]

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool with given arguments"""
        if tool_name not in self.tools:
            error_msg = f"Error: Unknown tool '{tool_name}'"
            logger.error(error_msg)
            return error_msg

        try:
            logger.info(f"Executing tool: {tool_name} with args: {args}")
            result = self.tools[tool_name]["function"](**args)
            logger.debug(f"Tool {tool_name} completed successfully")
            return result
        except (ToolExecutionError, CommandExecutionError, ValidationError,
                FileOperationError, PathTraversalError) as e:
            # Handle known errors with detailed information
            error_msg = str(e)
            logger.error(f"Tool {tool_name} failed: {error_msg}", exc_info=True)
            return f"Error: {error_msg}"
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Unexpected error in {tool_name}: {type(e).__name__}: {str(e)}"
            logger.exception(f"Unexpected error executing {tool_name}")
            return f"Error: {error_msg}"

    # Tool implementations

    def read_file(self, file_path: str, start_line: Optional[int] = None,
                  end_line: Optional[int] = None) -> str:
        """Read file contents with validation and security checks"""
        try:
            # Validate file path and check it exists
            path = validate_file_path(file_path, must_exist=True, must_be_file=True)

            # Validate line numbers if provided
            if start_line is not None and start_line < 1:
                raise ValidationError(f"start_line must be >= 1, got {start_line}")
            if end_line is not None and end_line < 1:
                raise ValidationError(f"end_line must be >= 1, got {end_line}")
            if start_line and end_line and start_line > end_line:
                raise ValidationError(f"start_line ({start_line}) cannot be greater than end_line ({end_line})")

            # Read file with safety checks
            content = safe_read_file(path)
            lines = content.splitlines(keepends=True)

            # Handle line range if specified
            if start_line is not None or end_line is not None:
                start = (start_line - 1) if start_line else 0
                end = end_line if end_line else len(lines)

                # Validate range is within file bounds
                if start >= len(lines):
                    raise ValidationError(f"start_line {start_line} is beyond file length ({len(lines)} lines)")
                if end > len(lines):
                    raise ValidationError(f"end_line {end_line} is beyond file length ({len(lines)} lines)")

                lines = lines[start:end]
                line_offset = start
            else:
                line_offset = 0

            # Add line numbers
            numbered_lines = [
                f"{line_offset + i + 1:4d}  {line}"
                for i, line in enumerate(lines)
            ]

            result = "".join(numbered_lines)
            logger.info(f"Successfully read {len(lines)} lines from {file_path}")
            return result

        except (ValidationError, FileOperationError, FilePermissionError,
                PoorFileNotFoundError, PathTraversalError) as e:
            # Re-raise known errors to be caught by execute_tool
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"Unexpected error reading file {file_path}")
            raise FileOperationError(f"Failed to read {file_path}", str(e))

    def write_file(self, file_path: str, content: str) -> str:
        """Write content to file with validation and security checks"""
        try:
            # Validate input
            if not isinstance(content, str):
                raise ValidationError(f"Content must be a string, got {type(content).__name__}")

            # Validate file path (no must_exist check since we're creating it)
            path = validate_file_path(file_path)

            # Write file with safety checks
            safe_write_file(path, content, create_dirs=True)

            logger.info(f"Successfully wrote {len(content)} characters to {file_path}")
            return f"Successfully wrote to {file_path}"

        except (ValidationError, FileOperationError, FilePermissionError,
                PathTraversalError) as e:
            # Re-raise known errors to be caught by execute_tool
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"Unexpected error writing file {file_path}")
            raise FileOperationError(f"Failed to write {file_path}", str(e))

    def edit_file(self, file_path: str, new_text: str, old_text: Optional[str] = None,
                  start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Edit file using string replacement or line-based editing with validation"""
        try:
            # Validate file path and check it exists
            path = validate_file_path(file_path, must_exist=True, must_be_file=True)

            # Validate input
            if not isinstance(new_text, str):
                raise ValidationError(f"new_text must be a string, got {type(new_text).__name__}")

            # Read file with safety checks
            content = safe_read_file(path)
            lines = content.splitlines(keepends=True)

            # Determine editing mode
            if old_text is not None:
                # String replacement mode
                if not isinstance(old_text, str):
                    raise ValidationError(f"old_text must be a string, got {type(old_text).__name__}")

                if old_text not in content:
                    # Provide more helpful error message
                    preview = old_text[:100] + "..." if len(old_text) > 100 else old_text
                    raise ValidationError(
                        f"Text not found in file. Searched for: {preview}"
                    )

                new_content = content.replace(old_text, new_text)
                logger.info(f"Replaced text in {file_path} (string replacement mode)")

            elif start_line is not None and end_line is not None:
                # Line-based editing mode
                if start_line < 1:
                    raise ValidationError(f"start_line must be >= 1, got {start_line}")
                if end_line < 1:
                    raise ValidationError(f"end_line must be >= 1, got {end_line}")
                if start_line > end_line:
                    raise ValidationError(
                        f"start_line ({start_line}) cannot be greater than end_line ({end_line})"
                    )
                if end_line > len(lines):
                    raise ValidationError(
                        f"end_line ({end_line}) exceeds file length ({len(lines)} lines)"
                    )

                # Replace the specified line range
                new_lines = lines[:start_line-1] + [new_text + '\n'] + lines[end_line:]
                new_content = "".join(new_lines)
                logger.info(f"Edited {file_path} lines {start_line}-{end_line}")

            else:
                raise ValidationError(
                    "Must provide either old_text (for string replacement) or "
                    "both start_line and end_line (for line-based editing)"
                )

            # Write the edited content back
            safe_write_file(path, new_content, create_dirs=False)

            return f"Successfully edited {file_path}"

        except (ValidationError, FileOperationError, FilePermissionError,
                PoorFileNotFoundError, PathTraversalError) as e:
            # Re-raise known errors to be caught by execute_tool
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"Unexpected error editing file {file_path}")
            raise FileOperationError(f"Failed to edit {file_path}", str(e))

    def glob_files(self, pattern: str, path: Optional[str] = None) -> str:
        """Find files matching glob pattern with validation"""
        try:
            # Validate pattern
            if not pattern or not isinstance(pattern, str):
                raise ValidationError("Pattern must be a non-empty string")

            # Validate and resolve search path
            if path:
                search_path = validate_file_path(path, must_exist=True, must_be_dir=True)
            else:
                search_path = Path.cwd()

            logger.info(f"Searching for pattern '{pattern}' in {search_path}")

            # Perform glob search
            try:
                matches = list(search_path.glob(pattern))
            except ValueError as e:
                raise ValidationError(f"Invalid glob pattern: {pattern}", str(e))

            if not matches:
                return f"No files found matching pattern: {pattern}"

            # Sort efficiently - only get mtime for files we'll display
            # This fixes the performance issue of sorting all matches
            try:
                matches_to_sort = matches[:1000]  # Only sort first 1000
                matches_to_sort.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                remaining = matches[1000:] if len(matches) > 1000 else []
                matches = matches_to_sort + remaining
            except OSError as e:
                # If sorting fails (e.g., permission issues), continue with unsorted
                logger.warning(f"Could not sort matches by modification time: {e}")

            # Build result
            result = f"Found {len(matches)} file(s):\n"
            display_limit = 100
            for match in matches[:display_limit]:
                result += f"  {match}\n"

            if len(matches) > display_limit:
                result += f"  ... and {len(matches) - display_limit} more\n"

            logger.info(f"Found {len(matches)} matches for pattern '{pattern}'")
            return result

        except (ValidationError, FileOperationError, PathTraversalError) as e:
            # Re-raise known errors to be caught by execute_tool
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"Unexpected error in glob search for pattern '{pattern}'")
            raise ToolExecutionError("glob_files", f"Search failed: {str(e)}")

    def grep_files(self, pattern: str, path: Optional[str] = None,
                   file_pattern: Optional[str] = None,
                   case_sensitive: bool = True) -> str:
        """Search for pattern in files with validation"""
        try:
            # Validate pattern
            if not pattern or not isinstance(pattern, str):
                raise ValidationError("Pattern must be a non-empty string")

            # Validate and resolve search path
            if path:
                search_path = validate_file_path(path, must_exist=True)
            else:
                search_path = Path.cwd()

            # Compile regex pattern
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                regex = re.compile(pattern, flags)
            except re.error as e:
                raise ValidationError(f"Invalid regex pattern: {pattern}", str(e))

            logger.info(f"Searching for pattern '{pattern}' in {search_path}")

            results = []
            files_searched = 0
            files_skipped = 0

            # Determine which files to search
            if search_path.is_file():
                files = [search_path]
            else:
                # Get all files matching file_pattern
                try:
                    if file_pattern:
                        files = list(search_path.glob(f"**/{file_pattern}"))
                    else:
                        files = [f for f in search_path.rglob("*") if f.is_file()]
                except ValueError as e:
                    raise ValidationError(f"Invalid file pattern: {file_pattern}", str(e))

            # Search through files
            result_limit = 100
            for file_path in files:
                if len(results) >= result_limit:
                    break

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{line_num}: {line.rstrip()}")

                                if len(results) >= result_limit:
                                    break
                    files_searched += 1

                except UnicodeDecodeError:
                    # Skip binary files silently
                    files_skipped += 1
                    logger.debug(f"Skipped binary file: {file_path}")
                    continue
                except PermissionError:
                    # Skip files we can't read
                    files_skipped += 1
                    logger.debug(f"Skipped file (permission denied): {file_path}")
                    continue
                except OSError as e:
                    # Skip files with other OS errors
                    files_skipped += 1
                    logger.debug(f"Skipped file (OS error): {file_path}: {e}")
                    continue

            # Build result message
            if not results:
                msg = f"No matches found for pattern: {pattern}"
                if files_searched > 0:
                    msg += f"\nSearched {files_searched} file(s)"
                    if files_skipped > 0:
                        msg += f" (skipped {files_skipped})"
                return msg

            result = f"Found {len(results)} match(es) in {files_searched} file(s)"
            if files_skipped > 0:
                result += f" (skipped {files_skipped} files)"
            result += ":\n"
            result += "\n".join(results)

            if len(results) >= result_limit:
                result += f"\n... (limit of {result_limit} results reached)"

            logger.info(f"Found {len(results)} matches for pattern '{pattern}' "
                       f"(searched {files_searched} files, skipped {files_skipped})")
            return result

        except (ValidationError, FileOperationError, PathTraversalError) as e:
            # Re-raise known errors to be caught by execute_tool
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"Unexpected error in grep search for pattern '{pattern}'")
            raise ToolExecutionError("grep_files", f"Search failed: {str(e)}")

    def bash(self, command: str, timeout: int = 120) -> str:
        """
        Execute bash command with validation and safety checks

        Note: Uses shell=True for flexibility, but commands should be validated
        by the permission system before reaching this point.
        """
        try:
            # Validate command input
            if not command or not isinstance(command, str):
                raise ValidationError("Command must be a non-empty string")

            # Validate timeout
            if not isinstance(timeout, int) or timeout <= 0:
                raise ValidationError(f"Timeout must be a positive integer, got {timeout}")
            if timeout > 600:  # Max 10 minutes
                raise ValidationError(f"Timeout too large (max 600 seconds), got {timeout}")

            # Log command execution
            logger.info(f"Executing bash command: {command[:100]}{'...' if len(command) > 100 else ''}")

            # Execute command
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=os.getcwd(),
                    # Note: We keep shell=True for compatibility with existing usage,
                    # but this should be validated by the permission system
                )
            except subprocess.TimeoutExpired as e:
                logger.warning(f"Command timed out after {timeout} seconds: {command[:100]}")
                raise CommandExecutionError(
                    command,
                    f"Command timed out after {timeout} seconds"
                )

            # Build output
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")

            output = "\n".join(output_parts) if output_parts else "Command completed with no output"

            # Log completion
            if result.returncode == 0:
                logger.info(f"Command completed successfully with exit code 0")
            else:
                logger.warning(f"Command exited with non-zero code: {result.returncode}")
                output += f"\n\nCommand exited with code {result.returncode}"

            return output

        except (ValidationError, CommandExecutionError) as e:
            # Re-raise known errors to be caught by execute_tool
            raise
        except FileNotFoundError as e:
            # Command not found
            logger.error(f"Command not found: {command}")
            raise CommandExecutionError(command, f"Command not found: {str(e)}")
        except PermissionError as e:
            # Permission denied
            logger.error(f"Permission denied for command: {command}")
            raise CommandExecutionError(command, f"Permission denied: {str(e)}")
        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"Unexpected error executing command: {command[:100]}")
            raise CommandExecutionError(
                command,
                f"Unexpected error: {type(e).__name__}: {str(e)}"
            )
