"""
Async tool implementations for poor-cli
"""

import os
import asyncio
import subprocess
import shlex
import glob as glob_module
import json
import time
import re
import shutil
import socket
import tempfile
import ipaddress
import importlib.metadata
import sys
import aiofiles
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from collections import Counter

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - exercised on py<3.11
    tomllib = None

try:
    import tomli
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    tomli = None

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:  # pragma: no cover - optional fallback
    YAML_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:  # pragma: no cover - optional fallback
    AIOHTTP_AVAILABLE = False

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
from .command_validator import get_command_validator

# Setup logger
logger = setup_logger(__name__)


class ToolRegistryAsync:
    """Async registry for all available tools"""
    MAX_CAPTURED_OUTPUT_BYTES = 1024 * 1024  # 1 MiB per stream

    def __init__(self):
        self.tools = {}
        self.command_validator = get_command_validator(strict_mode=False)
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
            },
            "list_directory": {
                "function": self.list_directory,
                "declaration": {
                    "name": "list_directory",
                    "description": "List directory contents with detailed metadata",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Directory path (defaults to current)"
                            },
                            "show_hidden": {
                                "type": "BOOLEAN",
                                "description": "Show hidden files (default false)"
                            }
                        },
                        "required": []
                    }
                }
            },
            "copy_file": {
                "function": self.copy_file,
                "declaration": {
                    "name": "copy_file",
                    "description": "Copy a file to another location",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "source": {
                                "type": "STRING",
                                "description": "Source file path"
                            },
                            "destination": {
                                "type": "STRING",
                                "description": "Destination file path"
                            }
                        },
                        "required": ["source", "destination"]
                    }
                }
            },
            "move_file": {
                "function": self.move_file,
                "declaration": {
                    "name": "move_file",
                    "description": "Move or rename a file",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "source": {
                                "type": "STRING",
                                "description": "Source file path"
                            },
                            "destination": {
                                "type": "STRING",
                                "description": "Destination file path"
                            }
                        },
                        "required": ["source", "destination"]
                    }
                }
            },
            "delete_file": {
                "function": self.delete_file,
                "declaration": {
                    "name": "delete_file",
                    "description": "Delete a file",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file_path": {
                                "type": "STRING",
                                "description": "Path to file to delete"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            "diff_files": {
                "function": self.diff_files,
                "declaration": {
                    "name": "diff_files",
                    "description": "Compare two files and show differences",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file1": {
                                "type": "STRING",
                                "description": "First file path"
                            },
                            "file2": {
                                "type": "STRING",
                                "description": "Second file path"
                            }
                        },
                        "required": ["file1", "file2"]
                    }
                }
            },
            "git_status": {
                "function": self.git_status,
                "declaration": {
                    "name": "git_status",
                    "description": "Get git repository status",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Repository path (defaults to current)"
                            }
                        },
                        "required": []
                    }
                }
            },
            "git_diff": {
                "function": self.git_diff,
                "declaration": {
                    "name": "git_diff",
                    "description": "Show git differences",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Repository path"
                            },
                            "file_path": {
                                "type": "STRING",
                                "description": "Specific file to diff"
                            }
                        },
                        "required": []
                    }
                }
            },
            "create_directory": {
                "function": self.create_directory,
                "declaration": {
                    "name": "create_directory",
                    "description": "Create a new directory",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Directory path to create"
                            }
                        },
                        "required": ["path"]
                    }
                }
            }
        }

        self.tools.update({
            "run_tests": {
                "function": self.run_tests,
                "declaration": {
                    "name": "run_tests",
                    "description": "Run project tests and return structured pass/fail output with failing locations",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "command": {
                                "type": "STRING",
                                "description": "Optional test command (for example: 'pytest -q' or 'cargo test')"
                            },
                            "path": {
                                "type": "STRING",
                                "description": "Project directory (defaults to current directory)"
                            },
                            "timeout": {
                                "type": "INTEGER",
                                "description": "Timeout in seconds (default 300)"
                            }
                        },
                        "required": []
                    }
                }
            },
            "git_status_diff": {
                "function": self.git_status_diff,
                "declaration": {
                    "name": "git_status_diff",
                    "description": "Summarize git status plus staged/unstaged diff stats and risk hints",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Repository path (defaults to current directory)"
                            },
                            "include_untracked": {
                                "type": "BOOLEAN",
                                "description": "Include untracked files in status summary (default true)"
                            }
                        },
                        "required": []
                    }
                }
            },
            "apply_patch_unified": {
                "function": self.apply_patch_unified,
                "declaration": {
                    "name": "apply_patch_unified",
                    "description": "Validate and apply a unified diff patch via git apply",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "patch": {
                                "type": "STRING",
                                "description": "Unified diff patch content"
                            },
                            "path": {
                                "type": "STRING",
                                "description": "Repository path (defaults to current directory)"
                            },
                            "check_only": {
                                "type": "BOOLEAN",
                                "description": "If true, validate patch without applying it"
                            }
                        },
                        "required": ["patch"]
                    }
                }
            },
            "format_and_lint": {
                "function": self.format_and_lint,
                "declaration": {
                    "name": "format_and_lint",
                    "description": "Run available formatters/linters and return structured results",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Project directory (defaults to current directory)"
                            },
                            "fix": {
                                "type": "BOOLEAN",
                                "description": "Auto-fix format/lint issues when supported (default true)"
                            },
                            "timeout": {
                                "type": "INTEGER",
                                "description": "Timeout per command in seconds (default 300)"
                            }
                        },
                        "required": []
                    }
                }
            },
            "dependency_inspect": {
                "function": self.dependency_inspect,
                "declaration": {
                    "name": "dependency_inspect",
                    "description": "Inspect project dependencies, installed versions, and outdated packages when available",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Project directory (defaults to current directory)"
                            }
                        },
                        "required": []
                    }
                }
            },
            "fetch_url": {
                "function": self.fetch_url,
                "declaration": {
                    "name": "fetch_url",
                    "description": "Fetch and summarize content from an HTTP(S) URL with SSRF safeguards",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "url": {
                                "type": "STRING",
                                "description": "HTTP or HTTPS URL to fetch"
                            },
                            "timeout": {
                                "type": "INTEGER",
                                "description": "Timeout in seconds (default 20)"
                            },
                            "max_chars": {
                                "type": "INTEGER",
                                "description": "Maximum characters to return from page text (default 12000)"
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            "json_yaml_edit": {
                "function": self.json_yaml_edit,
                "declaration": {
                    "name": "json_yaml_edit",
                    "description": "Edit JSON/YAML files using dotted-path updates",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file_path": {
                                "type": "STRING",
                                "description": "Path to JSON or YAML file"
                            },
                            "updates_json": {
                                "type": "STRING",
                                "description": "JSON object mapping dotted paths to new values"
                            },
                            "create_missing": {
                                "type": "BOOLEAN",
                                "description": "Create missing nested objects for dotted paths (default true)"
                            }
                        },
                        "required": ["file_path", "updates_json"]
                    }
                }
            },
            "process_logs": {
                "function": self.process_logs,
                "declaration": {
                    "name": "process_logs",
                    "description": "Analyze log files and summarize levels, frequent errors, and likely root cause",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {
                                "type": "STRING",
                                "description": "Log file or directory (defaults to current directory)"
                            },
                            "pattern": {
                                "type": "STRING",
                                "description": "Optional regex filter applied to log lines"
                            },
                            "max_lines": {
                                "type": "INTEGER",
                                "description": "Maximum lines to analyze (default 5000)"
                            }
                        },
                        "required": []
                    }
                }
            },
        })

        if shutil.which("gh"):
            self.tools.update({
                "gh_pr_list": {
                    "function": self.gh_pr_list,
                    "declaration": {
                        "name": "gh_pr_list",
                        "description": "List GitHub pull requests",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "state": {"type": "STRING", "description": "PR state: open, closed, merged"},
                                "limit": {"type": "INTEGER", "description": "Maximum number of PRs"}
                            },
                            "required": []
                        }
                    }
                },
                "gh_pr_view": {
                    "function": self.gh_pr_view,
                    "declaration": {
                        "name": "gh_pr_view",
                        "description": "View details for a GitHub pull request",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "number": {"type": "INTEGER", "description": "Pull request number"}
                            },
                            "required": ["number"]
                        }
                    }
                },
                "gh_issue_list": {
                    "function": self.gh_issue_list,
                    "declaration": {
                        "name": "gh_issue_list",
                        "description": "List GitHub issues",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "state": {"type": "STRING", "description": "Issue state: open or closed"},
                                "limit": {"type": "INTEGER", "description": "Maximum number of issues"}
                            },
                            "required": []
                        }
                    }
                },
                "gh_issue_view": {
                    "function": self.gh_issue_view,
                    "declaration": {
                        "name": "gh_issue_view",
                        "description": "View details for a GitHub issue",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "number": {"type": "INTEGER", "description": "Issue number"}
                            },
                            "required": ["number"]
                        }
                    }
                },
                "gh_pr_create": {
                    "function": self.gh_pr_create,
                    "declaration": {
                        "name": "gh_pr_create",
                        "description": "Create a GitHub pull request",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING", "description": "Pull request title"},
                                "body": {"type": "STRING", "description": "Pull request description/body"},
                                "base": {"type": "STRING", "description": "Base branch"}
                            },
                            "required": ["title", "body"]
                        }
                    }
                },
                "gh_pr_comment": {
                    "function": self.gh_pr_comment,
                    "declaration": {
                        "name": "gh_pr_comment",
                        "description": "Comment on a GitHub pull request",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "number": {"type": "INTEGER", "description": "Pull request number"},
                                "body": {"type": "STRING", "description": "Comment text"}
                            },
                            "required": ["number", "body"]
                        }
                    }
                },
            })

        self.tools["web_search"] = {
            "function": self.web_search,
            "declaration": {
                "name": "web_search",
                "description": "Search the web for current information. Returns titles, URLs, and snippets.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING", "description": "Search query"}
                    },
                    "required": ["query"]
                }
            }
        }

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Get tool declarations for API"""
        return [tool["declaration"] for tool in self.tools.values()]

    def register_external_tool(
        self,
        name: str,
        function: Any,
        declaration: Dict[str, Any]
    ) -> None:
        """Register an externally provided async tool function."""
        self.tools[name] = {
            "function": function,
            "declaration": declaration,
        }

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
                raise ToolExecutionError(tool_name, f"Unknown tool: {tool_name}")

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
            raise ToolExecutionError(tool_name, f"Tool execution failed: {str(e)}")

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
            raise ToolExecutionError("glob_files", f"Glob search failed: {str(e)}")

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
            raise ToolExecutionError("grep_files", f"Grep search failed: {str(e)}")

    async def _read_stream_with_limit(
        self,
        stream: Optional[asyncio.StreamReader],
        max_bytes: int,
    ) -> Tuple[bytes, bool]:
        """Read a process stream with bounded capture to avoid memory blowups."""
        if stream is None:
            return b"", False

        chunks: List[bytes] = []
        captured = 0
        truncated = False

        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break

            if captured < max_bytes:
                remaining = max_bytes - captured
                if len(chunk) > remaining:
                    truncated = True
                to_store = chunk[:remaining]
                chunks.append(to_store)
                captured += len(to_store)
            else:
                truncated = True

        return b"".join(chunks), truncated

    def _resolve_directory(self, path: Optional[str]) -> Path:
        """Resolve and validate a working directory."""
        if path:
            return validate_file_path(path, must_exist=True, must_be_dir=True)
        return Path.cwd()

    async def _run_command_capture(
        self,
        argv: List[str],
        timeout: int = 60,
        cwd: Optional[str] = None,
        stdin_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run command without shell and capture bounded stdout/stderr."""
        if not argv:
            raise ValidationError("Command argv cannot be empty")

        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if stdin_text is not None and process.stdin is not None:
            process.stdin.write(stdin_text.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()

        stdout_task = asyncio.create_task(
            self._read_stream_with_limit(
                process.stdout,
                self.MAX_CAPTURED_OUTPUT_BYTES,
            )
        )
        stderr_task = asyncio.create_task(
            self._read_stream_with_limit(
                process.stderr,
                self.MAX_CAPTURED_OUTPUT_BYTES,
            )
        )

        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            process.kill()
            await process.wait()

        stdout_bytes, stdout_truncated = await stdout_task
        stderr_bytes, stderr_truncated = await stderr_task

        return {
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }

    def _infer_test_command(self, work_dir: Path) -> Optional[List[str]]:
        """Infer a suitable default test command for a project directory."""
        pyproject = work_dir / "pyproject.toml"
        tests_dir = work_dir / "tests"
        cargo_toml = work_dir / "Cargo.toml"
        package_json = work_dir / "package.json"

        if (tests_dir.exists() or pyproject.exists()) and shutil.which("pytest"):
            return ["pytest", "tests/", "-v"]
        if cargo_toml.exists() and shutil.which("cargo"):
            return ["cargo", "test"]
        if package_json.exists() and shutil.which("npm"):
            return ["npm", "test", "--silent"]
        return None

    @staticmethod
    def _extract_failure_locations(text: str) -> List[Dict[str, Any]]:
        """Extract file/line hints from test/lint output."""
        locations: List[Dict[str, Any]] = []
        seen = set()
        pattern = re.compile(
            r"(?P<file>[A-Za-z0-9_./\-]+\.(?:py|rs|js|ts|tsx|jsx|go|java|kt|c|cpp|hpp|h|rb|php|swift|scala|lua|sh|yaml|yml|toml|json)):(?P<line>\d+)(?::(?P<col>\d+))?"
        )

        for match in pattern.finditer(text):
            file_path = match.group("file")
            line = int(match.group("line"))
            col_str = match.group("col")
            column = int(col_str) if col_str else None
            key = (file_path, line, column)
            if key in seen:
                continue
            seen.add(key)
            locations.append(
                {
                    "file": file_path,
                    "line": line,
                    "column": column,
                }
            )
            if len(locations) >= 20:
                break
        return locations

    @staticmethod
    def _strip_html(html: str) -> str:
        """Reduce HTML to plain text for compact retrieval."""
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_package_name(raw_name: str) -> str:
        """Normalize package names for metadata lookups."""
        return re.sub(r"[-_.]+", "-", raw_name).lower()

    def _parse_requirement_name(self, line: str) -> Optional[str]:
        """Extract package name from a requirements line."""
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("-r")
            or stripped.startswith("--")
            or stripped.startswith("git+")
        ):
            return None
        name = re.split(r"[<>=!~\[\s]", stripped, maxsplit=1)[0]
        return self._normalize_package_name(name) if name else None

    def _load_pyproject_dependencies(self, pyproject_path: Path) -> Dict[str, str]:
        """Load dependency declarations from pyproject.toml when parser is available."""
        parser = tomllib or tomli
        if parser is None:
            return {}
        try:
            data = parser.loads(pyproject_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        discovered: Dict[str, str] = {}
        project_data = data.get("project", {})
        dep_lists = []
        dep_lists.extend(project_data.get("dependencies", []) or [])
        optional = project_data.get("optional-dependencies", {}) or {}
        for extra_deps in optional.values():
            dep_lists.extend(extra_deps or [])

        for dep in dep_lists:
            if not isinstance(dep, str):
                continue
            name = self._parse_requirement_name(dep)
            if name and name not in discovered:
                discovered[name] = dep
        return discovered

    @staticmethod
    def _is_host_public(host: str) -> bool:
        """Check whether host resolves to public addresses only."""
        lowered = host.lower()
        if lowered in {"localhost", "127.0.0.1", "::1"} or lowered.endswith(".local"):
            return False

        try:
            ip = ipaddress.ip_address(host)
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            )
        except ValueError:
            pass

        try:
            resolved = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False

        for entry in resolved:
            addr = entry[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            ):
                return False
        return True

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

            security_cfg = getattr(getattr(self, "config", None), "security", None)
            timeout_ceiling = getattr(security_cfg, "max_bash_timeout_seconds", None)
            if isinstance(timeout_ceiling, int) and timeout_ceiling > 0:
                timeout = min(timeout, timeout_ceiling)

            validation = self.command_validator.validate(command)
            if not validation.is_safe:
                warning_text = "; ".join(validation.warnings) if validation.warnings else "Unsafe command blocked"
                suggestion_text = (
                    f" Suggested alternative: {validation.suggested_alternative}"
                    if validation.suggested_alternative
                    else ""
                )
                raise CommandExecutionError(
                    command,
                    (
                        f"Command blocked by validator "
                        f"(risk={validation.risk_level.value}): {warning_text}{suggestion_text}"
                    ),
                )

            if validation.warnings:
                logger.warning(
                    "Validator warnings for command '%s': %s",
                    command,
                    "; ".join(validation.warnings),
                )

            argv = shlex.split(command)
            if not argv:
                raise CommandExecutionError(command, "Command is empty after parsing")

            # Create subprocess asynchronously without shell interpolation.
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_task = asyncio.create_task(
                self._read_stream_with_limit(
                    process.stdout,
                    self.MAX_CAPTURED_OUTPUT_BYTES,
                )
            )
            stderr_task = asyncio.create_task(
                self._read_stream_with_limit(
                    process.stderr,
                    self.MAX_CAPTURED_OUTPUT_BYTES,
                )
            )

            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise CommandExecutionError(
                    command,
                    f"Command timed out after {timeout} seconds",
                )

            stdout_bytes, stdout_truncated = await stdout_task
            stderr_bytes, stderr_truncated = await stderr_task

            # Decode output
            stdout_text = stdout_bytes.decode('utf-8', errors='replace')
            stderr_text = stderr_bytes.decode('utf-8', errors='replace')

            truncation_notes: List[str] = []
            if stdout_truncated:
                truncation_notes.append(f"stdout truncated at {self.MAX_CAPTURED_OUTPUT_BYTES} bytes")
            if stderr_truncated:
                truncation_notes.append(f"stderr truncated at {self.MAX_CAPTURED_OUTPUT_BYTES} bytes")
            truncation_suffix = (
                "\n[Output truncated: " + ", ".join(truncation_notes) + "]"
                if truncation_notes
                else ""
            )

            if process.returncode != 0:
                error_msg = stderr_text or stdout_text or "Command failed"
                error_msg += truncation_suffix
                raise CommandExecutionError(
                    command,
                    f"Command failed with exit code {process.returncode}: {error_msg}",
                    return_code=process.returncode,
                )

            result = (stdout_text or "(No output)") + truncation_suffix
            logger.info(f"Bash command completed successfully")
            return result

        except CommandExecutionError:
            raise
        except Exception as e:
            raise CommandExecutionError(command, f"Failed to execute command: {str(e)}")

    async def list_directory(self, path: Optional[str] = None, show_hidden: bool = False) -> str:
        """List directory contents with metadata

        Args:
            path: Directory path (defaults to current)
            show_hidden: Show hidden files

        Returns:
            Directory listing

        Raises:
            FileOperationError: If listing fails
        """
        try:
            dir_path = path or os.getcwd()

            if not os.path.isdir(dir_path):
                raise FileOperationError(f"Not a directory: {dir_path}")

            # Get directory entries
            entries = []
            for entry in os.listdir(dir_path):
                if not show_hidden and entry.startswith('.'):
                    continue

                full_path = os.path.join(dir_path, entry)
                stat = os.stat(full_path)

                # Format size
                size = stat.st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f}MB"

                # Get type
                if os.path.isdir(full_path):
                    type_str = "DIR"
                elif os.path.islink(full_path):
                    type_str = "LINK"
                else:
                    type_str = "FILE"

                entries.append(f"{type_str:6} {size_str:10} {entry}")

            result = f"Contents of {dir_path}:\n" + "\n".join(sorted(entries))
            logger.info(f"Listed directory: {dir_path}")
            return result

        except Exception as e:
            raise FileOperationError(f"Failed to list directory: {str(e)}")

    async def copy_file(self, source: str, destination: str) -> str:
        """Copy file to another location

        Args:
            source: Source file path
            destination: Destination file path

        Returns:
            Success message

        Raises:
            FileOperationError: If copy fails
        """
        try:
            source = validate_file_path(source, must_exist=True, must_be_file=True)
            destination = validate_file_path(destination, must_exist=False)

            # Read source
            async with aiofiles.open(source, 'rb') as f:
                content = await f.read()

            # Write destination
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(destination, 'wb') as f:
                await f.write(content)

            logger.info(f"Copied {source} to {destination}")
            return f"Successfully copied {source} to {destination}"

        except Exception as e:
            raise FileOperationError(f"Failed to copy file: {str(e)}")

    async def move_file(self, source: str, destination: str) -> str:
        """Move or rename file

        Args:
            source: Source file path
            destination: Destination file path

        Returns:
            Success message

        Raises:
            FileOperationError: If move fails
        """
        try:
            source = validate_file_path(source, must_exist=True)
            destination = validate_file_path(destination, must_exist=False)

            # Create destination directory if needed
            Path(destination).parent.mkdir(parents=True, exist_ok=True)

            # Move file
            await asyncio.to_thread(os.rename, source, destination)

            logger.info(f"Moved {source} to {destination}")
            return f"Successfully moved {source} to {destination}"

        except Exception as e:
            raise FileOperationError(f"Failed to move file: {str(e)}")

    async def delete_file(self, file_path: str) -> str:
        """Delete a file

        Args:
            file_path: Path to file

        Returns:
            Success message

        Raises:
            FileOperationError: If delete fails
        """
        try:
            file_path = validate_file_path(file_path, must_exist=True, must_be_file=True)

            # Delete file
            await asyncio.to_thread(os.remove, file_path)

            logger.info(f"Deleted file: {file_path}")
            return f"Successfully deleted {file_path}"

        except Exception as e:
            raise FileOperationError(f"Failed to delete file: {str(e)}")

    async def diff_files(self, file1: str, file2: str) -> str:
        """Compare two files and show differences

        Args:
            file1: First file path
            file2: Second file path

        Returns:
            Diff output

        Raises:
            FileOperationError: If diff fails
        """
        try:
            import difflib

            file1 = validate_file_path(file1, must_exist=True, must_be_file=True)
            file2 = validate_file_path(file2, must_exist=True, must_be_file=True)

            # Read both files
            async with aiofiles.open(file1, 'r', encoding='utf-8') as f:
                content1 = (await f.read()).splitlines(keepends=True)

            async with aiofiles.open(file2, 'r', encoding='utf-8') as f:
                content2 = (await f.read()).splitlines(keepends=True)

            # Generate diff
            diff = difflib.unified_diff(content1, content2, fromfile=file1, tofile=file2)
            result = ''.join(diff)

            if not result:
                return "Files are identical"

            logger.info(f"Generated diff between {file1} and {file2}")
            return result

        except Exception as e:
            raise FileOperationError(f"Failed to diff files: {str(e)}")

    async def git_status(self, path: Optional[str] = None) -> str:
        """Get git repository status

        Args:
            path: Repository path

        Returns:
            Git status output

        Raises:
            CommandExecutionError: If git command fails
        """
        command = "git status"
        try:
            work_dir = path or os.getcwd()
            command = f"cd {work_dir} && git status"

            result = await self.bash(command, timeout=30)
            return result

        except Exception as e:
            raise CommandExecutionError(command, f"Git status failed: {str(e)}")

    async def git_diff(self, path: Optional[str] = None, file_path: Optional[str] = None) -> str:
        """Show git differences

        Args:
            path: Repository path
            file_path: Specific file to diff

        Returns:
            Git diff output

        Raises:
            CommandExecutionError: If git command fails
        """
        command = "git diff"
        try:
            work_dir = path or os.getcwd()
            file_arg = file_path if file_path else ""
            command = f"cd {work_dir} && git diff {file_arg}"

            result = await self.bash(command, timeout=30)
            return result if result.strip() else "No changes"

        except Exception as e:
            raise CommandExecutionError(command, f"Git diff failed: {str(e)}")

    async def create_directory(self, path: str) -> str:
        """Create a new directory

        Args:
            path: Directory path to create

        Returns:
            Success message

        Raises:
            FileOperationError: If creation fails
        """
        try:
            path = validate_file_path(path, must_exist=False)

            # Create directory
            Path(path).mkdir(parents=True, exist_ok=True)

            logger.info(f"Created directory: {path}")
            return f"Successfully created directory {path}"

        except Exception as e:
            raise FileOperationError(f"Failed to create directory: {str(e)}")

    async def run_tests(
        self,
        command: Optional[str] = None,
        path: Optional[str] = None,
        timeout: int = 300,
    ) -> str:
        """Run project tests and return structured results."""
        try:
            work_dir = self._resolve_directory(path)
            argv = shlex.split(command) if command else self._infer_test_command(work_dir)
            if not argv:
                raise ToolExecutionError(
                    "run_tests",
                    "Could not infer a test command. Provide `command`, for example `pytest -q`."
                )

            started = time.time()
            result = await self._run_command_capture(
                argv=argv,
                timeout=timeout,
                cwd=str(work_dir),
            )
            duration = round(time.time() - started, 2)

            combined_output = "\n".join(
                part for part in [result["stdout"], result["stderr"]] if part
            )
            payload = {
                "ok": (not result["timed_out"]) and result["exit_code"] == 0,
                "command": " ".join(argv),
                "working_directory": str(work_dir),
                "duration_seconds": duration,
                "timed_out": result["timed_out"],
                "exit_code": result["exit_code"],
                "failing_locations": self._extract_failure_locations(combined_output),
                "output_excerpt": combined_output[:6000],
            }
            return json.dumps(payload, indent=2)
        except (ValidationError, ToolExecutionError):
            raise
        except Exception as e:
            raise ToolExecutionError("run_tests", f"Failed to run tests: {str(e)}")

    async def git_status_diff(
        self,
        path: Optional[str] = None,
        include_untracked: bool = True,
    ) -> str:
        """Summarize repository status and diff statistics."""
        try:
            work_dir = self._resolve_directory(path)

            root_check = await self._run_command_capture(
                ["git", "rev-parse", "--show-toplevel"],
                timeout=15,
                cwd=str(work_dir),
            )
            if root_check["exit_code"] != 0:
                raise ToolExecutionError(
                    "git_status_diff",
                    root_check["stderr"].strip() or "Not a git repository"
                )
            repo_root = root_check["stdout"].strip()

            status_args = ["git", "status", "--short"]
            if not include_untracked:
                status_args.append("--untracked-files=no")
            status_result = await self._run_command_capture(
                status_args,
                timeout=20,
                cwd=str(work_dir),
            )
            unstaged_stat = await self._run_command_capture(
                ["git", "diff", "--stat"],
                timeout=20,
                cwd=str(work_dir),
            )
            staged_stat = await self._run_command_capture(
                ["git", "diff", "--cached", "--stat"],
                timeout=20,
                cwd=str(work_dir),
            )
            shortstat_unstaged = await self._run_command_capture(
                ["git", "diff", "--shortstat"],
                timeout=20,
                cwd=str(work_dir),
            )
            shortstat_staged = await self._run_command_capture(
                ["git", "diff", "--cached", "--shortstat"],
                timeout=20,
                cwd=str(work_dir),
            )

            status_lines = [
                line for line in status_result["stdout"].splitlines() if line.strip()
            ]
            changed_files: List[str] = []
            for line in status_lines:
                if len(line) < 4:
                    continue
                file_part = line[3:].strip()
                if " -> " in file_part:
                    file_part = file_part.split(" -> ", maxsplit=1)[-1].strip()
                if file_part:
                    changed_files.append(file_part)

            risk_hints: List[str] = []
            for file_path in changed_files:
                lowered = file_path.lower()
                if lowered.startswith(".github/workflows/"):
                    risk_hints.append(f"{file_path}: CI/workflow behavior changed")
                if lowered in {"dockerfile", "compose.yml", "docker-compose.yml"}:
                    risk_hints.append(f"{file_path}: deployment/runtime behavior may change")
                if lowered.endswith((".sql", ".db", ".sqlite")):
                    risk_hints.append(f"{file_path}: data migration/storage impact possible")
                if "auth" in lowered or "security" in lowered or ".env" in lowered:
                    risk_hints.append(f"{file_path}: security-sensitive surface touched")

            payload = {
                "repository_root": repo_root,
                "working_directory": str(work_dir),
                "changed_file_count": len(changed_files),
                "changed_files": changed_files,
                "status_porcelain": status_lines,
                "unstaged_diff_stat": (unstaged_stat["stdout"] or "").strip(),
                "staged_diff_stat": (staged_stat["stdout"] or "").strip(),
                "unstaged_shortstat": (shortstat_unstaged["stdout"] or "").strip(),
                "staged_shortstat": (shortstat_staged["stdout"] or "").strip(),
                "risk_hints": risk_hints[:15],
            }
            return json.dumps(payload, indent=2)
        except (ValidationError, ToolExecutionError):
            raise
        except Exception as e:
            raise ToolExecutionError("git_status_diff", f"Failed to summarize git status/diff: {str(e)}")

    async def apply_patch_unified(
        self,
        patch: str,
        path: Optional[str] = None,
        check_only: bool = False,
    ) -> str:
        """Validate and apply a unified patch using git apply."""
        if not patch or not patch.strip():
            raise ValidationError("Patch content cannot be empty")
        if not shutil.which("git"):
            raise ToolExecutionError("apply_patch_unified", "`git` is required for apply_patch_unified")

        work_dir = self._resolve_directory(path)
        patch_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".patch",
                prefix="poor_cli_",
                delete=False,
                dir=str(work_dir),
            ) as handle:
                handle.write(patch)
                patch_file = handle.name

            check_result = await self._run_command_capture(
                ["git", "apply", "--check", patch_file],
                timeout=60,
                cwd=str(work_dir),
            )
            if check_result["timed_out"]:
                raise ToolExecutionError("apply_patch_unified", "Patch validation timed out")
            if check_result["exit_code"] != 0:
                details = (check_result["stderr"] or check_result["stdout"]).strip()
                raise ToolExecutionError("apply_patch_unified", f"Patch validation failed: {details}")

            if check_only:
                return json.dumps(
                    {
                        "ok": True,
                        "check_only": True,
                        "message": "Patch validation successful",
                    },
                    indent=2,
                )

            apply_result = await self._run_command_capture(
                ["git", "apply", "--verbose", patch_file],
                timeout=120,
                cwd=str(work_dir),
            )
            if apply_result["timed_out"]:
                raise ToolExecutionError("apply_patch_unified", "Patch application timed out")
            if apply_result["exit_code"] != 0:
                details = (apply_result["stderr"] or apply_result["stdout"]).strip()
                raise ToolExecutionError("apply_patch_unified", f"Patch apply failed: {details}")

            return json.dumps(
                {
                    "ok": True,
                    "check_only": False,
                    "message": "Patch applied successfully",
                    "stdout": apply_result["stdout"].strip(),
                },
                indent=2,
            )
        finally:
            if patch_file and os.path.exists(patch_file):
                os.remove(patch_file)

    async def format_and_lint(
        self,
        path: Optional[str] = None,
        fix: bool = True,
        timeout: int = 300,
    ) -> str:
        """Run available formatter/linter commands with structured output."""
        try:
            work_dir = self._resolve_directory(path)
            target = str(work_dir)
            commands: List[Tuple[str, List[str]]] = []

            if shutil.which("black"):
                black_cmd = ["black", target]
                if not fix:
                    black_cmd = ["black", "--check", target]
                commands.append(("black", black_cmd))

            if shutil.which("ruff"):
                ruff_cmd = ["ruff", "check", target]
                if fix:
                    ruff_cmd.insert(2, "--fix")
                commands.append(("ruff", ruff_cmd))

            if shutil.which("mypy"):
                mypy_target = "poor_cli" if (work_dir / "poor_cli").exists() else target
                commands.append(("mypy", ["mypy", mypy_target, "--no-error-summary"]))

            if not commands:
                raise ToolExecutionError(
                    "format_and_lint",
                    "No formatter/linter tools found in PATH (expected black/ruff/mypy)."
                )

            results = []
            overall_ok = True
            for name, argv in commands:
                command_result = await self._run_command_capture(
                    argv=argv,
                    timeout=timeout,
                    cwd=str(work_dir),
                )
                ok = (not command_result["timed_out"]) and command_result["exit_code"] == 0
                overall_ok = overall_ok and ok
                results.append(
                    {
                        "tool": name,
                        "command": " ".join(argv),
                        "ok": ok,
                        "exit_code": command_result["exit_code"],
                        "timed_out": command_result["timed_out"],
                        "stdout_excerpt": command_result["stdout"][:3000],
                        "stderr_excerpt": command_result["stderr"][:3000],
                    }
                )

            return json.dumps(
                {
                    "ok": overall_ok,
                    "working_directory": str(work_dir),
                    "fix_mode": fix,
                    "results": results,
                },
                indent=2,
            )
        except (ValidationError, ToolExecutionError):
            raise
        except Exception as e:
            raise ToolExecutionError("format_and_lint", f"Failed to run format/lint: {str(e)}")

    async def dependency_inspect(self, path: Optional[str] = None) -> str:
        """Inspect dependency declarations and installed/outdated versions."""
        try:
            work_dir = self._resolve_directory(path)
            discovered: Dict[str, Dict[str, Any]] = {}

            for req_name in ("requirements.txt", "requirements-dev.txt"):
                req_path = work_dir / req_name
                if not req_path.exists():
                    continue
                lines = req_path.read_text(encoding="utf-8").splitlines()
                for raw_line in lines:
                    dep_name = self._parse_requirement_name(raw_line)
                    if not dep_name:
                        continue
                    discovered.setdefault(
                        dep_name,
                        {"name": dep_name, "sources": [], "declarations": []},
                    )
                    discovered[dep_name]["sources"].append(req_name)
                    discovered[dep_name]["declarations"].append(raw_line.strip())

            pyproject_path = work_dir / "pyproject.toml"
            if pyproject_path.exists():
                pyproject_deps = self._load_pyproject_dependencies(pyproject_path)
                for dep_name, declaration in pyproject_deps.items():
                    discovered.setdefault(
                        dep_name,
                        {"name": dep_name, "sources": [], "declarations": []},
                    )
                    discovered[dep_name]["sources"].append("pyproject.toml")
                    discovered[dep_name]["declarations"].append(declaration)

            outdated_map: Dict[str, Dict[str, str]] = {}
            pip_result = await self._run_command_capture(
                [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
                timeout=45,
                cwd=str(work_dir),
            )
            if not pip_result["timed_out"] and pip_result["exit_code"] == 0:
                try:
                    outdated_entries = json.loads(pip_result["stdout"] or "[]")
                    for entry in outdated_entries:
                        pkg_name = self._normalize_package_name(entry.get("name", ""))
                        if pkg_name:
                            outdated_map[pkg_name] = {
                                "installed_version": entry.get("version", ""),
                                "latest_version": entry.get("latest_version", ""),
                            }
                except json.JSONDecodeError:
                    pass

            dependency_rows = []
            for dep_name in sorted(discovered):
                declared = discovered[dep_name]
                try:
                    installed_version = importlib.metadata.version(dep_name)
                    installed = True
                except importlib.metadata.PackageNotFoundError:
                    installed_version = None
                    installed = False

                row: Dict[str, Any] = {
                    "name": dep_name,
                    "sources": sorted(set(declared["sources"])),
                    "declarations": declared["declarations"][:5],
                    "installed": installed,
                    "installed_version": installed_version,
                }
                if dep_name in outdated_map:
                    row["outdated"] = True
                    row["latest_version"] = outdated_map[dep_name]["latest_version"]
                else:
                    row["outdated"] = False
                dependency_rows.append(row)

            payload = {
                "working_directory": str(work_dir),
                "dependency_count": len(dependency_rows),
                "outdated_count": sum(1 for row in dependency_rows if row["outdated"]),
                "dependencies": dependency_rows,
            }
            return json.dumps(payload, indent=2)
        except Exception as e:
            raise ToolExecutionError("dependency_inspect", f"Failed to inspect dependencies: {str(e)}")

    async def fetch_url(self, url: str, timeout: int = 20, max_chars: int = 12000) -> str:
        """Fetch and summarize content from an HTTP(S) URL."""
        if not AIOHTTP_AVAILABLE:
            raise ToolExecutionError("fetch_url", "fetch_url requires aiohttp")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValidationError("Only http and https URLs are allowed")
        if not parsed.hostname:
            raise ValidationError("URL must include a valid hostname")
        if not self._is_host_public(parsed.hostname):
            raise ValidationError("Refusing to fetch local/private network addresses")

        timeout = max(timeout, 1)
        max_chars = max(max_chars, 200)

        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(url, allow_redirects=True) as response:
                    body = await response.text(errors="replace")
                    if response.status >= 400:
                        excerpt = body[:500].replace("\n", " ")
                        raise ToolExecutionError(
                            "fetch_url",
                            f"HTTP {response.status} fetching {url}: {excerpt}"
                        )

                    content_type = response.headers.get("Content-Type", "")
                    lowered_ct = content_type.lower()
                    title = ""
                    excerpt = body

                    if "html" in lowered_ct:
                        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
                        if title_match:
                            title = re.sub(r"\s+", " ", title_match.group(1)).strip()
                        excerpt = self._strip_html(body)
                    elif "json" in lowered_ct:
                        try:
                            excerpt = json.dumps(json.loads(body), indent=2)
                        except Exception:
                            excerpt = body

                    payload = {
                        "url": str(response.url),
                        "status": response.status,
                        "content_type": content_type,
                        "title": title,
                        "content_excerpt": excerpt[:max_chars],
                    }
                    return json.dumps(payload, indent=2)
        except asyncio.TimeoutError:
            raise ToolExecutionError("fetch_url", f"Timed out fetching URL after {timeout}s")
        except aiohttp.ClientError as e:
            raise ToolExecutionError("fetch_url", f"Network error fetching URL: {str(e)}")

    async def json_yaml_edit(
        self,
        file_path: str,
        updates_json: str,
        create_missing: bool = True,
    ) -> str:
        """Apply dotted-path updates to JSON/YAML files."""
        try:
            path_obj = validate_file_path(file_path, must_exist=True, must_be_file=True)
            suffix = path_obj.suffix.lower()
            if suffix not in {".json", ".yaml", ".yml"}:
                raise ValidationError("json_yaml_edit only supports .json/.yaml/.yml files")

            try:
                updates = json.loads(updates_json)
            except json.JSONDecodeError as e:
                raise ValidationError(f"updates_json must be valid JSON: {e}") from e

            if not isinstance(updates, dict) or not updates:
                raise ValidationError("updates_json must be a non-empty JSON object")

            raw_content = path_obj.read_text(encoding="utf-8")
            if suffix == ".json":
                document = json.loads(raw_content or "{}")
            else:
                if not YAML_AVAILABLE:
                    raise ToolExecutionError("json_yaml_edit", "PyYAML is required to edit YAML files")
                document = yaml.safe_load(raw_content) if raw_content.strip() else {}

            if document is None:
                document = {}
            if not isinstance(document, dict):
                raise ValidationError("Root document must be an object/dictionary")

            changed_paths = []
            for dotted_path, value in updates.items():
                if not isinstance(dotted_path, str) or not dotted_path.strip():
                    raise ValidationError("Update keys must be non-empty dotted paths")
                segments = [segment for segment in dotted_path.split(".") if segment]
                if not segments:
                    raise ValidationError(f"Invalid dotted path: {dotted_path}")

                cursor = document
                for segment in segments[:-1]:
                    existing = cursor.get(segment)
                    if existing is None:
                        if not create_missing:
                            raise ValidationError(
                                f"Missing path segment '{segment}' in '{dotted_path}'"
                            )
                        cursor[segment] = {}
                        existing = cursor[segment]
                    elif not isinstance(existing, dict):
                        if not create_missing:
                            raise ValidationError(
                                f"Path segment '{segment}' is not an object in '{dotted_path}'"
                            )
                        cursor[segment] = {}
                        existing = cursor[segment]
                    cursor = existing
                cursor[segments[-1]] = value
                changed_paths.append(dotted_path)

            if suffix == ".json":
                rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
            else:
                rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)

            path_obj.write_text(rendered, encoding="utf-8")
            return (
                f"Updated {path_obj} with {len(changed_paths)} changes: "
                + ", ".join(changed_paths[:15])
            )
        except (ValidationError, ToolExecutionError):
            raise
        except Exception as e:
            raise ToolExecutionError("json_yaml_edit", f"Failed to edit JSON/YAML file: {str(e)}")

    async def process_logs(
        self,
        path: Optional[str] = None,
        pattern: Optional[str] = None,
        max_lines: int = 5000,
    ) -> str:
        """Analyze log files and produce a concise diagnostic summary."""
        try:
            if max_lines <= 0:
                raise ValidationError("max_lines must be a positive integer")

            target = (
                validate_file_path(path, must_exist=True) if path else Path.cwd()
            )

            if target.is_file():
                files = [target]
            else:
                candidates: List[Path] = []
                for extension in ("*.log", "*.txt", "*.out"):
                    candidates.extend(target.rglob(extension))
                files = sorted({candidate for candidate in candidates if candidate.is_file()})

            if not files:
                raise ToolExecutionError("process_logs", "No log files found to process")

            regex = re.compile(pattern) if pattern else None
            per_file_budget = max(50, max_lines // max(len(files), 1))
            level_counts: Counter = Counter()
            error_signatures: Counter = Counter()
            signature_samples: Dict[str, str] = {}
            lines_analyzed = 0
            files_analyzed: List[str] = []

            for log_file in files[:25]:
                try:
                    async with aiofiles.open(
                        log_file,
                        "r",
                        encoding="utf-8",
                        errors="ignore",
                    ) as handle:
                        lines = await handle.readlines()
                except Exception:
                    continue

                tail_lines = lines[-per_file_budget:]
                files_analyzed.append(str(log_file))

                for raw_line in tail_lines:
                    line = raw_line.strip()
                    if not line:
                        continue
                    if regex and not regex.search(line):
                        continue

                    lines_analyzed += 1
                    lowered = line.lower()
                    if "error" in lowered or "exception" in lowered or "traceback" in lowered:
                        level_counts["error"] += 1
                        signature = re.sub(r"\d+", "<num>", line)
                        signature = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", signature, flags=re.IGNORECASE)
                        error_signatures[signature] += 1
                        signature_samples.setdefault(signature, line[:240])
                    elif "warn" in lowered:
                        level_counts["warning"] += 1
                    elif "info" in lowered:
                        level_counts["info"] += 1
                    elif "debug" in lowered:
                        level_counts["debug"] += 1
                    else:
                        level_counts["other"] += 1

            top_errors = []
            for signature, count in error_signatures.most_common(5):
                top_errors.append(
                    {
                        "signature": signature,
                        "count": count,
                        "sample": signature_samples.get(signature, ""),
                    }
                )

            likely_root_cause = top_errors[0]["sample"] if top_errors else ""

            payload = {
                "files_analyzed": files_analyzed,
                "lines_analyzed": lines_analyzed,
                "level_counts": dict(level_counts),
                "top_errors": top_errors,
                "likely_root_cause": likely_root_cause,
            }
            return json.dumps(payload, indent=2)
        except re.error as e:
            raise ValidationError(f"Invalid regex pattern: {e}") from e
        except (ValidationError, ToolExecutionError):
            raise
        except Exception as e:
            raise ToolExecutionError("process_logs", f"Failed to process logs: {str(e)}")

    async def gh_pr_list(self, state: str = "open", limit: int = 10) -> str:
        from .github_tools import gh_pr_list
        return await gh_pr_list(state=state, limit=limit)

    async def gh_pr_view(self, number: int) -> str:
        from .github_tools import gh_pr_view
        return await gh_pr_view(number=number)

    async def gh_issue_list(self, state: str = "open", limit: int = 10) -> str:
        from .github_tools import gh_issue_list
        return await gh_issue_list(state=state, limit=limit)

    async def gh_issue_view(self, number: int) -> str:
        from .github_tools import gh_issue_view
        return await gh_issue_view(number=number)

    async def gh_pr_create(self, title: str, body: str, base: str = "main") -> str:
        from .github_tools import gh_pr_create
        return await gh_pr_create(title=title, body=body, base=base)

    async def gh_pr_comment(self, number: int, body: str) -> str:
        from .github_tools import gh_pr_comment
        return await gh_pr_comment(number=number, body=body)

    async def web_search(self, query: str) -> str:
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
        if api_key:
            from .web_search import brave_search
            return await brave_search(query=query, api_key=api_key, count=5)

        from .web_search import duckduckgo_search
        return await duckduckgo_search(query=query, count=5)
