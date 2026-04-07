"""
Async tool implementations for poor-cli
"""

import os
import asyncio
import signal
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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
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
from .sandbox import ToolCapability, declaration_capabilities, tool_capability_metadata

# Setup logger
logger = setup_logger(__name__)

DEFAULT_TOOL_CAPABILITIES: Dict[str, List[str]] = {
    "read_file": [ToolCapability.FILESYSTEM_READ.value],
    "write_file": [ToolCapability.FILESYSTEM_WRITE.value],
    "edit_file": [ToolCapability.FILESYSTEM_WRITE.value],
    "glob_files": [ToolCapability.FILESYSTEM_READ.value],
    "grep_files": [ToolCapability.FILESYSTEM_READ.value],
    "bash": [ToolCapability.PROCESS_EXECUTE.value],
    "list_directory": [ToolCapability.FILESYSTEM_READ.value],
    "copy_file": [ToolCapability.FILESYSTEM_WRITE.value],
    "move_file": [ToolCapability.FILESYSTEM_WRITE.value],
    "delete_file": [ToolCapability.FILESYSTEM_WRITE.value],
    "diff_files": [ToolCapability.FILESYSTEM_READ.value],
    "git_status": [ToolCapability.GIT_READ.value],
    "git_diff": [ToolCapability.GIT_READ.value],
    "git_log": [ToolCapability.GIT_READ.value],
    "git_add": [ToolCapability.GIT_WRITE.value],
    "git_commit": [ToolCapability.GIT_WRITE.value],
    "create_directory": [ToolCapability.FILESYSTEM_WRITE.value],
    "run_tests": [ToolCapability.PROCESS_EXECUTE.value],
    "run_affected_tests": [ToolCapability.PROCESS_EXECUTE.value],
    "git_status_diff": [ToolCapability.GIT_READ.value],
    "apply_patch_unified": [ToolCapability.FILESYSTEM_WRITE.value],
    "format_and_lint": [
        ToolCapability.FILESYSTEM_WRITE.value,
        ToolCapability.PROCESS_EXECUTE.value,
    ],
    "dependency_inspect": [ToolCapability.PROCESS_EXECUTE.value],
    "fetch_url": [ToolCapability.NETWORK_ACCESS.value],
    "json_yaml_edit": [ToolCapability.FILESYSTEM_WRITE.value],
    "process_logs": [ToolCapability.FILESYSTEM_READ.value],
    "gh_pr_list": [ToolCapability.NETWORK_ACCESS.value],
    "gh_pr_view": [ToolCapability.NETWORK_ACCESS.value],
    "gh_issue_list": [ToolCapability.NETWORK_ACCESS.value],
    "gh_issue_view": [ToolCapability.NETWORK_ACCESS.value],
    "gh_pr_create": [ToolCapability.NETWORK_ACCESS.value],
    "gh_pr_comment": [ToolCapability.NETWORK_ACCESS.value],
    "web_search": [ToolCapability.NETWORK_ACCESS.value],
    "compact_conversation": [],
    "write_todos": [],
    "update_todo": [],
    "delegate_task": [ToolCapability.PROCESS_EXECUTE.value],
    "memory_save": [],
    "memory_search": [],
    "memory_delete": [],
    "memory_list": [],
    "spawn_parallel_agents": [ToolCapability.PROCESS_EXECUTE.value],
    "semantic_search": [ToolCapability.FILESYSTEM_READ.value],
    "index_codebase": [ToolCapability.FILESYSTEM_READ.value],
    "browser_navigate": [ToolCapability.NETWORK_ACCESS.value],
    "browser_screenshot": [ToolCapability.NETWORK_ACCESS.value],
    "browser_click": [ToolCapability.NETWORK_ACCESS.value],
    "browser_type": [ToolCapability.NETWORK_ACCESS.value],
    "browser_evaluate": [ToolCapability.NETWORK_ACCESS.value],
}

_CACHEABLE_TOOLS = frozenset({"read_file", "glob_files", "grep_files", "git_status", "git_diff", "git_log", "list_directory", "diff_files"})
_MUTATION_TOOLS = frozenset({"write_file", "edit_file", "delete_file", "copy_file", "move_file", "bash", "git_add", "git_commit", "create_directory", "apply_patch_unified", "json_yaml_edit"})
_STATE_MUTATION_TOOLS = frozenset(
    {
        "compact_conversation",
        "write_todos",
        "update_todo",
        "memory_save",
        "memory_delete",
    }
)
_READ_ONLY_CAPABILITIES = frozenset(
    {
        ToolCapability.FILESYSTEM_READ.value,
        ToolCapability.GIT_READ.value,
        ToolCapability.NETWORK_ACCESS.value,
    }
)
_UNSAFE_CONCURRENCY_CAPABILITIES = frozenset(
    {
        ToolCapability.FILESYSTEM_WRITE.value,
        ToolCapability.GIT_WRITE.value,
        ToolCapability.PROCESS_EXECUTE.value,
    }
)

DEFAULT_MUTATING_TOOLS = {
    "write_file",
    "edit_file",
    "copy_file",
    "move_file",
    "delete_file",
    "create_directory",
    "apply_patch_unified",
    "format_and_lint",
    "json_yaml_edit",
    "git_add",
    "git_commit",
}


@dataclass
class ToolOutcome:
    """Structured result for mutating tools."""

    ok: bool
    operation: str
    path: str
    changed: bool
    diff: str = ""
    checkpoint_id: Optional[str] = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "ok": self.ok,
            "operation": self.operation,
            "path": self.path,
            "changed": self.changed,
            "diff": self.diff,
            "checkpoint_id": self.checkpoint_id,
            "message": self.message,
            "metadata": self.metadata,
        }
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class PatchHunk:
    """Single hunk inside a unified patch section."""

    path: str
    index: int
    header: str
    lines: List[str]


@dataclass
class PatchSection:
    """Unified patch section for a single target file."""

    path: str
    header_lines: List[str]
    hunks: List[PatchHunk]


def truncate_output(text: str, max_chars: int = 32000, max_lines: int = 500) -> str:
    """Truncate tool output to stay within context budget."""
    if not text:
        return text
    lines = text.splitlines(keepends=True)
    truncated = False
    if max_lines > 0 and len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    result = "".join(lines)
    if max_chars > 0 and len(result) > max_chars:
        result = result[:max_chars]
        truncated = True
    if truncated:
        result += "\n\n[Output truncated. Use specific file/line tools for full content.]"
    return result


