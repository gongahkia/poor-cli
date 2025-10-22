"""
Tool implementations for poor-cli
"""

import os
import subprocess
import glob as glob_module
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


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
                    "description": "Write content to a file (creates new or overwrites existing)",
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
            return f"Error: Unknown tool '{tool_name}'"

        try:
            result = self.tools[tool_name]["function"](**args)
            return result
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    # Tool implementations

    def read_file(self, file_path: str, start_line: Optional[int] = None,
                  end_line: Optional[int] = None) -> str:
        """Read file contents"""
        try:
            path = Path(file_path).expanduser().resolve()

            if not path.exists():
                return f"Error: File not found: {file_path}"

            if not path.is_file():
                return f"Error: Not a file: {file_path}"

            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if start_line is not None or end_line is not None:
                start = (start_line - 1) if start_line else 0
                end = end_line if end_line else len(lines)
                lines = lines[start:end]

            # Add line numbers
            numbered_lines = [f"{i+1:4d}  {line}" for i, line in enumerate(lines,
                             start=(start_line-1 if start_line else 0))]

            return "".join(numbered_lines)

        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, file_path: str, content: str) -> str:
        """Write content to file"""
        try:
            path = Path(file_path).expanduser().resolve()

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            return f"Successfully wrote to {file_path}"

        except Exception as e:
            return f"Error writing file: {str(e)}"

    def edit_file(self, file_path: str, new_text: str, old_text: Optional[str] = None,
                  start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Edit file using string replacement or line-based editing"""
        try:
            path = Path(file_path).expanduser().resolve()

            if not path.exists():
                return f"Error: File not found: {file_path}"

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines(keepends=True)

            # String replacement mode
            if old_text is not None:
                if old_text not in content:
                    return f"Error: Text not found in file: {old_text[:50]}..."

                new_content = content.replace(old_text, new_text)

            # Line-based editing mode
            elif start_line is not None and end_line is not None:
                if start_line < 1 or end_line > len(lines) or start_line > end_line:
                    return f"Error: Invalid line range {start_line}-{end_line}"

                new_lines = lines[:start_line-1] + [new_text + '\n'] + lines[end_line:]
                new_content = "".join(new_lines)

            else:
                return "Error: Must provide either old_text or start_line/end_line"

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return f"Successfully edited {file_path}"

        except Exception as e:
            return f"Error editing file: {str(e)}"

    def glob_files(self, pattern: str, path: Optional[str] = None) -> str:
        """Find files matching glob pattern"""
        try:
            search_path = Path(path).expanduser().resolve() if path else Path.cwd()

            if not search_path.exists():
                return f"Error: Path not found: {path}"

            matches = list(search_path.glob(pattern))

            if not matches:
                return f"No files found matching pattern: {pattern}"

            # Sort by modification time (newest first)
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            result = f"Found {len(matches)} file(s):\n"
            for match in matches[:100]:  # Limit to 100 results
                result += f"  {match}\n"

            if len(matches) > 100:
                result += f"  ... and {len(matches) - 100} more\n"

            return result

        except Exception as e:
            return f"Error in glob search: {str(e)}"

    def grep_files(self, pattern: str, path: Optional[str] = None,
                   file_pattern: Optional[str] = None,
                   case_sensitive: bool = True) -> str:
        """Search for pattern in files"""
        try:
            search_path = Path(path).expanduser().resolve() if path else Path.cwd()

            if not search_path.exists():
                return f"Error: Path not found: {path}"

            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)

            results = []

            if search_path.is_file():
                files = [search_path]
            else:
                # Get all files matching file_pattern
                if file_pattern:
                    files = list(search_path.glob(f"**/{file_pattern}"))
                else:
                    files = [f for f in search_path.rglob("*") if f.is_file()]

            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{line_num}: {line.rstrip()}")

                                if len(results) >= 100:  # Limit results
                                    break
                except (UnicodeDecodeError, PermissionError):
                    continue

                if len(results) >= 100:
                    break

            if not results:
                return f"No matches found for pattern: {pattern}"

            result = f"Found {len(results)} match(es):\n"
            result += "\n".join(results)

            return result

        except Exception as e:
            return f"Error in grep search: {str(e)}"

    def bash(self, command: str, timeout: int = 120) -> str:
        """Execute bash command"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd()
            )

            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"

            if result.returncode != 0:
                output += f"\n\nCommand exited with code {result.returncode}"

            return output or "Command completed with no output"

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"
