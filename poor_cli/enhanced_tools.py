"""
Enhanced Tools for poor-cli

Wraps existing tools with checkpoint and diff preview functionality.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable, Sequence

from poor_cli.tools_async import ToolRegistryAsync, ToolOutcome
from poor_cli.checkpoint import CheckpointManager
from poor_cli.diff_preview import DiffPreview
from poor_cli.config import Config
from poor_cli.exceptions import setup_logger, CommandExecutionError
from poor_cli.history import TokenCounter
from poor_cli.repo_config import get_repo_config
from poor_cli.rtk_integration import RTKState, detect_rtk, wrap_shell_command
from poor_cli.tool_output_filter import ToolOutputFilter, empty_filter_stats

logger = setup_logger(__name__)

CORE_TOOL_GROUP = "core"
MCP_GROUP_PREFIX = "mcp:"

TOOL_GROUPS: Dict[str, tuple[str, ...]] = {
    "core": ("read_file", "write_file", "edit_file", "bash", "discover_tools"),
    "search": ("glob_files", "grep_files", "list_directory", "semantic_search", "index_codebase"),
    "git": ("git_status", "git_diff", "git_log", "git_add", "git_commit", "git_status_diff", "apply_patch_unified"),
    "github": ("gh_pr_list", "gh_pr_view", "gh_issue_list", "gh_issue_view", "gh_pr_create", "gh_pr_comment"),
    "quality": ("run_tests", "run_affected_tests", "format_and_lint", "dependency_inspect", "process_logs"),
    "network": ("fetch_url", "web_search"),
    "file_ops": ("copy_file", "move_file", "delete_file", "create_directory", "diff_files"),
    "data": ("json_yaml_edit",),
    "planning": ("compact_conversation", "write_todos", "update_todo"),
    "memory": ("memory_save", "memory_search", "memory_delete", "memory_list"),
    "agents": ("spawn_parallel_agents", "delegate_task"),
    "browser": ("browser_navigate", "browser_screenshot", "browser_click", "browser_type", "browser_evaluate"),
    "mcp_admin": ("mcp_scaffold",),
}

_GROUP_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "search": (
        "search", "find", "grep", "glob", "where", "locate", "lookup", "look up", "trace",
        "explain", "inspect", "understand", "analyze", "review", "function", "class",
        "method", "symbol", "definition", "usage", "reference", "read", "show me",
    ),
    "git": (
        "git", "commit", "branch", "diff", "patch", "staged", "unstaged", "merge",
        "rebase", "checkout", "cherry-pick", "blame", "log",
    ),
    "github": (
        "github", "pull request", "pull-request", "gh ", " issue ", "issue#", "issue #",
        "pr#", "pr #", "review thread",
    ),
    "quality": (
        "test", "tests", "pytest", "coverage", "failing", "failure", "lint", "format",
        "formatter", "linter", "flake", "ruff", "logs", "stack trace", "dependency",
        "dependencies", "outdated", "qa",
    ),
    "network": (
        "http", "https", "url", "website", "web", "fetch", "download", "search online",
        "online", "remote", "api docs", "docs site",
    ),
    "file_ops": (
        "copy file", "move file", "rename file", "delete file", "remove file",
        "create directory", "mkdir", "new directory", "diff files",
    ),
    "data": (
        "json", "yaml", "yml", "toml", "config", "settings", "manifest", "package.json",
        "pyproject", "lockfile",
    ),
    "planning": ("todo", "todos", "task list", "plan", "compact", "summarize history"),
    "memory": ("remember", "memory", "preference", "saved context"),
    "agents": ("parallel agent", "parallel agents", "delegate", "sub-agent", "subagent"),
    "browser": ("browser", "page", "click", "screenshot", "navigate", "dom", "type into"),
    "mcp_admin": ("mcp scaffold", "mcp server", "model context protocol"),
}


@dataclass(frozen=True)
class ToolCatalogAudit:
    total_tools: int
    total_groups: int
    group_counts: Dict[str, int]
    schema_chars: int
    schema_tokens: int


def _stable_declarations_payload(declarations: Sequence[Dict[str, Any]]) -> str:
    normalized = sorted(
        [dict(declaration) for declaration in declarations],
        key=lambda declaration: str(declaration.get("name", "")),
    )
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _text_has_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _looks_like_github_request(text: str) -> bool:
    lowered = f" {text.lower()} "
    if _text_has_any(lowered, _GROUP_KEYWORDS["github"]):
        return True
    return bool(re.search(r"\b(pr|pull request|github)\b", lowered))


class EnhancedToolRegistry(ToolRegistryAsync):
    """Enhanced tool registry with checkpoints and diff preview"""

    def __init__(
        self,
        config: Config,
        checkpoint_manager: Optional[CheckpointManager] = None,
        diff_preview: Optional[DiffPreview] = None,
        output_max_chars: int = 0,
        output_max_lines: int = 0,
    ):
        """Initialize enhanced tools

        Args:
            config: Configuration object
            checkpoint_manager: Optional checkpoint manager
            diff_preview: Optional diff preview
        """
        super().__init__(
            output_max_chars=output_max_chars,
            output_max_lines=output_max_lines,
        )

        self.config = config
        self.checkpoint_manager = checkpoint_manager
        self.diff_preview = diff_preview
        self.output_filter = ToolOutputFilter(repo_root=Path.cwd())
        self._output_filter_stats = empty_filter_stats()

        # Track if diff/checkpoint should be shown for next operation
        self.show_diff = True
        self.create_checkpoint = True

        logger.info("Initialized enhanced tool registry")

    def set_checkpoint_manager(self, checkpoint_manager: CheckpointManager):
        """Set checkpoint manager"""
        self.checkpoint_manager = checkpoint_manager

    def set_diff_preview(self, diff_preview: DiffPreview):
        """Set diff preview"""
        self.diff_preview = diff_preview

    def disable_diff_for_next(self):
        """Disable diff preview for next operation (internal use)"""
        self.show_diff = False

    def disable_checkpoint_for_next(self):
        """Disable checkpoint for next operation (internal use)"""
        self.create_checkpoint = False

    def tool_groups(
        self,
        *,
        mcp_server_names: Optional[Iterable[str]] = None,
    ) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        available = set(self.tools)
        for group_name, tool_names in TOOL_GROUPS.items():
            groups[group_name] = [name for name in tool_names if name in available]
        for server_name in _ordered_unique(mcp_server_names or []):
            groups[f"{MCP_GROUP_PREFIX}{server_name}"] = []
        return groups

    def tool_group_for_name(
        self,
        tool_name: str,
        *,
        mcp_server_names: Optional[Iterable[str]] = None,
    ) -> Optional[str]:
        name = str(tool_name or "").strip()
        if not name:
            return None
        if ":" in name:
            server_name = name.split(":", 1)[0].strip()
            if server_name:
                return f"{MCP_GROUP_PREFIX}{server_name}"
        for group_name, tool_names in self.tool_groups(mcp_server_names=mcp_server_names).items():
            if name in tool_names:
                return group_name
        return None

    def required_tool_groups(
        self,
        prompt: str,
        *,
        context_files: Optional[Sequence[str]] = None,
        pinned_context_files: Optional[Sequence[str]] = None,
        mcp_server_names: Optional[Iterable[str]] = None,
    ) -> List[str]:
        text = str(prompt or "").strip().lower()
        groups: List[str] = [CORE_TOOL_GROUP]
        if not text:
            return groups

        if _text_has_any(text, _GROUP_KEYWORDS["search"]):
            groups.append("search")
        if _text_has_any(text, _GROUP_KEYWORDS["git"]):
            groups.append("git")
        if _looks_like_github_request(text):
            groups.append("github")
        if _text_has_any(text, _GROUP_KEYWORDS["quality"]):
            groups.append("quality")
        if _text_has_any(text, _GROUP_KEYWORDS["network"]):
            groups.append("network")
        if _text_has_any(text, _GROUP_KEYWORDS["file_ops"]):
            groups.append("file_ops")
        if _text_has_any(text, _GROUP_KEYWORDS["data"]):
            groups.append("data")
        if _text_has_any(text, _GROUP_KEYWORDS["planning"]):
            groups.append("planning")
        if _text_has_any(text, _GROUP_KEYWORDS["memory"]):
            groups.append("memory")
        if _text_has_any(text, _GROUP_KEYWORDS["agents"]):
            groups.append("agents")
        if _text_has_any(text, _GROUP_KEYWORDS["browser"]):
            groups.append("browser")
        if _text_has_any(text, _GROUP_KEYWORDS["mcp_admin"]):
            groups.append("mcp_admin")

        files = [*(context_files or []), *(pinned_context_files or [])]
        if files:
            extensions = {Path(file_path).suffix.lower() for file_path in files if str(file_path).strip()}
            if extensions.intersection({".json", ".yaml", ".yml", ".toml"}):
                if any(token in text for token in ("config", "setting", "update", "change", "edit", "set")):
                    groups.append("data")
            if any(token in text for token in ("explain", "inspect", "analyze", "review", "trace", "find")):
                groups.append("search")

        for server_name in _ordered_unique(mcp_server_names or []):
            if server_name.lower() in text:
                groups.append(f"{MCP_GROUP_PREFIX}{server_name}")

        return _ordered_unique(groups)

    def get_tool_declarations_by_names(self, names: Iterable[str]) -> List[Dict[str, Any]]:
        declarations = [
            self.tools[name]["declaration"]
            for name in _ordered_unique(names)
            if name in self.tools
        ]
        return sorted(declarations, key=lambda declaration: declaration.get("name", ""))

    def get_tool_declarations_for_groups(
        self,
        groups: Iterable[str],
        *,
        mcp_server_names: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        names: List[str] = []
        group_map = self.tool_groups(mcp_server_names=mcp_server_names)
        for group_name in _ordered_unique(groups):
            if group_name.startswith(MCP_GROUP_PREFIX):
                continue
            names.extend(group_map.get(group_name, []))
        return self.get_tool_declarations_by_names(names)

    def get_core_tool_declarations(self) -> List[Dict[str, Any]]:
        return self.get_tool_declarations_for_groups((CORE_TOOL_GROUP,))

    def audit_tool_catalog(
        self,
        *,
        extra_declarations: Optional[Sequence[Dict[str, Any]]] = None,
        extra_groups: Optional[Dict[str, Sequence[str]]] = None,
    ) -> ToolCatalogAudit:
        declarations = self.get_tool_declarations()
        if extra_declarations:
            declarations = sorted(
                [*declarations, *[dict(declaration) for declaration in extra_declarations]],
                key=lambda declaration: declaration.get("name", ""),
            )
        group_map = self.tool_groups()
        if extra_groups:
            for group_name, tool_names in extra_groups.items():
                merged = [*(group_map.get(group_name, [])), *list(tool_names)]
                group_map[group_name] = _ordered_unique(merged)
        payload = _stable_declarations_payload(declarations)
        return ToolCatalogAudit(
            total_tools=len(declarations),
            total_groups=len(group_map),
            group_counts={group_name: len(tool_names) for group_name, tool_names in group_map.items()},
            schema_chars=len(payload),
            schema_tokens=TokenCounter.estimate_tokens(payload),
        )

    def _get_rtk_state(self) -> RTKState:
        enabled = True
        tee_on_failure = True
        try:
            prefs = get_repo_config(enable_legacy_history_migration=False).preferences
            enabled = getattr(prefs, "rtk_enabled", True)
            tee_on_failure = getattr(prefs, "rtk_tee_on_failure", True)
        except Exception as e:
            logger.debug(f"Failed to load RTK preferences: {e}")
        return detect_rtk(enabled=enabled, tee_on_failure=tee_on_failure)

    async def bash(self, command: str, timeout: int = 60) -> str:
        state = self._get_rtk_state()
        wrapped_command = wrap_shell_command(command, state)
        if wrapped_command == command:
            return await super().bash(command, timeout=timeout)
        try:
            return await super().bash(wrapped_command, timeout=timeout)
        except CommandExecutionError:
            if not state.tee_on_failure:
                raise
            logger.info("RTK-wrapped bash failed; retrying raw command")
            return await super().bash(command, timeout=timeout)

    async def write_file_enhanced(
        self,
        file_path: str,
        content: str,
        show_diff: Optional[bool] = None,
        create_checkpoint: Optional[bool] = None
    ) -> str:
        """Enhanced write_file with checkpoint and diff preview

        Args:
            file_path: Path to file
            content: Content to write
            show_diff: Whether to show diff (None = use config)
            create_checkpoint: Whether to create checkpoint (None = use config)

        Returns:
            Result message
        """
        # Determine if we should show diff/checkpoint
        should_show_diff = (
            show_diff if show_diff is not None
            else (self.config.plan_mode.show_diff_in_plan and self.show_diff)
        )

        should_checkpoint = (
            create_checkpoint if create_checkpoint is not None
            else (
                self.config.checkpoint.enabled and
                self.config.checkpoint.auto_checkpoint_before_write and
                self.create_checkpoint
            )
        )

        path = Path(file_path)

        try:
            # Create checkpoint if file exists and checkpointing enabled
            if should_checkpoint and path.exists() and self.checkpoint_manager:
                try:
                    checkpoint = self.checkpoint_manager.create_checkpoint(
                        file_paths=[file_path],
                        description=f"Before writing: {path.name}",
                        operation_type="pre_write"
                    )
                    logger.info(f"Created checkpoint before write: {checkpoint.checkpoint_id}")
                except Exception as e:
                    logger.warning(f"Failed to create checkpoint: {e}")

            # Call parent write_file
            result = await super().write_file(file_path, content)

            # Reset flags
            self.show_diff = True
            self.create_checkpoint = True

            return result

        except Exception as e:
            # Reset flags even on error
            self.show_diff = True
            self.create_checkpoint = True
            raise

    async def edit_file_enhanced(
        self,
        file_path: str,
        new_text: str,
        old_text: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        show_diff: Optional[bool] = None,
        create_checkpoint: Optional[bool] = None
    ) -> str:
        """Enhanced edit_file with checkpoint and diff preview

        Args:
            file_path: Path to file
            new_text: New text
            old_text: Old text to replace
            start_line: Start line
            end_line: End line
            show_diff: Whether to show diff
            create_checkpoint: Whether to create checkpoint

        Returns:
            Result message
        """
        # Determine if we should checkpoint
        should_checkpoint = (
            create_checkpoint if create_checkpoint is not None
            else (
                self.config.checkpoint.enabled and
                self.config.checkpoint.auto_checkpoint_before_edit and
                self.create_checkpoint
            )
        )

        try:
            # Create checkpoint before edit
            if should_checkpoint and self.checkpoint_manager:
                try:
                    path = Path(file_path)
                    if path.exists():
                        checkpoint = self.checkpoint_manager.create_checkpoint(
                            file_paths=[file_path],
                            description=f"Before editing: {path.name}",
                            operation_type="pre_edit"
                        )
                        logger.info(f"Created checkpoint before edit: {checkpoint.checkpoint_id}")
                except Exception as e:
                    logger.warning(f"Failed to create checkpoint: {e}")

            # Call parent edit_file
            result = await super().edit_file(
                file_path, new_text, old_text, start_line, end_line
            )

            # Reset flags
            self.show_diff = True
            self.create_checkpoint = True

            return result

        except Exception as e:
            # Reset flags even on error
            self.show_diff = True
            self.create_checkpoint = True
            raise

    async def delete_file_enhanced(
        self,
        file_path: str,
        create_checkpoint: Optional[bool] = None
    ) -> str:
        """Enhanced delete_file with checkpoint

        Args:
            file_path: Path to file
            create_checkpoint: Whether to create checkpoint

        Returns:
            Result message
        """
        # Determine if we should checkpoint
        should_checkpoint = (
            create_checkpoint if create_checkpoint is not None
            else (
                self.config.checkpoint.enabled and
                self.config.checkpoint.auto_checkpoint_before_delete and
                self.create_checkpoint
            )
        )

        try:
            # Create checkpoint before delete
            if should_checkpoint and self.checkpoint_manager:
                try:
                    path = Path(file_path)
                    if path.exists():
                        checkpoint = self.checkpoint_manager.create_checkpoint(
                            file_paths=[file_path],
                            description=f"Before deleting: {path.name}",
                            operation_type="pre_delete"
                        )
                        logger.info(f"Created checkpoint before delete: {checkpoint.checkpoint_id}")
                except Exception as e:
                    logger.warning(f"Failed to create checkpoint: {e}")

            # Call parent delete_file
            result = await super().delete_file(file_path)

            # Reset flags
            self.create_checkpoint = True

            return result

        except Exception as e:
            # Reset flags even on error
            self.create_checkpoint = True
            raise

    def _record_output_filter_result(self, tokens_saved: int, *, auto_filtered: bool, projected: bool) -> None:
        self._output_filter_stats["filtered_calls"] += 1
        if auto_filtered:
            self._output_filter_stats["auto_filtered_calls"] += 1
        if projected:
            self._output_filter_stats["projection_filtered_calls"] += 1
        self._output_filter_stats["tokens_saved"] += max(0, int(tokens_saved or 0))

    async def execute_tool_raw(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        declaration = self.tools.get(tool_name, {}).get("declaration", {})
        request = self.output_filter.prepare_call(tool_name, arguments, declaration)
        clean_args = request.arguments

        if tool_name == "write_file" and self.checkpoint_manager:
            result = await self.write_file_enhanced(**clean_args)
        elif tool_name == "edit_file" and self.checkpoint_manager:
            result = await self.edit_file_enhanced(**clean_args)
        elif tool_name == "delete_file" and self.checkpoint_manager:
            result = await self.delete_file_enhanced(**clean_args)
        else:
            result = await super().execute_tool_raw(tool_name, clean_args)

        if isinstance(result, ToolOutcome):
            return result

        filtered = self.output_filter.filter(
            tool_name,
            result,
            projection=request.projection,
            max_tokens=request.max_tokens,
            explicit_projection=request.explicit_projection,
        )
        if filtered.applied:
            self._record_output_filter_result(
                filtered.tokens_saved,
                auto_filtered=filtered.auto_filtered,
                projected=bool(filtered.projection),
            )
            return filtered.output
        return result

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        return await super().execute_tool(tool_name, arguments)

    def get_checkpoint_stats(self) -> Dict[str, Any]:
        """Get checkpoint statistics"""
        if not self.checkpoint_manager:
            return {}

        checkpoints = self.checkpoint_manager.list_checkpoints(limit=10)
        total_size = self.checkpoint_manager.get_storage_size()

        return {
            "total_checkpoints": len(self.checkpoint_manager.checkpoints),
            "recent_checkpoints": len(checkpoints),
            "storage_size_bytes": total_size,
            "storage_size_mb": total_size / (1024 * 1024)
        }

    def get_output_filter_stats(self) -> Dict[str, int]:
        return dict(self._output_filter_stats)