class ToolRegistryAsync:
    """Async registry for all available tools"""
    MAX_CAPTURED_OUTPUT_BYTES = 1024 * 1024  # 1 MiB per stream

    def __init__(self, output_max_chars: int = 0, output_max_lines: int = 0):
        self.tools = {}
        self._output_max_chars = output_max_chars  # 0 = no truncation
        self._output_max_lines = output_max_lines
        self._cwd: str = os.getcwd()  # persisted working directory across bash calls
        self.command_validator = get_command_validator(strict_mode=False)
        self._core = None  # set by PoorCLICore after init for compact/delegate
        self._tool_cache: Dict[str, str] = {}
        self._tool_cache_hits: int = 0
        self._tool_cache_misses: int = 0
        self._todos: List[Dict[str, str]] = []  # agent todo list
        self._todos_path = Path.cwd() / ".poor-cli" / "todos.json"
        self._load_todos()
        self._register_tools()

    def _tool_cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        import hashlib
        canonical = json.dumps({"t": tool_name, "a": arguments}, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def reset_cwd(self) -> None:
        self._cwd = os.getcwd()  # reset to process working directory

    def _scan_unicode(self, text: str) -> str:
        """Scan text for dangerous unicode chars. Returns warning string or empty."""
        try:
            if self._core and hasattr(self._core, "config") and self._core.config:
                if not getattr(self._core.config.security, "unicode_scanning", True):
                    return ""
            from .unicode_security import scan_text
            result = scan_text(text)
            return result.summary()
        except Exception:
            return ""

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
                            },
                            "pages": {
                                "type": "STRING",
                                "description": "Page range for PDF files (e.g., '1-5', '3', '10-20'). Only for .pdf files."
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
                            },
                            "replace_all": {
                                "type": "BOOLEAN",
                                "description": "Replace all occurrences of old_text (default false)"
                            },
                            "format": {
                                "type": "STRING",
                                "description": "Edit format: 'search_replace' (default), 'whole_file', 'unified_diff', 'line_range'"
                            },
                            "diff_text": {
                                "type": "STRING",
                                "description": "Unified diff text to apply (only for format='unified_diff')"
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
                            },
                            "context_lines": {
                                "type": "INTEGER",
                                "description": "Number of context lines before and after each match"
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
            "git_log": {
                "function": self.git_log,
                "declaration": {
                    "name": "git_log",
                    "description": "Show recent git commit history",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "count": {"type": "INTEGER", "description": "Number of recent commits to show (default 10)"},
                            "file_path": {"type": "STRING", "description": "Optional file path to show history for"},
                            "path": {"type": "STRING", "description": "Repository path (defaults to current)"}
                        },
                        "required": []
                    }
                }
            },
            "git_add": {
                "function": self.git_add,
                "declaration": {
                    "name": "git_add",
                    "description": "Stage specific files for commit",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file_paths": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                                "description": "List of file paths to stage"
                            },
                            "path": {"type": "STRING", "description": "Repository path (defaults to current)"}
                        },
                        "required": ["file_paths"]
                    }
                }
            },
            "git_commit": {
                "function": self.git_commit,
                "declaration": {
                    "name": "git_commit",
                    "description": "Create a git commit with a message",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "message": {"type": "STRING", "description": "Commit message"},
                            "path": {"type": "STRING", "description": "Repository path (defaults to current)"}
                        },
                        "required": ["message"]
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
            "run_affected_tests": {
                "function": self.run_affected_tests,
                "declaration": {
                    "name": "run_affected_tests",
                    "description": "Run only tests affected by changed files, using repo graph and filename heuristics for smart selection",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "changed_files": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                                "description": "List of changed file paths. If empty, auto-detects from git diff HEAD."
                            },
                            "path": {
                                "type": "STRING",
                                "description": "Project directory (defaults to current directory)"
                            },
                            "framework": {
                                "type": "STRING",
                                "description": "Test framework: pytest, jest, cargo, go. Auto-detected if omitted."
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

        self.tools["compact_conversation"] = {
            "function": self.compact_conversation,
            "declaration": {
                "name": "compact_conversation",
                "description": "Compact the conversation history using LLM summarization to free up context window. Use when conversation is getting long.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "strategy": {
                            "type": "STRING",
                            "description": "Compaction strategy: 'compact' (LLM summary), 'compress' (strip tool calls), or 'handoff' (new session with summary)"
                        }
                    },
                    "required": []
                }
            }
        }

        self.tools["write_todos"] = {
            "function": self.write_todos,
            "declaration": {
                "name": "write_todos",
                "description": "Create or replace the agent todo list for tracking multi-step task progress. Items are injected into context each turn.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "todos": {
                            "type": "STRING",
                            "description": "JSON array of todo items: [{\"id\": \"1\", \"description\": \"...\", \"status\": \"pending\"}]. Status: pending|in_progress|completed"
                        }
                    },
                    "required": ["todos"]
                }
            }
        }

        self.tools["update_todo"] = {
            "function": self.update_todo,
            "declaration": {
                "name": "update_todo",
                "description": "Update the status of a todo item by id",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "id": {"type": "STRING", "description": "Todo item id"},
                        "status": {"type": "STRING", "description": "New status: pending|in_progress|completed"},
                        "description": {"type": "STRING", "description": "Optional new description"}
                    },
                    "required": ["id", "status"]
                }
            }
        }

        # ── semantic search tools ────────────────────────────────────────
        self.tools["semantic_search"] = {
            "function": self.semantic_search,
            "declaration": {
                "name": "semantic_search",
                "description": "Search the codebase using full-text search over an index of all project files. More thorough than grep for conceptual queries.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING", "description": "Search query (keywords or concepts)"},
                        "max_results": {"type": "INTEGER", "description": "Max results (default 10)"},
                        "file_filter": {"type": "STRING", "description": "Optional filename filter (e.g., '.py' or 'auth')"},
                    },
                    "required": ["query"]
                }
            }
        }
        self.tools["index_codebase"] = {
            "function": self.index_codebase,
            "declaration": {
                "name": "index_codebase",
                "description": "Build or refresh the semantic search index for the codebase. Only re-indexes changed files.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "force": {"type": "BOOLEAN", "description": "Force full re-index (default false)"},
                    },
                    "required": []
                }
            }
        }

        # ── parallel agent tool ──────────────────────────────────────────
        self.tools["spawn_parallel_agents"] = {
            "function": self.spawn_parallel_agents,
            "declaration": {
                "name": "spawn_parallel_agents",
                "description": "Spawn multiple isolated background agents running in parallel on separate git worktrees. Each agent works independently on its sub-task.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "prompts": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "List of task prompts, one per parallel agent (max 4)"
                        },
                        "sandbox_preset": {"type": "STRING", "description": "Sandbox preset for all agents (default: workspace-write)"},
                    },
                    "required": ["prompts"]
                }
            }
        }

        # ── memory tools ─────────────────────────────────────────────────
        self.tools["memory_save"] = {
            "function": self.memory_save,
            "declaration": {
                "name": "memory_save",
                "description": "Save a persistent memory that will be available in future sessions. Use for user preferences, project decisions, feedback, or external references.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING", "description": "Short descriptive name for this memory"},
                        "type": {"type": "STRING", "description": "Memory type: user, feedback, project, or reference"},
                        "description": {"type": "STRING", "description": "One-line description used to decide relevance in future sessions"},
                        "content": {"type": "STRING", "description": "Full memory content (markdown)"},
                    },
                    "required": ["name", "type", "description", "content"]
                }
            }
        }
        self.tools["memory_search"] = {
            "function": self.memory_search,
            "declaration": {
                "name": "memory_search",
                "description": "Search persistent memories by keyword query. Returns relevant memories from past sessions.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING", "description": "Search query"},
                        "type": {"type": "STRING", "description": "Optional filter: user, feedback, project, or reference"},
                        "max_results": {"type": "INTEGER", "description": "Max results to return (default 10)"},
                    },
                    "required": ["query"]
                }
            }
        }
        self.tools["memory_delete"] = {
            "function": self.memory_delete,
            "declaration": {
                "name": "memory_delete",
                "description": "Delete a persistent memory by name.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING", "description": "Name of the memory to delete"},
                    },
                    "required": ["name"]
                }
            }
        }
        self.tools["memory_list"] = {
            "function": self.memory_list,
            "declaration": {
                "name": "memory_list",
                "description": "List all persistent memories, optionally filtered by type.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "type": {"type": "STRING", "description": "Optional filter: user, feedback, project, or reference"},
                    },
                    "required": []
                }
            }
        }

        self.tools["mcp_scaffold"] = {
            "function": self._mcp_scaffold,
            "declaration": {
                "name": "mcp_scaffold",
                "description": "Scaffold a new MCP server from a template (Python or Node.js). Creates server file, README, and config snippet.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING", "description": "Server name (used for directory and config key)"},
                        "language": {"type": "STRING", "description": "Server language: 'python' or 'node' (default: python)"},
                    },
                    "required": ["name"]
                }
            }
        }
        self.tools["delegate_task"] = {
            "function": self.delegate_task,
            "declaration": {
                "name": "delegate_task",
                "description": "Delegate a sub-task to an in-process sub-agent with its own conversation. Returns the sub-agent's final response.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "prompt": {"type": "STRING", "description": "Task prompt for the sub-agent"},
                        "context_files": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "File paths to include as context"
                        },
                        "max_iterations": {"type": "INTEGER", "description": "Max tool iterations for sub-agent (default 10)"},
                        "tools": {"type": "STRING", "description": "Comma-separated allowed tools (e.g. 'read_file,grep_files'). If omitted, write/exec tools are denied by default."},
                        "archetype": {"type": "STRING", "description": "Sub-agent archetype: 'generic', 'research' (read-only), 'code' (full edit), 'test' (run tests), 'review' (code review). Overrides tool restrictions with archetype-specific defaults."}
                    },
                    "required": ["prompt"]
                }
            }
        }

        # register browser automation tools (lazy — playwright imported on first use)
        try:
            from .browser_tool import BROWSER_TOOLS, BROWSER_TOOL_DECLARATIONS
            for decl in BROWSER_TOOL_DECLARATIONS:
                name = decl["name"]
                self.tools[name] = {"function": BROWSER_TOOLS[name], "declaration": decl}
        except Exception as e:
            logger.debug("browser tools not registered: %s", e)

        for name, tool in self.tools.items():
            capabilities = DEFAULT_TOOL_CAPABILITIES.get(name, [])
            tool["capabilities"] = list(capabilities)
            tool["declaration"].update(
                tool_capability_metadata(
                    capabilities,
                    mutating=name in DEFAULT_MUTATING_TOOLS,
                )
            )

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Get tool declarations for API"""
        return [tool["declaration"] for tool in self.tools.values()]

    def get_tool_capabilities(self, tool_name: str) -> List[str]:
        tool = self.tools.get(tool_name)
        if not tool:
            return []
        capabilities = tool.get("capabilities")
        if isinstance(capabilities, list):
            return [str(capability) for capability in capabilities if str(capability).strip()]
        declaration = tool.get("declaration")
        if isinstance(declaration, dict):
            return declaration_capabilities(declaration)
        return []

    def register_external_tool(
        self,
        name: str,
        function: Any,
        declaration: Dict[str, Any]
    ) -> None:
        """Register an externally provided async tool function."""
        capabilities = declaration_capabilities(declaration)
        if not capabilities:
            capabilities = [ToolCapability.PROCESS_EXECUTE.value]
        self.tools[name] = {
            "function": function,
            "declaration": declaration,
            "capabilities": capabilities,
        }

    def is_mutating_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Return whether the tool invocation mutates state."""
        args = arguments or {}
        if tool_name == "apply_patch_unified" and bool(args.get("check_only")):
            return False
        if tool_name in _MUTATION_TOOLS or tool_name in _STATE_MUTATION_TOOLS:
            return True

        declaration = self.tools.get(tool_name, {}).get("declaration", {})
        if isinstance(declaration, dict):
            metadata = declaration.get("x-poor-cli")
            if isinstance(metadata, dict) and metadata.get("mutating") is True:
                return True

        capabilities = set(self.get_tool_capabilities(tool_name))
        if ToolCapability.FILESYSTEM_WRITE.value in capabilities:
            return True
        if ToolCapability.GIT_WRITE.value in capabilities:
            return True
        return False

    def is_concurrency_safe_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Return whether this tool call is safe to execute in parallel.

        Conservative by default: unknown/no-capability tools execute sequentially.
        """
        if self.is_mutating_tool(tool_name, arguments):
            return False

        capabilities = set(self.get_tool_capabilities(tool_name))
        if not capabilities:
            return False
        if capabilities.intersection(_UNSAFE_CONCURRENCY_CAPABILITIES):
            return False
        return capabilities.issubset(_READ_ONLY_CAPABILITIES)

    async def execute_tool_raw(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool and return its raw result."""
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
        if tool_name in _CACHEABLE_TOOLS:
            cache_key = self._tool_cache_key(tool_name, arguments)
            if cache_key in self._tool_cache:
                self._tool_cache_hits += 1
                return self._tool_cache[cache_key]
            self._tool_cache_misses += 1
        elif tool_name in _MUTATION_TOOLS:
            self._tool_cache.clear()

        result = await self.execute_tool_raw(tool_name, arguments)
        if isinstance(result, ToolOutcome):
            text = result.to_json()
        else:
            text = str(result)
        if self._output_max_chars > 0 or self._output_max_lines > 0:
            text = truncate_output(text, self._output_max_chars, self._output_max_lines)

        if tool_name in _CACHEABLE_TOOLS:
            self._tool_cache[self._tool_cache_key(tool_name, arguments)] = text

        return text

    def get_tool_cache_stats(self) -> Dict[str, int]:
        """Return cache hit/miss stats for /cost display."""
        return {
            "cache_hits": self._tool_cache_hits,
            "cache_misses": self._tool_cache_misses,
            "cache_entries": len(self._tool_cache),
        }

    @staticmethod
    def _text_diff(file_path: str, before: str, after: str) -> str:
        import difflib

        diff_lines = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        return "".join(diff_lines)

    @staticmethod
    def _read_text_for_diff(path: Path) -> Optional[str]:
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        if b"\0" in raw:
            return None
        return raw.decode("utf-8", errors="ignore")

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temp_path, path)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _tool_outcome(
        self,
        *,
        operation: str,
        path: Path,
        before: Optional[str],
        after: Optional[str],
        changed: bool,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ToolOutcome:
        diff = ""
        if before is not None and after is not None and (before != after):
            diff = self._text_diff(str(path), before, after)
        if changed and operation in ("write_file", "edit_file"):
            self._maybe_auto_commit(str(path), operation)
        return ToolOutcome(
            ok=True,
            operation=operation,
            path=str(path),
            changed=changed,
            diff=diff,
            message=message,
            metadata=metadata or {},
        )

    def _maybe_auto_commit(self, file_path: str, operation: str) -> None:
        """Auto-commit a file mutation if agentic.auto_commit is enabled."""
        try:
            agentic = getattr(getattr(self, "config", None), "agentic", None)
            if not agentic or not getattr(agentic, "auto_commit", False):
                return
            import subprocess as _sp
            check = _sp.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, timeout=5)
            if check.returncode != 0:
                return
            ignored = _sp.run(["git", "check-ignore", "-q", file_path], capture_output=True, timeout=5)
            if ignored.returncode == 0: # file is gitignored
                return
            rel = os.path.relpath(file_path)
            _sp.run(["git", "add", "--", file_path], capture_output=True, timeout=10)
            _sp.run(["git", "commit", "-m", f"Auto: {operation} {rel}"], capture_output=True, timeout=15)
        except Exception as e:
            logger.debug("auto-commit skipped: %s", e)

    def inspect_mutation_targets(self, tool_name: str, arguments: Dict[str, Any]) -> List[str]:
        """Return candidate file paths touched by a mutating tool invocation."""
        if tool_name in {"write_file", "edit_file", "delete_file", "json_yaml_edit"}:
            file_path = arguments.get("file_path")
            if file_path:
                try:
                    return [str(validate_file_path(file_path, must_exist=False))]
                except Exception:
                    return [str(Path(str(file_path)).expanduser().resolve())]
            return []

        if tool_name == "apply_patch_unified":
            patch = str(arguments.get("patch", "") or "")
            patch_root = self._resolve_directory(arguments.get("path"))
            return self._extract_patch_targets(patch, patch_root)

        return []

    @staticmethod
    def _normalize_mutation_paths(paths: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for path in paths:
            if not path:
                continue
            resolved = str(Path(str(path)).expanduser().resolve())
            if resolved not in seen:
                seen.add(resolved)
                normalized.append(resolved)
        return normalized

    @staticmethod
    def _normalize_chunk_index(value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @staticmethod
    def _resolve_patch_path(path: str, work_dir: Path) -> str:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return str(candidate.resolve())
        return str((work_dir / candidate).resolve())

    def _split_patch_sections(
        self,
        patch: str,
        work_dir: Path,
    ) -> Tuple[List[str], List[PatchSection]]:
        if not patch.strip():
            return [], []

        lines = patch.splitlines(keepends=True)
        preamble: List[str] = []
        raw_sections: List[List[str]] = []
        current_section: List[str] = []
        saw_section = False

        for line in lines:
            if line.startswith("diff --git "):
                saw_section = True
                if current_section:
                    raw_sections.append(current_section)
                current_section = [line]
                continue

            if saw_section:
                current_section.append(line)
            else:
                preamble.append(line)

        if current_section:
            raw_sections.append(current_section)
        elif not raw_sections:
            raw_sections.append(lines)
            preamble = []

        sections: List[PatchSection] = []
        for raw_section in raw_sections:
            header_lines: List[str] = []
            hunks: List[PatchHunk] = []
            current_hunk: List[str] = []
            section_text = "".join(raw_section)
            targets = self._extract_patch_targets(section_text, work_dir)
            section_path = targets[0] if targets else ""
            hunk_index = 0

            for line in raw_section:
                if line.startswith("@@"):
                    if current_hunk:
                        hunks.append(
                            PatchHunk(
                                path=section_path,
                                index=hunk_index,
                                header=current_hunk[0].rstrip("\n"),
                                lines=current_hunk,
                            )
                        )
                        hunk_index += 1
                    current_hunk = [line]
                elif current_hunk:
                    current_hunk.append(line)
                else:
                    header_lines.append(line)

            if current_hunk:
                hunks.append(
                    PatchHunk(
                        path=section_path,
                        index=hunk_index,
                        header=current_hunk[0].rstrip("\n"),
                        lines=current_hunk,
                    )
                )

            sections.append(
                PatchSection(
                    path=section_path,
                    header_lines=header_lines,
                    hunks=hunks,
                )
            )

        return preamble, sections

    @staticmethod
    def _render_patch_sections(preamble: List[str], sections: List[PatchSection]) -> str:
        rendered: List[str] = list(preamble)
        for section in sections:
            rendered.extend(section.header_lines)
            for hunk in section.hunks:
                rendered.extend(hunk.lines)
        return "".join(rendered)

    def _filter_patch_to_targets(
        self,
        patch: str,
        work_dir: Path,
        approved_paths: List[str],
    ) -> Tuple[str, List[str]]:
        if not patch.strip():
            return "", []

        normalized_paths = set(self._normalize_mutation_paths(approved_paths))
        if not normalized_paths:
            return patch, []

        preamble, sections = self._split_patch_sections(patch, work_dir)
        selected_sections: List[PatchSection] = []
        matched_targets: List[str] = []
        seen_targets: set[str] = set()
        for section in sections:
            if section.path not in normalized_paths:
                continue
            selected_sections.append(section)
            if section.path and section.path not in seen_targets:
                seen_targets.add(section.path)
                matched_targets.append(section.path)

        if not selected_sections:
            return "", []

        return self._render_patch_sections(preamble, selected_sections), matched_targets

    def _filter_patch_to_hunks(
        self,
        patch: str,
        work_dir: Path,
        approved_chunks: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        if not patch.strip():
            return "", []

        chunk_refs: Dict[str, set[int]] = {}
        for chunk in approved_chunks:
            if not isinstance(chunk, dict):
                continue
            raw_path = chunk.get("path") or chunk.get("filePath")
            raw_index = chunk.get("index")
            if raw_index is None:
                raw_index = chunk.get("hunkIndex")
            if not isinstance(raw_path, str) or not raw_path:
                continue
            index = self._normalize_chunk_index(raw_index)
            if index is None:
                continue
            resolved_path = self._resolve_patch_path(raw_path, work_dir)
            chunk_refs.setdefault(resolved_path, set()).add(index)

        if not chunk_refs:
            return patch, []

        preamble, sections = self._split_patch_sections(patch, work_dir)
        selected_sections: List[PatchSection] = []
        matched_chunks: List[Dict[str, Any]] = []

        for section in sections:
            allowed_indexes = chunk_refs.get(section.path)
            if not allowed_indexes:
                continue
            selected_hunks = [
                PatchHunk(
                    path=hunk.path,
                    index=hunk.index,
                    header=hunk.header,
                    lines=list(hunk.lines),
                )
                for hunk in section.hunks
                if hunk.index in allowed_indexes
            ]
            if not selected_hunks:
                continue
            selected_sections.append(
                PatchSection(
                    path=section.path,
                    header_lines=list(section.header_lines),
                    hunks=selected_hunks,
                )
            )
            for hunk in selected_hunks:
                matched_chunks.append(
                    {
                        "path": hunk.path,
                        "index": hunk.index,
                        "header": hunk.header,
                    }
                )

        if not selected_sections:
            return "", []

        return self._render_patch_sections(preamble, selected_sections), matched_chunks

    def narrow_mutation_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        approved_paths: List[str],
        approved_chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Restrict a mutation to the approved file subset when possible."""
        normalized_paths = self._normalize_mutation_paths(approved_paths)
        approved_chunks = approved_chunks or []
        if not normalized_paths and not approved_chunks:
            return dict(arguments)

        if tool_name in {"write_file", "edit_file", "delete_file", "json_yaml_edit"}:
            if not normalized_paths:
                return dict(arguments)
            targets = self.inspect_mutation_targets(tool_name, arguments)
            if not targets:
                raise ValidationError("Mutation does not expose file targets")
            if targets[0] not in set(normalized_paths):
                raise ValidationError("Selected file is not part of this mutation")
            return dict(arguments)

        if tool_name == "apply_patch_unified":
            work_dir = self._resolve_directory(arguments.get("path"))
            filtered_patch = str(arguments.get("patch", ""))
            matched_targets: List[str] = []

            if approved_chunks:
                filtered_patch, matched_chunks = self._filter_patch_to_hunks(
                    filtered_patch,
                    work_dir,
                    approved_chunks,
                )
                if not matched_chunks or not filtered_patch.strip():
                    raise ValidationError("Selected chunk is not part of this patch")
                matched_targets = self._normalize_mutation_paths(
                    [str(chunk["path"]) for chunk in matched_chunks]
                )
            elif normalized_paths:
                filtered_patch, matched_targets = self._filter_patch_to_targets(
                    filtered_patch,
                    work_dir,
                    normalized_paths,
                )
                if not matched_targets or not filtered_patch.strip():
                    raise ValidationError("Selected file is not part of this patch")
            narrowed = dict(arguments)
            narrowed["patch"] = filtered_patch
            return narrowed

        return dict(arguments)

    async def preview_mutation(self, tool_name: str, arguments: Dict[str, Any]) -> ToolOutcome:
        """Preview a mutating tool without writing to disk."""
        if tool_name == "write_file":
            return await self._preview_write_file(
                str(arguments.get("file_path", "")),
                str(arguments.get("content", "")),
            )
        if tool_name == "edit_file":
            return await self._preview_edit_file(
                file_path=str(arguments.get("file_path", "")),
                new_text=str(arguments.get("new_text", "")),
                old_text=arguments.get("old_text"),
                start_line=arguments.get("start_line"),
                end_line=arguments.get("end_line"),
            )
        if tool_name == "delete_file":
            return await self._preview_delete_file(str(arguments.get("file_path", "")))
        if tool_name == "apply_patch_unified":
            return await self._preview_apply_patch_unified(
                patch=str(arguments.get("patch", "")),
                path=arguments.get("path"),
                check_only=bool(arguments.get("check_only", False)),
            )
        if tool_name == "json_yaml_edit":
            return await self._preview_json_yaml_edit(
                file_path=str(arguments.get("file_path", "")),
                updates_json=str(arguments.get("updates_json", "")),
                create_missing=bool(arguments.get("create_missing", True)),
            )
        raise ValidationError(f"preview_mutation does not support tool `{tool_name}`")

    @staticmethod
    def _path_is_within_root(candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _extract_patch_targets(patch: str, work_dir: Path) -> List[str]:
        targets: List[str] = []
        seen: set[str] = set()
        resolved_root = work_dir.resolve()
        for line in patch.splitlines():
            candidate: Optional[str] = None
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) >= 4:
                    candidate = parts[3]
            elif line.startswith("+++ "):
                candidate = line[4:].strip()

            if not candidate or candidate == "/dev/null":
                continue

            if candidate.startswith("a/") or candidate.startswith("b/"):
                candidate = candidate[2:]

            resolved_path = (resolved_root / candidate).resolve()
            if not ToolRegistryAsync._path_is_within_root(resolved_path, resolved_root):
                raise ValidationError(
                    f"Patch target escapes working directory: {candidate}"
                )
            resolved = str(resolved_path)
            if resolved not in seen:
                seen.add(resolved)
                targets.append(resolved)
        return targets

    def _render_edit_content(
        self,
        *,
        content: str,
        new_text: str,
        old_text: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        replace_all: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        if old_text is None and start_line is None:
            raise ValidationError("edit_file requires `old_text` or `start_line`")

        if old_text is not None:
            occurrences = content.count(old_text)
            if occurrences == 0:
                raise ValidationError(f"Text not found in file: {old_text[:50]}...")
            if not replace_all and occurrences > 1:
                raise ValidationError(
                    "edit_file requires an exact single match; multiple matches found"
                )
            replaced = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
            return (
                replaced,
                {"mode": "exact_replace", "match_count": occurrences, "replacements": occurrences},
            )

        lines = content.splitlines(keepends=True)
        if not lines and start_line not in (None, 1):
            raise ValidationError(f"Invalid start_line: {start_line}")

        start = (start_line or 1) - 1
        end = end_line if end_line is not None else start + 1

        if start < 0 or start > len(lines):
            raise ValidationError(f"Invalid start_line: {start_line}")
        if end < start + 1 or end > len(lines):
            raise ValidationError(f"Invalid end_line: {end_line}")

        replacement_lines = new_text.splitlines(keepends=True)
        if new_text and not replacement_lines:
            replacement_lines = [new_text]

        return (
            "".join(lines[:start] + replacement_lines + lines[end:]),
            {
                "mode": "line_range",
                "start_line": start_line,
                "end_line": end_line or (start_line or 1),
            },
        )

    def _render_json_yaml_edit(
        self,
        *,
        path_obj: Path,
        updates_json: str,
        create_missing: bool,
    ) -> Tuple[str, str, List[str]]:
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

        return raw_content, rendered, changed_paths

    async def _preview_write_file(self, file_path: str, content: str) -> ToolOutcome:
        path_obj = validate_file_path(file_path, must_exist=False)
        existed_before = path_obj.exists()
        before = self._read_text_for_diff(path_obj) if existed_before else ""
        changed = before != content
        return self._tool_outcome(
            operation="write_file",
            path=path_obj,
            before=before or "",
            after=content,
            changed=changed,
            message=(
                f"Preview create {path_obj}" if not existed_before else f"Preview write {path_obj}"
            ),
            metadata={
                "created": not existed_before,
                "bytes": len(content),
                "preview": True,
                "paths": [str(path_obj)],
                "changed_paths": [str(path_obj)] if changed else [],
            },
        )

    async def _preview_edit_file(
        self,
        *,
        file_path: str,
        new_text: str,
        old_text: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> ToolOutcome:
        path_obj = validate_file_path(file_path, must_exist=True, must_be_file=True)
        content = path_obj.read_text(encoding="utf-8")
        new_content, metadata = self._render_edit_content(
            content=content,
            new_text=new_text,
            old_text=old_text,
            start_line=start_line,
            end_line=end_line,
        )
        changed = new_content != content
        return self._tool_outcome(
            operation="edit_file",
            path=path_obj,
            before=content,
            after=new_content,
            changed=changed,
            message=f"Preview edit {path_obj}",
            metadata={
                **metadata,
                "preview": True,
                "paths": [str(path_obj)],
                "changed_paths": [str(path_obj)] if changed else [],
            },
        )

    async def _preview_delete_file(self, file_path: str) -> ToolOutcome:
        path_obj = validate_file_path(file_path, must_exist=True, must_be_file=True)
        before = self._read_text_for_diff(path_obj)
        return self._tool_outcome(
            operation="delete_file",
            path=path_obj,
            before=before,
            after="",
            changed=True,
            message=f"Preview delete {path_obj}",
            metadata={
                "deleted": True,
                "preview": True,
                "paths": [str(path_obj)],
                "changed_paths": [str(path_obj)],
            },
        )

    async def _preview_apply_patch_unified(
        self,
        *,
        patch: str,
        path: Optional[str] = None,
        check_only: bool = False,
    ) -> ToolOutcome:
        if not patch or not patch.strip():
            raise ValidationError("Patch content cannot be empty")
        if not shutil.which("git"):
            raise ToolExecutionError("apply_patch_unified", "`git` is required for apply_patch_unified")

        work_dir = self._resolve_directory(path)
        patch_file = None
        target_paths = self._extract_patch_targets(patch, work_dir)
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".patch",
                prefix="poor_cli_preview_",
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

            changed = (not check_only) and bool(target_paths)
            return ToolOutcome(
                ok=True,
                operation="apply_patch_unified",
                path=str(work_dir),
                changed=changed,
                diff=patch,
                message="Patch preview ready",
                metadata={
                    "check_only": check_only,
                    "preview": True,
                    "paths": target_paths,
                    "changed_paths": target_paths if changed else [],
                },
            )
        finally:
            if patch_file and os.path.exists(patch_file):
                os.remove(patch_file)

    async def _preview_json_yaml_edit(
        self,
        *,
        file_path: str,
        updates_json: str,
        create_missing: bool = True,
    ) -> ToolOutcome:
        path_obj = validate_file_path(file_path, must_exist=True, must_be_file=True)
        raw_content, rendered, changed_paths = self._render_json_yaml_edit(
            path_obj=path_obj,
            updates_json=updates_json,
            create_missing=create_missing,
        )
        changed = rendered != raw_content
        return self._tool_outcome(
            operation="json_yaml_edit",
            path=path_obj,
            before=raw_content,
            after=rendered,
            changed=changed,
            message=(
                f"Preview update {path_obj} with {len(changed_paths)} changes: "
                + ", ".join(changed_paths[:15])
            ),
            metadata={
                "changed_paths": changed_paths,
                "create_missing": create_missing,
                "preview": True,
                "paths": [str(path_obj)],
            },
        )

    async def read_file(self, file_path: str, start_line: Optional[int] = None,
                       end_line: Optional[int] = None, pages: Optional[str] = None) -> str:
        """Read file contents asynchronously

        Args:
            file_path: Path to file
            start_line: Optional starting line (1-indexed)
            end_line: Optional ending line (1-indexed)
            pages: Optional page range for PDF files (e.g., "1-5")

        Returns:
            File contents

        Raises:
            FileOperationError: If read fails
        """
        try:
            # Validate path
            file_path = validate_file_path(file_path, must_exist=True, must_be_file=True)

            # route to specialized readers for non-text formats
            ext = Path(file_path).suffix.lower()
            if ext == ".pdf":
                from .readers.pdf_reader import read_pdf
                return read_pdf(file_path, pages=pages)
            if ext == ".ipynb":
                from .readers.notebook_reader import read_notebook
                return read_notebook(file_path)

            # Read file asynchronously
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if start_line or end_line:
                    lines = await f.readlines()
                    start = (start_line - 1) if start_line else 0
                    end = end_line if end_line else len(lines)
                    selected = lines[start:end]
                    offset = start + 1 # 1-indexed line numbers matching file position
                    content = ''.join(f"{offset + i:6d}\t{line}" for i, line in enumerate(selected))
                else:
                    content = await f.read()
                    if content: # add line numbers in cat -n format
                        raw_lines = content.splitlines(True)
                        content = ''.join(f"{i:6d}\t{line}" for i, line in enumerate(raw_lines, 1))

            logger.info(f"Read file: {file_path}")
            unicode_warn = self._scan_unicode(content)
            if unicode_warn:
                content = f"{unicode_warn}\n\n{content}"
            return content

        except (PoorFileNotFoundError, FilePermissionError, PathTraversalError):
            raise
        except Exception as e:
            raise FileOperationError(f"Failed to read file {file_path}: {str(e)}")

    async def write_file(self, file_path: str, content: str) -> ToolOutcome:
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
            path_obj = Path(file_path)
            existed_before = path_obj.exists()
            before = self._read_text_for_diff(path_obj) if existed_before else ""

            unicode_warn = self._scan_unicode(content)
            changed = before != content
            if changed:
                self._atomic_write_text(path_obj, content)

            logger.info(f"Wrote file: {file_path}")
            message = (
                f"Created {file_path}" if not existed_before else f"Wrote {file_path}"
            )
            if unicode_warn:
                message = f"{message}\n{unicode_warn}"
            return self._tool_outcome(
                operation="write_file",
                path=path_obj,
                before=before or "",
                after=content,
                changed=changed,
                message=message,
                metadata={"created": not existed_before, "bytes": len(content)},
            )

        except (PathTraversalError, FilePermissionError):
            raise
        except Exception as e:
            raise FileOperationError(f"Failed to write file {file_path}: {str(e)}")

    async def edit_file(self, file_path: str, new_text: str, old_text: Optional[str] = None,
                       start_line: Optional[int] = None, end_line: Optional[int] = None,
                       replace_all: bool = False, format: Optional[str] = None,
                       diff_text: Optional[str] = None) -> ToolOutcome:
        """Edit file by replacing text, lines, whole file, or applying a unified diff."""
        try:
            file_path = validate_file_path(file_path, must_exist=True, must_be_file=True)
            path_obj = Path(file_path)
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            # route to edit_formats module for non-default formats
            if format and format in ("unified_diff", "whole_file"):
                from .edit_formats import get_format
                fmt = get_format(format)
                new_content, mode_desc = fmt.apply(content, new_text=new_text, old_text=old_text or "",
                                                    diff_text=diff_text or "", replace_all=replace_all,
                                                    start_line=start_line or 0, end_line=end_line or 0)
                metadata = {"mode": mode_desc}
            else:
                new_content, metadata = self._render_edit_content(
                    content=content, new_text=new_text, old_text=old_text,
                    start_line=start_line, end_line=end_line, replace_all=replace_all,
                )

            changed = new_content != content
            if changed:
                self._atomic_write_text(path_obj, new_content)

            logger.info(f"Edited file: {file_path}")
            unicode_warn = self._scan_unicode(new_content)
            edit_msg = f"Edited {file_path}"
            if unicode_warn:
                edit_msg = f"{edit_msg}\n{unicode_warn}"
            return self._tool_outcome(
                operation="edit_file",
                path=path_obj,
                before=content,
                after=new_content,
                changed=changed,
                message=edit_msg,
                metadata=metadata,
            )

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
                        file_pattern: str = "*", case_sensitive: bool = True,
                        context_lines: int = 0) -> str:
        """Search for pattern in files

        Args:
            pattern: Regex pattern to search for
            path: Directory or file to search
            file_pattern: Glob pattern to filter files
            case_sensitive: Case sensitivity
            context_lines: Number of context lines before and after each match

        Returns:
            Search results

        Raises:
            ToolExecutionError: If grep fails
        """
        try:
            search_path = path or os.getcwd()

            if shutil.which("rg"): # prefer ripgrep when available
                return await self._grep_ripgrep(pattern, search_path, file_pattern, case_sensitive, context_lines)
            if shutil.which("grep"): # unix grep as intermediate fallback
                return await self._grep_unix_fallback(pattern, search_path, file_pattern, case_sensitive, context_lines)
            return await self._grep_python_fallback(pattern, search_path, file_pattern, case_sensitive, context_lines)

        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("grep_files", f"Grep search failed: {str(e)}")

    async def _grep_ripgrep(self, pattern: str, search_path: str,
                            file_pattern: str, case_sensitive: bool,
                            context_lines: int) -> str:
        """ripgrep-based grep implementation"""
        cmd = ["rg", "--line-number", "--no-heading", "--max-count", "500"]
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])
        if not case_sensitive:
            cmd.append("-i")
        if file_pattern != "*":
            cmd.extend(["--glob", file_pattern])
        cmd.append(pattern)
        cmd.append(search_path)

        result = await self._run_command_capture(cmd, timeout=30)
        if result["timed_out"]:
            raise ToolExecutionError("grep_files", "ripgrep search timed out")
        if result["exit_code"] == 1: # rg exit 1 means no matches
            return f"No matches found for pattern: {pattern}"
        if result["exit_code"] not in (0, 1):
            raise ToolExecutionError("grep_files", f"ripgrep failed: {result['stderr']}")

        stdout = result["stdout"].rstrip()
        if not stdout:
            return f"No matches found for pattern: {pattern}"

        lines = stdout.split("\n")[:500] # cap result lines
        output = f"Found {len(lines)} result lines:\n" + "\n".join(lines)
        logger.info(f"Grep search (rg): {pattern} found {len(lines)} result lines")
        return output

    async def _grep_unix_fallback(self, pattern: str, search_path: str,
                                  file_pattern: str, case_sensitive: bool,
                                  context_lines: int) -> str:
        """unix grep fallback (faster than pure Python, slower than rg)"""
        cmd = ["grep", "-rn", "--max-count=500", "-E"]
        if context_lines > 0:
            cmd.extend(["-C", str(context_lines)])
        if not case_sensitive:
            cmd.append("-i")
        if file_pattern != "*":
            cmd.extend(["--include", file_pattern])
        # exclude common noise dirs
        for d in (".git", "node_modules", "__pycache__", ".venv", "target", "dist"):
            cmd.extend(["--exclude-dir", d])
        cmd.append(pattern)
        cmd.append(search_path)
        result = await self._run_command_capture(cmd, timeout=30)
        if result["timed_out"]:
            raise ToolExecutionError("grep_files", "grep search timed out")
        if result["exit_code"] == 1: # no matches
            return f"No matches found for pattern: {pattern}"
        if result["exit_code"] not in (0, 1):
            # fall through to python fallback on error
            return await self._grep_python_fallback(pattern, search_path, file_pattern, case_sensitive, context_lines)
        stdout = result["stdout"].rstrip()
        if not stdout:
            return f"No matches found for pattern: {pattern}"
        lines = stdout.split("\n")[:500]
        output = f"Found {len(lines)} result lines:\n" + "\n".join(lines)
        logger.info(f"Grep search (grep): {pattern} found {len(lines)} result lines")
        return output

    async def _grep_python_fallback(self, pattern: str, search_path: str,
                                    file_pattern: str, case_sensitive: bool,
                                    context_lines: int) -> str:
        """python re-based grep fallback"""
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
        results = []
        result_count = 0

        if os.path.isfile(search_path):
            files = [search_path]
        else:
            full_pattern = os.path.join(search_path, "**", file_pattern)
            files = glob_module.glob(full_pattern, recursive=True)
            files = [f for f in files if os.path.isfile(f)]

        for file_path in files[:200]: # raised cap from 50 to 200
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = await f.readlines()

                for line_num, line in enumerate(all_lines, 1):
                    if regex.search(line):
                        if context_lines > 0: # add context window around match
                            start = max(0, line_num - 1 - context_lines)
                            end = min(len(all_lines), line_num + context_lines)
                            for ctx_idx in range(start, end):
                                ctx_line = all_lines[ctx_idx].rstrip()
                                results.append(f"{file_path}:{ctx_idx + 1}: {ctx_line}")
                                result_count += 1
                                if result_count >= 500:
                                    break
                        else:
                            results.append(f"{file_path}:{line_num}: {line.rstrip()}")
                            result_count += 1

                        if result_count >= 500: # raised cap from 100 to 500
                            break

            except Exception as e:
                logger.debug(f"Skipping file {file_path}: {e}")
                continue

            if result_count >= 500:
                break

        if not results:
            return f"No matches found for pattern: {pattern}"

        result = f"Found {len(results)} matches:\n" + "\n".join(results)
        logger.info(f"Grep search: {pattern} found {len(results)} matches")
        return result

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

    @staticmethod
    def _subprocess_spawn_kwargs() -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if hasattr(os, "killpg"):
            kwargs["start_new_session"] = True
        return kwargs

    @staticmethod
    def _signal_async_process(process: Any, sig: int) -> bool:
        pid = getattr(process, "pid", None)
        if pid is not None and int(pid) > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(int(pid), sig)
                return True
            except PermissionError:
                return True
            except OSError:
                pass

        try:
            if sig == signal.SIGTERM and hasattr(process, "terminate"):
                process.terminate()
            else:
                process.kill()
        except ProcessLookupError:
            return False
        return True

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
            **self._subprocess_spawn_kwargs(),
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
            self._signal_async_process(process, signal.SIGKILL)
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

    @staticmethod
    def _raise_for_capture_failure(tool_name: str, label: str, result: Dict[str, Any]) -> None:
        if result.get("timed_out"):
            raise ToolExecutionError(tool_name, f"{label} timed out")
        if int(result.get("exit_code", 0)) != 0:
            details = (
                str(result.get("stderr", "") or "").strip()
                or str(result.get("stdout", "") or "").strip()
                or f"{label} failed"
            )
            raise ToolExecutionError(tool_name, details)

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

    def _validate_fetch_target(self, url: str) -> None:
        """Validate an outbound fetch target before making a network request."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValidationError("Only http and https URLs are allowed")
        if not parsed.hostname:
            raise ValidationError("URL must include a valid hostname")
        if parsed.username or parsed.password:
            raise ValidationError("URLs with embedded credentials are not allowed")
        if not self._is_host_public(parsed.hostname):
            raise ValidationError("Refusing to fetch local/private network addresses")

    async def _read_http_body_with_limit(
        self,
        response: Any,
        max_bytes: int,
    ) -> Tuple[str, bool]:
        """Read an HTTP response body up to a byte limit."""
        chunks: List[bytes] = []
        captured = 0
        truncated = False

        async for chunk in response.content.iter_chunked(4096):
            if captured < max_bytes:
                remaining = max_bytes - captured
                if len(chunk) > remaining:
                    truncated = True
                to_store = chunk[:remaining]
                chunks.append(to_store)
                captured += len(to_store)
            else:
                truncated = True
                break

        return b"".join(chunks).decode("utf-8", errors="replace"), truncated

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

            if not command.strip():
                raise CommandExecutionError(command, "Command is empty after parsing")

            wrapped_cmd = f"{command}; echo __CWD__=$(pwd)"  # track cwd after execution
            # use OS-level or Docker sandbox if available
            from .sandbox import os_sandbox_available, sandboxed_command
            from .docker_sandbox import docker_sandbox_enabled, docker_sandboxed_command
            sandbox_preset = getattr(self, "_sandbox_preset", None) or getattr(getattr(self._core, "_sandbox_preset", None), "", "workspace-write") if self._core else "workspace-write"
            if docker_sandbox_enabled() and sandbox_preset != "full-access":
                argv = docker_sandboxed_command(wrapped_cmd, sandbox_preset)
                try:
                    from .audit_log import get_audit_logger, AuditEventType
                    get_audit_logger().log_event(AuditEventType.BASH_COMMAND, operation="docker_sandbox_wrap", target=command, details={"preset": sandbox_preset})
                except Exception:
                    pass
            elif os_sandbox_available() and sandbox_preset != "full-access":
                argv = sandboxed_command(wrapped_cmd, sandbox_preset)
            else:
                argv = ["sh", "-c", wrapped_cmd]

            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                **self._subprocess_spawn_kwargs(),
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
                self._signal_async_process(process, signal.SIGKILL)
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

            # extract cwd marker and update persisted working directory
            _cwd_lines = []
            _output_lines = []
            for _line in stdout_text.splitlines(True):
                if _line.rstrip("\n\r").startswith("__CWD__="):
                    _cwd_lines.append(_line.rstrip("\n\r")[len("__CWD__="):])
                else:
                    _output_lines.append(_line)
            if _cwd_lines and process.returncode == 0:
                self._cwd = _cwd_lines[-1]  # use last marker
            stdout_text = "".join(_output_lines)

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

            # prefer ls for speed and native formatting
            ls_cmd = ["ls", "-lh"]
            if show_hidden:
                ls_cmd.append("-a")
            ls_cmd.append(dir_path)
            try:
                ls_result = await self._run_command_capture(ls_cmd, timeout=10)
                if ls_result["exit_code"] == 0 and ls_result["stdout"].strip():
                    result = f"Contents of {dir_path}:\n{ls_result['stdout'].rstrip()}"
                    logger.info(f"Listed directory (ls): {dir_path}")
                    return result
            except Exception:
                pass # fall through to python fallback

            entries = []
            for entry in os.listdir(dir_path):
                if not show_hidden and entry.startswith('.'):
                    continue
                full_path = os.path.join(dir_path, entry)
                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue
                size = stat.st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f}MB"
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

    async def delete_file(self, file_path: str) -> ToolOutcome:
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
            path_obj = Path(file_path)
            before = self._read_text_for_diff(path_obj)

            # Delete file
            await asyncio.to_thread(os.remove, file_path)

            logger.info(f"Deleted file: {file_path}")
            return self._tool_outcome(
                operation="delete_file",
                path=path_obj,
                before=before,
                after="",
                changed=True,
                message=f"Deleted {file_path}",
                metadata={"deleted": True},
            )

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
        try:
            work_dir = self._resolve_directory(path)
            result = await self._run_command_capture(
                ["git", "status"],
                timeout=30,
                cwd=str(work_dir),
            )
            if result["timed_out"]:
                raise CommandExecutionError(
                    "git status",
                    "Git status timed out after 30 seconds",
                )
            if result["exit_code"] != 0:
                details = (result["stderr"] or result["stdout"]).strip() or "Git status failed"
                raise CommandExecutionError(
                    "git status",
                    details,
                    return_code=result["exit_code"],
                )

            output = (result["stdout"] or result["stderr"]).strip()
            return output or "Working tree clean"

        except Exception as e:
            if isinstance(e, CommandExecutionError):
                raise
            raise CommandExecutionError("git status", f"Git status failed: {str(e)}")

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
        try:
            work_dir = self._resolve_directory(path)
            argv = ["git", "diff"]
            if file_path:
                argv.extend(["--", file_path])

            result = await self._run_command_capture(
                argv,
                timeout=30,
                cwd=str(work_dir),
            )
            if result["timed_out"]:
                raise CommandExecutionError(
                    "git diff",
                    "Git diff timed out after 30 seconds",
                )
            if result["exit_code"] != 0:
                details = (result["stderr"] or result["stdout"]).strip() or "Git diff failed"
                raise CommandExecutionError(
                    "git diff",
                    details,
                    return_code=result["exit_code"],
                )

            output = result["stdout"].strip()
            return output or "No changes"

        except Exception as e:
            if isinstance(e, CommandExecutionError):
                raise
            raise CommandExecutionError("git diff", f"Git diff failed: {str(e)}")

    async def git_log(self, count: int = 10, file_path: Optional[str] = None, path: Optional[str] = None) -> str:
        """Show recent git commit history"""
        try:
            work_dir = self._resolve_directory(path)
            argv = ["git", "log", "--oneline", f"-{count}"]
            if file_path:
                argv.extend(["--", file_path])
            result = await self._run_command_capture(argv, timeout=30, cwd=str(work_dir))
            if result["timed_out"]:
                raise CommandExecutionError("git log", "Git log timed out after 30 seconds")
            if result["exit_code"] != 0:
                details = (result["stderr"] or result["stdout"]).strip() or "Git log failed"
                raise CommandExecutionError("git log", details, return_code=result["exit_code"])
            output = (result["stdout"] or result["stderr"]).strip()
            return output or "No commits found"
        except Exception as e:
            if isinstance(e, CommandExecutionError):
                raise
            raise CommandExecutionError("git log", f"Git log failed: {str(e)}")

    async def git_add(self, file_paths: List[str], path: Optional[str] = None) -> str:
        """Stage specific files for commit"""
        if not file_paths:
            raise ValidationError("file_paths must not be empty")
        for fp in file_paths: # reject broad-add patterns
            stripped = fp.strip()
            if stripped in (".", "-A", "--all"):
                raise ValidationError(f"Refusing to stage '{stripped}': specify individual files instead")
        try:
            work_dir = self._resolve_directory(path)
            argv = ["git", "add", "--"] + list(file_paths)
            result = await self._run_command_capture(argv, timeout=30, cwd=str(work_dir))
            if result["timed_out"]:
                raise CommandExecutionError("git add", "Git add timed out after 30 seconds")
            if result["exit_code"] != 0:
                details = (result["stderr"] or result["stdout"]).strip() or "Git add failed"
                raise CommandExecutionError("git add", details, return_code=result["exit_code"])
            return f"Staged {len(file_paths)} file(s)"
        except Exception as e:
            if isinstance(e, (CommandExecutionError, ValidationError)):
                raise
            raise CommandExecutionError("git add", f"Git add failed: {str(e)}")

    async def git_commit(self, message: str, path: Optional[str] = None) -> str:
        """Create a git commit with a message"""
        if not message or not message.strip():
            raise ValidationError("Commit message must not be empty")
        try:
            work_dir = self._resolve_directory(path)
            argv = ["git", "commit", "-m", message]
            result = await self._run_command_capture(argv, timeout=30, cwd=str(work_dir))
            if result["timed_out"]:
                raise CommandExecutionError("git commit", "Git commit timed out after 30 seconds")
            if result["exit_code"] != 0:
                details = (result["stderr"] or result["stdout"]).strip() or "Git commit failed"
                raise CommandExecutionError("git commit", details, return_code=result["exit_code"])
            output = (result["stdout"] or result["stderr"]).strip()
            return output or "Commit created"
        except Exception as e:
            if isinstance(e, (CommandExecutionError, ValidationError)):
                raise
            raise CommandExecutionError("git commit", f"Git commit failed: {str(e)}")

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
                "stdout_truncated": result["stdout_truncated"],
                "stderr_truncated": result["stderr_truncated"],
                "output_truncated": bool(
                    result["stdout_truncated"] or result["stderr_truncated"]
                ),
                "failing_locations": self._extract_failure_locations(combined_output),
                "output_excerpt": combined_output[:6000],
            }
            return json.dumps(payload, indent=2)
        except (ValidationError, ToolExecutionError):
            raise
        except Exception as e:
            raise ToolExecutionError("run_tests", f"Failed to run tests: {str(e)}")

    async def run_affected_tests(
        self,
        changed_files: Optional[List[str]] = None,
        path: Optional[str] = None,
        framework: Optional[str] = None,
    ) -> str:
        """Run only tests affected by changed files."""
        try:
            work_dir = self._resolve_directory(path)
            if not changed_files:
                result = await self._run_command_capture(
                    argv=["git", "diff", "--name-only", "HEAD"],
                    timeout=10, cwd=str(work_dir),
                )
                changed_files = [
                    f for f in (result.get("stdout", "") or "").splitlines() if f.strip()
                ]
            if not changed_files:
                return json.dumps({"ok": True, "message": "No changed files detected.", "tests_run": []})

            from poor_cli.testing_tools import TestRunner, TestFramework
            runner = TestRunner(workspace_root=work_dir)

            if not framework:
                framework = self._detect_test_framework(work_dir)

            fw_map = {
                "pytest": TestFramework.PYTEST, "jest": TestFramework.JEST,
                "cargo": TestFramework.CARGO_TEST, "go": TestFramework.GO_TEST,
            }
            fw = fw_map.get(framework or "pytest", TestFramework.PYTEST)

            repo_graph = None
            if self._core and hasattr(self._core, "_repo_graph"):
                repo_graph = self._core._repo_graph

            result, test_files = runner.run_affected_tests(changed_files, fw, repo_graph)
            payload = {
                "ok": result.failed == 0 and result.total > 0,
                "passed": result.passed,
                "failed": result.failed,
                "skipped": result.skipped,
                "total": result.total,
                "duration_seconds": round(result.duration_seconds, 2),
                "tests_run": test_files,
                "changed_files": changed_files,
                "output_excerpt": result.output[:6000] if result.output else "",
            }
            return json.dumps(payload, indent=2)
        except Exception as e:
            raise ToolExecutionError("run_affected_tests", f"Failed: {str(e)}")

    def _detect_test_framework(self, work_dir: Path) -> str:
        """Auto-detect test framework from workspace files."""
        if (work_dir / "pytest.ini").exists() or (work_dir / "pyproject.toml").exists() or (work_dir / "setup.py").exists():
            return "pytest"
        if (work_dir / "package.json").exists():
            return "jest"
        if (work_dir / "Cargo.toml").exists():
            return "cargo"
        if (work_dir / "go.mod").exists():
            return "go"
        return "pytest"

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
            self._raise_for_capture_failure("git_status_diff", "Git root check", root_check)
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
            self._raise_for_capture_failure("git_status_diff", "git status", status_result)
            self._raise_for_capture_failure("git_status_diff", "git diff --stat", unstaged_stat)
            self._raise_for_capture_failure("git_status_diff", "git diff --cached --stat", staged_stat)
            self._raise_for_capture_failure("git_status_diff", "git diff --shortstat", shortstat_unstaged)
            self._raise_for_capture_failure(
                "git_status_diff",
                "git diff --cached --shortstat",
                shortstat_staged,
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
    ) -> ToolOutcome:
        """Validate and apply a unified patch using git apply."""
        if not patch or not patch.strip():
            raise ValidationError("Patch content cannot be empty")
        if not shutil.which("git"):
            raise ToolExecutionError("apply_patch_unified", "`git` is required for apply_patch_unified")

        work_dir = self._resolve_directory(path)
        patch_file = None
        target_paths = self._extract_patch_targets(patch, work_dir)
        before_map = {
            target_path: self._read_text_for_diff(Path(target_path))
            for target_path in target_paths
        }
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
                return ToolOutcome(
                    ok=True,
                    operation="apply_patch_unified",
                    path=str(work_dir),
                    changed=False,
                    message="Patch validation successful",
                    metadata={
                        "check_only": True,
                        "paths": target_paths,
                    },
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

            diff_parts: List[str] = []
            changed_paths: List[str] = []
            for target_path in target_paths:
                after = self._read_text_for_diff(Path(target_path))
                before = before_map.get(target_path)
                if before is None and after is None:
                    continue
                rendered_before = before or ""
                rendered_after = after or ""
                if rendered_before != rendered_after:
                    changed_paths.append(target_path)
                    diff_parts.append(
                        self._text_diff(target_path, rendered_before, rendered_after)
                    )

            return ToolOutcome(
                ok=True,
                operation="apply_patch_unified",
                path=str(work_dir),
                changed=bool(changed_paths),
                diff="".join(diff_parts),
                message="Patch applied successfully",
                metadata={
                    "check_only": False,
                    "paths": target_paths,
                    "changed_paths": changed_paths,
                    "stdout": apply_result["stdout"].strip(),
                },
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
                        "stdout_truncated": command_result["stdout_truncated"],
                        "stderr_truncated": command_result["stderr_truncated"],
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
        self._validate_fetch_target(url)
        if not AIOHTTP_AVAILABLE:
            raise ToolExecutionError("fetch_url", "fetch_url requires aiohttp")

        timeout = max(timeout, 1)
        max_chars = max(max_chars, 200)
        max_redirects = 5
        max_body_bytes = min(max(max_chars * 8, 65536), self.MAX_CAPTURED_OUTPUT_BYTES)

        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                current_url = url
                for _ in range(max_redirects + 1):
                    self._validate_fetch_target(current_url)
                    async with session.get(current_url, allow_redirects=False) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            location = str(response.headers.get("Location", "")).strip()
                            if not location:
                                raise ToolExecutionError(
                                    "fetch_url",
                                    f"Redirect response from {current_url} missing Location header",
                                )
                            current_url = urljoin(str(response.url), location)
                            continue

                        body, body_truncated = await self._read_http_body_with_limit(
                            response,
                            max_body_bytes,
                        )
                        if response.status >= 400:
                            excerpt = body[:500].replace("\n", " ")
                            raise ToolExecutionError(
                                "fetch_url",
                                f"HTTP {response.status} fetching {current_url}: {excerpt}",
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
                            "content_truncated": body_truncated or len(excerpt) > max_chars,
                        }
                        return json.dumps(payload, indent=2)

                raise ToolExecutionError(
                    "fetch_url",
                    f"Too many redirects fetching URL: {url}",
                )
        except asyncio.TimeoutError:
            raise ToolExecutionError("fetch_url", f"Timed out fetching URL after {timeout}s")
        except aiohttp.ClientError as e:
            raise ToolExecutionError("fetch_url", f"Network error fetching URL: {str(e)}")

    async def json_yaml_edit(
        self,
        file_path: str,
        updates_json: str,
        create_missing: bool = True,
    ) -> ToolOutcome:
        """Apply dotted-path updates to JSON/YAML files."""
        try:
            path_obj = validate_file_path(file_path, must_exist=True, must_be_file=True)
            raw_content, rendered, changed_paths = self._render_json_yaml_edit(
                path_obj=path_obj,
                updates_json=updates_json,
                create_missing=create_missing,
            )

            changed = rendered != raw_content
            if changed:
                self._atomic_write_text(path_obj, rendered)

            return self._tool_outcome(
                operation="json_yaml_edit",
                path=path_obj,
                before=raw_content,
                after=rendered,
                changed=changed,
                message=(
                    f"Updated {path_obj} with {len(changed_paths)} changes: "
                    + ", ".join(changed_paths[:15])
                ),
                metadata={
                    "changed_paths": changed_paths,
                    "create_missing": create_missing,
                },
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

    def _load_todos(self) -> None:
        try:
            if self._todos_path.exists():
                self._todos = json.loads(self._todos_path.read_text(encoding="utf-8"))
        except Exception:
            self._todos = []

    def _save_todos(self) -> None:
        try:
            self._todos_path.parent.mkdir(parents=True, exist_ok=True)
            self._todos_path.write_text(json.dumps(self._todos, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("failed to persist todos: %s", e)

    def render_todos_for_context(self) -> str:
        if not self._todos:
            return ""
        lines = ["[ACTIVE TODO LIST]"]
        for item in self._todos:
            status = item.get("status", "pending")
            marker = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}.get(status, "[ ]")
            lines.append(f"  {marker} #{item.get('id', '?')}: {item.get('description', '')}")
        completed = sum(1 for t in self._todos if t.get("status") == "completed")
        lines.append(f"  Progress: {completed}/{len(self._todos)}")
        return "\n".join(lines)

    async def compact_conversation(self, strategy: str = "compact") -> str:
        if not self._core:
            return "error: core engine not available for compaction"
        if strategy not in ("compact", "compress", "handoff"):
            return f"error: unknown strategy '{strategy}', use compact|compress|handoff"
        result = await self._core.compact_context(strategy)
        return json.dumps(result, indent=2)

    async def write_todos(self, todos: str) -> str:
        try:
            items = json.loads(todos)
            if not isinstance(items, list):
                return "error: todos must be a JSON array"
            for item in items:
                if not isinstance(item, dict) or "id" not in item or "description" not in item:
                    return "error: each todo must have 'id' and 'description'"
                item.setdefault("status", "pending")
            self._todos = items
            self._save_todos()
            return f"todo list set: {len(items)} items"
        except json.JSONDecodeError as e:
            return f"error: invalid JSON: {e}"

    async def update_todo(self, id: str, status: str, description: str = "") -> str:
        if status not in ("pending", "in_progress", "completed"):
            return f"error: invalid status '{status}'"
        for item in self._todos:
            if item.get("id") == id:
                item["status"] = status
                if description:
                    item["description"] = description
                self._save_todos()
                return f"todo #{id} updated to {status}"
        return f"error: todo #{id} not found"

    # ── semantic search implementations ────────────────────────────────

    async def semantic_search(self, query: str, max_results: int = 10, file_filter: str = "", rerank: bool = True) -> str:
        try:
            from .indexer import CodebaseIndexer
            indexer = CodebaseIndexer()
            stats = indexer.get_stats()
            if stats.total_files == 0:
                indexer.index()
            if rerank:
                # auto-index embeddings on first vector search if missing
                emb_stats = indexer.get_embedding_stats() if hasattr(indexer, "get_embedding_stats") else {}
                if not emb_stats.get("total_embeddings", 0):
                    try:
                        await indexer.index_embeddings()
                    except Exception:
                        pass # fall through to hybrid (which falls back to FTS-only)
                results = await indexer.hybrid_search(
                    query, max_results=max_results, file_filter=file_filter or None,
                )
            else:
                results = indexer.search(query, max_results=max_results, file_filter=file_filter or None)
            if not results:
                return f"no results for: {query}"
            parts = [f"Found {len(results)} results for '{query}':\n"]
            for r in results:
                score_label = f"relevance: {r.score:.2f}" if r.score else ""
                parts.append(f"### {r.file_path} (chunk {r.chunk_index}, {score_label}, {r.language})\n```\n{r.content[:800]}\n```\n")
            return "\n".join(parts)
        except Exception as exc:
            return f"error: {exc}"

    async def index_codebase(self, force: bool = False) -> str:
        try:
            from .indexer import CodebaseIndexer
            indexer = CodebaseIndexer()
            stats = indexer.index(force=force)
            msg = (
                f"Indexing complete: {stats.total_files} files, "
                f"{stats.total_chunks} chunks, "
                f"index size: {stats.index_size_bytes // 1024}KB"
            )
            # auto-generate embeddings if a provider is available
            emb_result = await indexer.index_embeddings(force=force)
            if emb_result.get("embedded", 0) > 0:
                msg += f"\nEmbeddings: {emb_result['embedded']} chunks via {emb_result['provider']}"
            elif emb_result.get("error"):
                msg += f"\nEmbeddings: skipped ({emb_result['error']})"
            return msg
        except Exception as exc:
            return f"error: {exc}"

    # ── parallel agent implementation ──────────────────────────────────

    async def spawn_parallel_agents(self, prompts: List[str], sandbox_preset: str = "workspace-write") -> str:
        try:
            from .agent_runner import AgentManager
            mgr = AgentManager()
            agents = []
            for prompt in prompts[:4]: # cap at 4
                agent = mgr.create_agent(
                    prompt=prompt,
                    sandbox_preset=sandbox_preset,
                    source="parallel-tool",
                    use_worktree=True,
                    auto_start=True,
                )
                agents.append(agent)
            lines = [f"spawned {len(agents)} parallel agents:"]
            for a in agents:
                lines.append(f"  - {a.agent_id}: {a.prompt[:60]}... (branch: {a.branch_name})")
            lines.append("\nUse `poor-cli agent list` or `poor-cli agent result <id>` to check progress.")
            return "\n".join(lines)
        except Exception as exc:
            return f"error spawning parallel agents: {exc}"

    # ── memory tool implementations ────────────────────────────────────

    async def memory_save(self, name: str, type: str, description: str, content: str) -> str:
        try:
            from .memory import MemoryManager, MemoryEntry
            mgr = MemoryManager()
            mgr.load()
            existing = mgr.get(name)
            if existing:
                mgr.update(name, content=content, description=description, type_=type)
                return f"updated memory: {name}"
            entry = MemoryEntry(name=name, description=description, type=type, content=content)
            mgr.save(entry)
            return f"saved memory: {name} ({type})"
        except Exception as exc:
            return f"error saving memory: {exc}"

    async def memory_search(self, query: str, type: str = "", max_results: int = 10) -> str:
        try:
            from .memory import MemoryManager
            mgr = MemoryManager()
            mgr.load()
            results = mgr.search(query, type_filter=type or None, max_results=max_results)
            if not results:
                return "no memories found"
            lines = []
            for r in results:
                lines.append(f"## {r.name} ({r.type})\n{r.description}\n\n{r.content}\n")
            return "\n---\n".join(lines)
        except Exception as exc:
            return f"error searching memory: {exc}"

    async def memory_delete(self, name: str) -> str:
        try:
            from .memory import MemoryManager
            mgr = MemoryManager()
            mgr.load()
            if mgr.delete(name):
                return f"deleted memory: {name}"
            return f"memory not found: {name}"
        except Exception as exc:
            return f"error deleting memory: {exc}"

    async def memory_list(self, type: str = "") -> str:
        try:
            from .memory import MemoryManager
            mgr = MemoryManager()
            mgr.load()
            entries = mgr.list_all(type_filter=type or None)
            if not entries:
                return "no memories stored"
            lines = []
            for e in entries:
                lines.append(f"- **{e.name}** ({e.type}): {e.description}")
            return "\n".join(lines)
        except Exception as exc:
            return f"error listing memories: {exc}"

    async def _mcp_scaffold(self, name: str, language: str = "python") -> str:
        try:
            from .mcp_scaffold import scaffold_mcp_server
            return scaffold_mcp_server(name=name, language=language)
        except Exception as e:
            return f"error scaffolding MCP server: {e}"

    async def delegate_task(self, prompt: str, context_files: Optional[List[str]] = None, max_iterations: int = 10, tools: Optional[str] = None, archetype: Optional[str] = None) -> str:
        if not self._core:
            return "error: core engine not available for delegation"
        try:
            from .sub_agent import SubAgent
            archetype = archetype or "generic"
            allowed_tools = None
            denied_tools = None
            if tools and tools.strip():
                allowed_tools = {t.strip() for t in tools.split(",") if t.strip()}
            elif archetype == "generic":
                agentic_cfg = getattr(self._core.config, "agentic", None) if self._core.config else None
                denied_tools = set(getattr(agentic_cfg, "sub_agent_default_denied_tools", []) if agentic_cfg else [])
            agent = SubAgent(self._core, max_iterations=max_iterations, allowed_tools=allowed_tools, denied_tools=denied_tools, archetype=archetype)
            result = await agent.run(prompt, context_files=context_files)
            usage = agent.get_usage()
            if usage.get("input_tokens") or usage.get("output_tokens"):
                self._core._track_cost(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
            return result
        except Exception as e:
            return f"sub-agent error: {e}"

    async def web_search(self, query: str) -> str:
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
        if api_key:
            from .web_search import brave_search
            return await brave_search(query=query, api_key=api_key, count=5)

        from .web_search import duckduckgo_search
        return await duckduckgo_search(query=query, count=5)
