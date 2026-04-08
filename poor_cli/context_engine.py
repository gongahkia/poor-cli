"""Context engine mixin for PoorCLICore.

Handles context file selection, message building, deduplication,
diff-only reads, and context pressure monitoring.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .core_events import CoreEvent
from .exceptions import setup_logger
from .instructions import InstructionManager, InstructionSnapshot

logger = setup_logger(__name__)


class ContextEngineMixin:
    """Mixin providing context gathering, deduplication, and pressure monitoring."""

    def _inspect_instruction_snapshot(
        self, referenced_files: Optional[List[str]] = None,
    ) -> InstructionSnapshot:
        manager = self._instruction_manager or InstructionManager(Path.cwd())
        repo_summary = ""
        if self._repo_graph is not None:
            try:
                repo_summary = self._repo_graph.build_repo_summary()
            except Exception:
                logger.debug("Failed to build repo summary", exc_info=True)
        return manager.build_snapshot(
            referenced_files or [],
            plan_mode_enabled=bool(self.config and self.config.plan_mode.enabled),
            repo_summary=repo_summary,
        )

    async def _select_context_files(
        self, message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ):
        if not self._context_manager:
            return None
        return await self._context_manager.select_context_files(
            message=message,
            explicit_files=context_files or [],
            pinned_files=pinned_context_files or [],
            repo_root=str(Path.cwd()),
            max_files=12,
        )

    async def _build_context_message(
        self, message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> str:
        """Build a backend-owned context message with excerpted files."""
        referenced_files: List[str] = []
        referenced_files.extend(context_files or [])
        referenced_files.extend(pinned_context_files or [])
        # resolve @mention context providers
        try:
            from .context_providers import resolve_mentions
            message, mention_blocks = await resolve_mentions(message, self)
            if mention_blocks:
                message = message + "\n\n" + "\n\n".join(mention_blocks)
        except Exception as e:
            logger.warning("context provider resolution failed: %s", e)
        # inject git context for change-related queries
        git_keywords = {"commit", "change", "diff", "push", "merge", "rebase", "staged", "recent"}
        if any(kw in message.lower() for kw in git_keywords):
            git_ctx = self._git_context_summary_cached()
            if git_ctx:
                message = f"{message}\n\n[Git context]\n{git_ctx}"
        context_result = None
        if self._context_manager:
            context_result = await self._select_context_files(
                message=message, context_files=context_files,
                pinned_context_files=pinned_context_files,
                context_budget_tokens=context_budget_tokens,
            )
            if context_result is not None:
                referenced_files.extend(file_ctx.path for file_ctx in context_result.files)
                self._record_context_preview({
                    "selected": list(context_result.selected),
                    "excluded": list(context_result.excluded),
                    "totalTokens": context_result.total_tokens,
                    "truncated": context_result.truncated,
                    "message": context_result.message,
                    "budgetTokens": context_budget_tokens or getattr(self._context_manager, "max_tokens", 0),
                })
                n_sel = len(context_result.selected)
                n_exc = len(context_result.excluded)
                tokens = context_result.total_tokens
                trunc = " (truncated)" if context_result.truncated else ""
                sources: Dict[str, int] = {}
                for fc in context_result.files:
                    src = getattr(fc, "source", "auto")
                    sources[src] = sources.get(src, 0) + 1
                src_parts = ", ".join(f"{k}={v}" for k, v in sorted(sources.items()))
                self._pending_events.append(CoreEvent(
                    type="progress",
                    data={"phase": "context_selection", "message": f"context: {n_sel} files selected (~{tokens} tokens){trunc} [{src_parts}] | {n_exc} excluded"},
                ))
        instruction_snapshot = self._inspect_instruction_snapshot(referenced_files)
        context_contract = getattr(self, "_context_contract", None)
        if context_contract:
            contract_snapshot = context_contract.build_snapshot(
                referenced_files=referenced_files,
                plan_mode_enabled=bool(self.config and self.config.plan_mode.enabled),
                instruction_snapshot=instruction_snapshot,
            )
            instruction_prefix = contract_snapshot.rendered_prompt_prefix
        else:
            instruction_prefix = instruction_snapshot.render_prompt_prefix()
        # auto-surface relevant skills
        try:
            from .skill_surfacer import detect_relevant_skills, build_skill_hints
            from .skills import SkillRegistry
            _skill_reg = SkillRegistry(getattr(self, "_repo_root", Path.cwd()))
            _all_skills = _skill_reg.list_skills()
            _skill_names = [s.name for s in _all_skills]
            _matched = detect_relevant_skills(message, _skill_names)
            if _matched:
                _descs = {s.name: s.description for s in _all_skills}
                _hint = build_skill_hints(_matched, _descs)
                if _hint:
                    instruction_prefix = f"{instruction_prefix}\n\n{_hint}" if instruction_prefix else _hint
        except Exception:
            pass
        # inject agent todo list
        todo_ctx = ""
        if self.tool_registry:
            todo_ctx = self.tool_registry.render_todos_for_context()
        if todo_ctx:
            message = f"{todo_ctx}\n\n{message}"
        if not self._context_manager or context_result is None or not context_result.files:
            if instruction_prefix:
                return f"{instruction_prefix}\n\nUser request: {message}"
            return message
        logger.info(context_result.message)
        context_message = await self._context_manager.build_context_message(
            message, context_result, max_tokens=context_budget_tokens,
        )
        if not instruction_prefix:
            return context_message
        return f"{instruction_prefix}\n\n{context_message}"

    def _dedup_context_files(self, context_text: str) -> Tuple[str, int]:
        """Remove file content blocks already seen this session."""
        if not self.config or not (self.config.economy.context_dedup or self.config.economy.dedup_context):
            return context_text, 0
        lines = context_text.split("\n")
        output_lines: List[str] = []
        skipping = False
        tokens_saved = 0
        for line in lines:
            if line.startswith("--- file: ") or line.startswith("File: "):
                path = line.split(": ", 1)[-1].strip()
                content_hash = hashlib.md5(line.encode()).hexdigest()
                if path in self._files_seen_in_session and self._files_seen_in_session[path] == content_hash:
                    skipping = True
                    output_lines.append(f"{line} [already in context, skipped]")
                    continue
                else:
                    self._files_seen_in_session[path] = content_hash
                    skipping = False
            if skipping:
                tokens_saved += len(line) // 4
                continue
            output_lines.append(line)
        return "\n".join(output_lines), tokens_saved

    def _apply_diff_only_read(self, tool_name: str, tool_args: Dict[str, Any], result: str) -> str:
        """For read_file, return only changed lines vs last read if diff_only_reads enabled."""
        if not self.config or not self.config.economy.diff_only_reads:
            return result
        if tool_name != "read_file":
            return result
        path = tool_args.get("file_path", "")
        if not path:
            return result
        previous = self._last_file_contents.get(path)
        self._last_file_contents[path] = result
        if previous is None:
            return result
        if previous == result:
            return f"[unchanged since last read: {path}]"
        diff = difflib.unified_diff(
            previous.splitlines(keepends=True), result.splitlines(keepends=True),
            fromfile=f"{path} (previous)", tofile=f"{path} (current)", n=3,
        )
        diff_text = "".join(diff)
        return f"[diff-only read: {path}]\n{diff_text}" if diff_text else f"[unchanged since last read: {path}]"

    def _check_context_pressure(self) -> Optional[str]:
        """Check if remaining context window is low. Returns warning or None."""
        if not self.provider or not self.config:
            return None
        try:
            caps = self.provider.get_capabilities()
            max_ctx = getattr(caps, "max_context_tokens", 0)
            if not max_ctx:
                return None
            history = self.provider.get_history()
            used = sum(len(str(t.get("content", ""))) // 4 for t in history)
            ratio = 1 - (used / max_ctx)
            if ratio < self.config.agentic.context_pressure_stop_ratio:
                return f"CRITICAL: context window nearly full ({ratio:.0%} remaining). Stop and summarize."
            if ratio < self.config.agentic.context_pressure_warn_ratio:
                return f"WARNING: context pressure high ({ratio:.0%} remaining). Consider compacting."
        except Exception:
            pass
        return None
