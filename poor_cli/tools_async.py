"""
Async tool implementations for poor-cli
"""

import os
import asyncio
import subprocess
import glob as glob_module
import re
import aiofiles
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import (
    ToolExecutionError,
    CommandExecutionError,
    ValidationError,
    validate_file_path,
    setup_logger,
    FileNotFoundError as PoorFileNotFoundError,
    FilePermissionError,
    FileOperationError,
    PathTraversalError,
)

# Setup logger
logger = setup_logger(__name__)


class ToolRegistryAsync:
    """Async registry for all available tools"""

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
                    "description": "REQUIRED: Use this to actually create/write a file. Call this whenever the user asks to create, write, or generate a file.",
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
                                "description": "Text to find and replace"
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
                    "description": "Find files matching a glob pattern",
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
                                "description": "Directory or file to search in"
                            },
                            "file_pattern": {
                                "type": "STRING",
                                "description": "Glob pattern to filter files"
                            },
                            "case_sensitive": {
                                "type": "BOOLEAN",
                                "description": "Whether search should be case sensitive"
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
                    "description": "Execute a bash command",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "command": {
                                "type": "STRING",
                                "description": "Command to execute"
                            },
                            "timeout": {
                                "type": "INTEGER",
                                "description": "Timeout in seconds (default 60)"
                            }
                        },
                        "required": ["command"]
                    }
                }
            }
        }

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Get tool declarations for API"""
        return [tool["declaration"] for tool in self.tools.values()]

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool with given arguments

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result as string

        Raises:
            ToolExecutionError: If tool execution fails
        """
        try:
            if tool_name not in self.tools:
                raise ToolExecutionError(f"Unknown tool: {tool_name}")

            tool_function = self.tools[tool_name]["function"]
            logger.info(f"Executing tool: {tool_name} with args: {arguments}")

            result = await tool_function(**arguments)
            logger.debug(f"Tool {tool_name} executed successfully")

            return result

        except (ToolExecutionError, ValidationError, FileOperationError) as e:
            logger.error(f"Tool execution failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in tool execution: {e}", exc_info=True)
            raise ToolExecutionError(f"Tool execution failed: {str(e)}")

    async def read_file(self, file_path: str, start_line: Optional[int] = None,
                       end_line: Optional[int] = None) -> str:
        """Read file contents asynchronously

        Args:
            file_path: Path to file
            start_line: Optional starting line (1-indexed)
            end_line: Optional ending line (1-indexed)

        Returns:
            File contents

        Raises:
            FileOperationError: If read fails
        """
        try:
            # Validate path
            file_path = validate_file_path(file_path, must_exist=True, must_be_file=True)

            # Read file asynchronously
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if start_line or end_line:
                    lines = await f.readlines()
                    start = (start_line - 1) if start_line else 0
                    end = end_line if end_line else len(lines)
                    content = ''.join(lines[start:end])
                else:
                    content = await f.read()

            logger.info(f"Read file: {file_path}")
            return content

        except (PoorFileNotFoundError, FilePermissionError, PathTraversalError):
            raise
        except Exception as e:
            raise FileOperationError(f"Failed to read file {file_path}: {str(e)}")

    async def write_file(self, file_path: str, content: str) -> str:
        """Write content to file asynchronously

        Args:
            file_path: Path to file
            content: Content to write

        Returns:
            Success message

        Raises:
            FileOperationError: If write fails
        """
        try:
            # Validate path (don't require existence for write)
            file_path = validate_file_path(file_path, must_exist=False)

            # Create parent directories if needed
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            # Write file asynchronously
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)

            logger.info(f"Wrote file: {file_path}")
            return f"Successfully wrote to {file_path}"

        except (PathTraversalError, FilePermissionError):
            raise
        except Exception as e:
            raise FileOperationError(f"Failed to write file {file_path}: {str(e)}")

    async def edit_file(self, file_path: str, new_text: str, old_text: Optional[str] = None,
                       start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Edit file by replacing text or lines

        Args:
            file_path: Path to file
            new_text: New text to insert
            old_text: Old text to replace (for text replacement mode)
            start_line: Start line for line-based editing (1-indexed)
            end_line: End line for line-based editing (1-indexed)

        Returns:
            Success message

        Raises:
            FileOperationError: If edit fails
        """
        try:
            # Validate path
            file_path = validate_file_path(file_path, must_exist=True, must_be_file=True)

            # Read current content
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()

            # Perform edit
            if old_text is not None:
                # Text replacement mode
                if old_text not in content:
                    raise ValidationError(f"Text not found in file: {old_text[:50]}...")
                new_content = content.replace(old_text, new_text)
            elif start_line is not None:
                # Line-based editing mode
                lines = content.split('\n')
                start = start_line - 1
                end = end_line if end_line else start + 1

                if start < 0 or start >= len(lines):
                    raise ValidationError(f"Invalid start_line: {start_line}")

                lines[start:end] = [new_text]
                new_content = '\n'.join(lines)
            else:
                # Just append if no old_text or line numbers
                new_content = content + new_text

            # Write new content
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(new_content)

            logger.info(f"Edited file: {file_path}")
            return f"Successfully edited {file_path}"

        except (PoorFileNotFoundError, FilePermissionError, ValidationError):
            raise
        except Exception as e:
            raise FileOperationError(f"Failed to edit file {file_path}: {str(e)}")

    async def glob_files(self, pattern: str, path: Optional[str] = None) -> str:
        """Find files matching glob pattern

        Args:
            pattern: Glob pattern
            path: Directory to search in

        Returns:
            List of matching files

        Raises:
            ToolExecutionError: If glob fails
        """
        try:
            search_path = path or os.getcwd()

            # Run glob in thread pool
            def _glob():
                full_pattern = os.path.join(search_path, pattern)
                matches = sorted(glob_module.glob(full_pattern, recursive=True))
                return matches[:100]  # Limit results

            matches = await asyncio.to_thread(_glob)

            if not matches:
                return f"No files found matching: {pattern}"

            result = f"Found {len(matches)} files:\n" + "\n".join(matches)
            logger.info(f"Glob search: {pattern} found {len(matches)} files")
            return result

        except Exception as e:
            raise ToolExecutionError(f"Glob search failed: {str(e)}")

    async def grep_files(self, pattern: str, path: Optional[str] = None,
                        file_pattern: str = "*", case_sensitive: bool = True) -> str:
        """Search for pattern in files

        Args:
            pattern: Regex pattern to search for
            path: Directory or file to search
            file_pattern: Glob pattern to filter files
            case_sensitive: Case sensitivity

        Returns:
            Search results

        Raises:
            ToolExecutionError: If grep fails
        """
        try:
            search_path = path or os.getcwd()
            flags = 0 if case_sensitive else re.IGNORECASE

            # Compile regex
            regex = re.compile(pattern, flags)

            results = []
            result_count = 0

            # Get files to search
            if os.path.isfile(search_path):
                files = [search_path]
            else:
                full_pattern = os.path.join(search_path, "**", file_pattern)
                files = glob_module.glob(full_pattern, recursive=True)
                files = [f for f in files if os.path.isfile(f)]

            # Search each file
            for file_path in files[:50]:  # Limit files searched
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = await f.readlines()

                    for line_num, line in enumerate(lines, 1):
                        if regex.search(line):
                            results.append(f"{file_path}:{line_num}: {line.rstrip()}")
                            result_count += 1

                            if result_count >= 100:  # Limit total results
                                break

                except Exception as e:
                    logger.debug(f"Skipping file {file_path}: {e}")
                    continue

                if result_count >= 100:
                    break

            if not results:
                return f"No matches found for pattern: {pattern}"

            result = f"Found {len(results)} matches:\n" + "\n".join(results)
            logger.info(f"Grep search: {pattern} found {len(results)} matches")
            return result

        except Exception as e:
            raise ToolExecutionError(f"Grep search failed: {str(e)}")

    async def bash(self, command: str, timeout: int = 60) -> str:
        """Execute bash command asynchronously

        Args:
            command: Command to execute
            timeout: Timeout in seconds

        Returns:
            Command output

        Raises:
            CommandExecutionError: If command fails
        """
        try:
            logger.info(f"Executing bash command: {command}")

            # Create subprocess asynchronously
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )

            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise CommandExecutionError(
                    f"Command timed out after {timeout} seconds: {command}"
                )

            # Decode output
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')

            if process.returncode != 0:
                error_msg = stderr_text or stdout_text or "Command failed"
                raise CommandExecutionError(
                    f"Command failed with exit code {process.returncode}: {error_msg}"
                )

            result = stdout_text or "(No output)"
            logger.info(f"Bash command completed successfully")
            return result

        except CommandExecutionError:
            raise
        except Exception as e:
            raise CommandExecutionError(f"Failed to execute command: {str(e)}")
