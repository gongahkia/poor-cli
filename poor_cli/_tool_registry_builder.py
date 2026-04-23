"""Tool registry declarations for ToolRegistryAsync.

Extracted from tools_async.py to keep that file under its line-budget cap.
Called once from ToolRegistryAsync._register_tools during __init__.
"""

from __future__ import annotations


def build_tool_registry(self) -> None:
    """Register all available tools"""
    import json
    import shutil
    from .tools_async import (
        DEFAULT_MUTATING_TOOLS,
        DEFAULT_SCHEMA_OUTPUT_FILTERS,
        DEFAULT_TOOL_CAPABILITIES,
        STREAMING_TOOL_NAMES,
        logger,
        tool_capability_metadata,
    )
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
                        },
                        "result_mode": {
                            "type": "STRING",
                            "description": "Result shape: full (default) or summary"
                        },
                        "max_bytes": {
                            "type": "INTEGER",
                            "description": "Optional returned byte cap"
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
                        },
                        "max_results": {
                            "type": "INTEGER",
                            "description": "Maximum result lines/files to return (default 100, max 500)"
                        },
                        "result_mode": {
                            "type": "STRING",
                            "description": "Result shape: snippets (default), paths_only, or counts_only"
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
                        },
                        "result_mode": {
                            "type": "STRING",
                            "description": "Result shape: full (default) or summary"
                        },
                        "max_output_bytes": {
                            "type": "INTEGER",
                            "description": "Optional returned byte cap"
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
                        },
                        "result_mode": {
                            "type": "STRING",
                            "description": "Result shape: full (default) or names_only"
                        },
                        "max_results": {
                            "type": "INTEGER",
                            "description": "Max entries to return (default 200)"
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
                        "description": "Compaction strategy: 'auto', 'compact', 'gentle', 'aggressive', 'compress', or 'handoff'"
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
            "description": "Spawn opt-in isolated background agents in separate git worktrees for independent experiments. Prefer delegate_task read-only archetypes for normal multi-agent help; parallel writers can make conflicting implicit decisions.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "prompts": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "description": "List of task prompts, one per parallel agent (max 4)"
                    },
                    "sandbox_preset": {"type": "STRING", "description": "Sandbox preset for all agents (default: workspace-write)"},
                    "communication_mode": {"type": "STRING", "description": "Agent communication mode: text or latent. Latent falls back to text for isolated background agents."},
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
                    "mode": {"type": "STRING", "description": "Retrieval mode: lod (default mixed full/summary/headline) or full"},
                    "alpha_profile": {"type": "STRING", "description": "LOD profile: semantic, balanced, or recency"},
                    "query_mode": {"type": "STRING", "description": "LOD query mode: auto, recent, last_week, never_seen, or ignored"},
                    "exclude": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Terms to penalize/exclude from LOD retrieval"},
                },
                "required": ["query"]
            }
        }
    }
    self.tools["memory_expand"] = {
        "function": self.memory_expand,
        "declaration": {
            "name": "memory_expand",
            "description": "Expand a memory returned as headline/summary by memory_search into full content.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Memory name or filename"},
                },
                "required": ["name"]
            }
        }
    }
    self.tools["memory_promote"] = {
        "function": self.memory_promote,
        "declaration": {
            "name": "memory_promote",
            "description": "Promote/pin a memory so LOD retrieval keeps it high-resolution.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Memory name or filename"},
                },
                "required": ["name"]
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
            "description": "Delegate a sub-task to an in-process sub-agent with its own conversation. Best for read-only research, clean-context review, tests, or smart-friend advice while the parent stays the default single writer.",
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
                    "tools": {"type": "STRING", "description": "Comma-separated allowed tools (e.g. 'read_file,grep_files'); use 'none' for toolless latent sub-agents. If omitted, write/exec tools are denied by default."},
                    "archetype": {"type": "STRING", "description": "Sub-agent archetype: 'generic', 'research' (read-only), 'code' (explicit opt-in writer), 'test' (run tests), 'review' (clean-context diff review), 'advisor' (smart-friend plan/risk critique). Overrides tool restrictions with archetype-specific defaults."},
                    "communication_mode": {"type": "STRING", "description": "Sub-agent communication mode: text or latent. Latent requires hf_local and research.latent_communication.enabled."}
                },
                "required": ["prompt"]
            }
        }
    }

    # register discover_tools meta-tool for deferred tool activation
    self.tools["discover_tools"] = {
        "function": self.discover_tools,
        "declaration": self._discover_tools_declaration(),
    }

    # register browser automation tools (lazy — playwright imported on first use)
    try:
        from .browser_tool import BROWSER_TOOLS, BROWSER_TOOL_DECLARATIONS
        for decl in BROWSER_TOOL_DECLARATIONS:
            name = decl["name"]
            self.tools[name] = {"function": BROWSER_TOOLS[name], "declaration": decl}
    except Exception as e:
        logger.debug("browser tools not registered: %s", e)

    # database tools (deferred)
    try:
        from .database_tools import DatabaseInspector, MigrationGenerator
        async def _db_inspect_schema(db_path: str = "", db_type: str = "sqlite", connection_string: str = "") -> str:
            inspector = DatabaseInspector()
            if db_type == "sqlite":
                schema = inspector.inspect_sqlite(db_path)
            elif db_type == "postgresql":
                schema = inspector.inspect_postgresql(connection_string)
            else:
                return f"Unsupported database type: {db_type}"
            return json.dumps({"database": schema.database_name, "type": schema.database_type.value, "tables": [{"name": t.name, "columns": [{"name": c.name, "type": c.data_type, "nullable": c.nullable, "primary_key": c.primary_key} for c in t.columns]} for t in schema.tables]}, indent=2)
        async def _db_generate_migration(workspace_root: str = ".", framework: str = "alembic", message: str = "auto migration") -> str:
            import shlex
            safe_message = shlex.quote(message) # sanitize RPC params
            gen = MigrationGenerator()
            if framework == "alembic":
                return gen.generate_alembic_migration(workspace_root, safe_message)
            elif framework == "django":
                return gen.generate_django_migration(workspace_root, safe_message)
            return f"Unsupported framework: {framework}"
        self.tools["db_inspect_schema"] = {"function": _db_inspect_schema, "declaration": {"name": "db_inspect_schema", "description": "Inspect database schema (SQLite or PostgreSQL)", "parameters": {"type": "object", "properties": {"db_path": {"type": "string", "description": "Path to SQLite database file"}, "db_type": {"type": "string", "enum": ["sqlite", "postgresql"], "description": "Database type"}, "connection_string": {"type": "string", "description": "PostgreSQL connection string"}}, "required": []}}}
        self.tools["db_generate_migration"] = {"function": _db_generate_migration, "declaration": {"name": "db_generate_migration", "description": "Generate database migration (Alembic or Django)", "parameters": {"type": "object", "properties": {"workspace_root": {"type": "string", "description": "Project root directory"}, "framework": {"type": "string", "enum": ["alembic", "django"], "description": "Migration framework"}, "message": {"type": "string", "description": "Migration description"}}, "required": ["workspace_root"]}}}
    except Exception as e:
        logger.debug("database tools not registered: %s", e)

    for name, tool in self.tools.items():
        capabilities = DEFAULT_TOOL_CAPABILITIES.get(name, [])
        tool["capabilities"] = list(capabilities)
        output_filter = DEFAULT_SCHEMA_OUTPUT_FILTERS.get(name)
        tool["output_filter"] = output_filter
        tool["declaration"]["output_filter"] = output_filter.to_schema() if output_filter else None
        tool["declaration"].update(
            tool_capability_metadata(
                capabilities,
                mutating=name in DEFAULT_MUTATING_TOOLS,
            )
        )
        if name in STREAMING_TOOL_NAMES:
            from .tool_streaming_tools import bind_stream_function

            tool["stream_function"] = bind_stream_function(self, name)
            tool["declaration"].setdefault("x-poor-cli", {})["streamsOutput"] = True
