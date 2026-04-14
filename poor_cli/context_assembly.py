"""Context assembly orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .context import FileContext
from .block_cache import BlockCacheSession
from .code_tokenizer import is_safe_pretokenize_language, safe_pretokenize
from .core_events import CoreEvent
from .exceptions import setup_logger
from .skills import SkillRegistry
from .token_counter import get_token_counter

logger = setup_logger(__name__)


@dataclass(frozen=True)
class ContextFile:
    path: str
    content: str
    tokens: int
    reason: str
    compressed: bool
    original_tokens: int = 0
    compressed_tokens: int = 0
    tokens_saved: int = 0
    pretokenized: bool = False


@dataclass(frozen=True)
class TurnInput:
    prompt: str
    turn_id: str = ""
    context_files: Tuple[str, ...] = field(default_factory=tuple)
    pinned_context_files: Tuple[str, ...] = field(default_factory=tuple)
    context_budget_tokens: Optional[int] = None
    activate_tools: bool = True


@dataclass(frozen=True)
class ContextSnapshot:
    system_prompt: str
    rules: str
    files: Tuple[ContextFile, ...]
    messages: Tuple[Dict[str, Any], ...]
    history: Tuple[Dict[str, Any], ...]
    tool_schemas: Tuple[Dict[str, Any], ...]
    tokens: Dict[str, int]
    budget: int
    provider: str
    model: str
    key: str
    message: str = ""
    user_prompt: str = ""
    turn_id: str = ""


class ContextAssemblyOrchestrator:
    def __init__(self, core: Any) -> None:
        self._core = core
        from .context_compressor import ContextCompressor
        from .context_optimizer import TieredContextCompactor
        self.context_compressor = getattr(core, "_context_compressor", None) or ContextCompressor()
        self.tiered_compactor = getattr(core, "_tiered_compactor", None) or TieredContextCompactor()
        self.block_cache = getattr(core, "_block_cache", None) or BlockCacheSession()
        core._context_compressor = self.context_compressor
        core._tiered_compactor = self.tiered_compactor
        core._block_cache = self.block_cache
        self._last_invalidation_reason = ""

    def invalidate(self, reason: str) -> None:
        self._last_invalidation_reason = str(reason or "")

    async def assemble(
        self,
        turn_input: Optional[TurnInput | str] = None,
        *,
        prompt: Optional[str] = None,
        turn_id: str = "",
        context_files: Optional[Sequence[str]] = None,
        pinned_context_files: Optional[Sequence[str]] = None,
        context_budget_tokens: Optional[int] = None,
        activate_tools: bool = True,
    ) -> ContextSnapshot:
        request = self._normalize_turn_input(
            turn_input,
            prompt=prompt,
            turn_id=turn_id,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
            activate_tools=activate_tools,
        )
        provider_name, model_name, budget = self._resolve_provider_model_budget()
        message, context_result, referenced_files, rules = await self._assemble_user_message(request)
        if request.activate_tools:
            await self._activate_tools(request)
        tool_schemas = self._tool_schemas()
        history = self._history()
        files = self._context_files(context_result)
        history = await self._compact_if_over_budget(
            history=history,
            system_prompt=self._system_prompt(),
            rules=rules,
            files=files,
            tool_schemas=tool_schemas,
            message=message,
            provider_name=provider_name,
            model_name=model_name,
            budget=budget,
        )
        messages = ({"role": "user", "content": message},)
        tokens = self._token_breakdown(
            system_prompt=self._system_prompt(),
            rules=rules,
            files=files,
            history=history,
            tool_schemas=tool_schemas,
            messages=messages,
            provider_name=provider_name,
            model_name=model_name,
        )
        key = self._snapshot_key(
            rules=rules,
            files=files,
            history=history,
            tool_schemas=tool_schemas,
            provider_name=provider_name,
            model_name=model_name,
        )
        return ContextSnapshot(
            system_prompt=self._system_prompt(),
            rules=rules,
            files=files,
            messages=messages,
            history=tuple(history),
            tool_schemas=tuple(tool_schemas),
            tokens=tokens,
            budget=budget,
            provider=provider_name,
            model=model_name,
            key=key,
            message=message,
            user_prompt=request.prompt,
            turn_id=request.turn_id,
        )

    def _normalize_turn_input(
        self,
        turn_input: Optional[TurnInput | str],
        *,
        prompt: Optional[str],
        turn_id: str,
        context_files: Optional[Sequence[str]],
        pinned_context_files: Optional[Sequence[str]],
        context_budget_tokens: Optional[int],
        activate_tools: bool,
    ) -> TurnInput:
        if isinstance(turn_input, TurnInput):
            return turn_input
        resolved_prompt = prompt if prompt is not None else (turn_input if isinstance(turn_input, str) else "")
        return TurnInput(
            prompt=str(resolved_prompt or ""),
            turn_id=str(turn_id or ""),
            context_files=tuple(str(path) for path in (context_files or ())),
            pinned_context_files=tuple(str(path) for path in (pinned_context_files or ())),
            context_budget_tokens=context_budget_tokens,
            activate_tools=activate_tools,
        )

    def _resolve_provider_model_budget(self) -> Tuple[str, str, int]:
        core = self._core
        config = getattr(core, "config", None)
        provider_name = ""
        model_name = ""
        if config is not None and getattr(config, "model", None) is not None:
            provider_name = str(getattr(config.model, "provider", "") or "")
            model_name = str(getattr(config.model, "model_name", "") or "")
        provider = getattr(core, "provider", None)
        if provider is not None:
            model_name = str(getattr(provider, "model_name", model_name) or model_name)
            try:
                caps = provider.get_capabilities()
                budget = int(getattr(caps, "max_context_tokens", 0) or 0)
            except Exception:
                budget = 0
        else:
            budget = 0
        if budget <= 0 and config is not None and getattr(config, "history", None) is not None:
            budget = int(getattr(config.history, "max_token_limit", 0) or 0)
        return provider_name, model_name, max(0, budget)

    async def _assemble_user_message(
        self,
        request: TurnInput,
    ) -> Tuple[str, Any, List[str], str]:
        core = self._core
        message = request.prompt
        referenced_files: List[str] = []
        referenced_files.extend(request.context_files)
        referenced_files.extend(request.pinned_context_files)
        try:
            from .context_providers import resolve_mentions
            message, mention_blocks = await resolve_mentions(message, core)
            if mention_blocks:
                message = message + "\n\n" + "\n\n".join(mention_blocks)
        except Exception as e:
            logger.warning("context provider resolution failed: %s", e)
        git_keywords = {"commit", "change", "diff", "push", "merge", "rebase", "staged", "recent"}
        if any(keyword in message.lower() for keyword in git_keywords):
            git_ctx = core._git_context_summary_cached()
            if git_ctx:
                message = f"{message}\n\n[Git context]\n{git_ctx}"
        context_result = await self._select_files(message, request)
        if context_result is not None:
            self._apply_safe_pretokenization(context_result, request)
            self._apply_diff_of_diff_cache(context_result, request)
            referenced_files.extend(file_ctx.path for file_ctx in context_result.files)
            self._record_context_result(context_result, request)
        rules = self._assemble_rules(message, referenced_files)
        skill_hint = self._skill_hint(message)
        todo_ctx = ""
        if getattr(core, "tool_registry", None):
            todo_ctx = core.tool_registry.render_todos_for_context()
        if skill_hint:
            message = f"{skill_hint}\n\n{message}"
        if todo_ctx:
            message = f"{todo_ctx}\n\n{message}"
        if not getattr(core, "_context_manager", None) or context_result is None or not context_result.files:
            return f"User request: {message}", context_result, referenced_files, rules
        logger.info(context_result.message)
        context_message = await core._context_manager.build_context_message(
            message,
            context_result,
            max_tokens=request.context_budget_tokens,
        )
        return context_message, context_result, referenced_files, rules

    async def _select_files(self, message: str, request: TurnInput) -> Any:
        core = self._core
        context_manager = getattr(core, "_context_manager", None)
        if not context_manager:
            return None
        ensure_repo_graph = getattr(core, "_ensure_repo_graph", None)
        if ensure_repo_graph is not None:
            await ensure_repo_graph()
        previous_selector = getattr(context_manager, "_file_selector", None)
        context_manager._file_selector = self._file_selector()
        try:
            result = await context_manager.select_context_files(
                message=message,
                explicit_files=list(request.context_files),
                pinned_files=list(request.pinned_context_files),
                repo_root=str(Path.cwd()),
                max_files=12,
            )
            if result is not None and getattr(result, "files", None):
                self._apply_dropped_files(result)
                result.files = list(self.block_cache.stabilize_files(result.files))
                if getattr(result, "selected", None):
                    order = {file_ctx.path: idx for idx, file_ctx in enumerate(result.files)}
                    result.selected = sorted(
                        result.selected,
                        key=lambda item: order.get(str(item.get("path", "")), 10**9),
                    )
            return result
        finally:
            context_manager._file_selector = previous_selector

    def _apply_dropped_files(self, result: Any) -> None:
        dropped = {
            str(Path(path).expanduser().resolve())
            for path in getattr(self._core, "_context_dropped_files", set()) or set()
            if str(path or "").strip()
        }
        if not dropped:
            return
        kept = []
        removed = set()
        for file_ctx in list(getattr(result, "files", []) or []):
            path = str(Path(str(getattr(file_ctx, "path", "") or "")).expanduser().resolve())
            if path in dropped:
                removed.add(str(getattr(file_ctx, "path", "") or path))
                continue
            kept.append(file_ctx)
        if not removed:
            return
        result.files = kept
        if not isinstance(getattr(result, "excluded", None), list):
            result.excluded = []
        if getattr(result, "selected", None):
            selected = []
            for item in result.selected:
                path = str(item.get("path", "")) if isinstance(item, dict) else ""
                if path in removed or str(Path(path).expanduser().resolve()) in dropped:
                    if isinstance(item, dict):
                        excluded = dict(item)
                        excluded["excludedReason"] = "user-dropped"
                        result.excluded.append(excluded)
                    continue
                selected.append(item)
            result.selected = selected
        result.total_tokens = sum(int(getattr(file_ctx, "tokens_estimate", 0) or 0) for file_ctx in kept)

    def _file_selector(self) -> Any:
        from .context.file_selector import FileSelector, SelectionWeights

        core = self._core
        task = getattr(core, "_repo_graph_task", None)
        graph_ready = task is None or bool(getattr(task, "done", lambda: True)())
        prefs = getattr(getattr(core, "_repo_config", None), "preferences", None)
        if prefs is None:
            try:
                from .repo_config import get_repo_config
                prefs = get_repo_config(enable_legacy_history_migration=False).preferences
            except Exception:
                prefs = None
        raw_weights = {}
        if prefs is not None:
            raw_context = getattr(prefs, "context", {}) or {}
            if isinstance(raw_context, dict):
                raw_weights = raw_context.get("selection_weights", {}) or {}
        return FileSelector(
            repo_graph=getattr(core, "_repo_graph", None),
            weights=SelectionWeights.from_mapping(raw_weights),
            graph_ready=graph_ready,
        )

    def _record_context_result(self, context_result: Any, request: TurnInput) -> None:
        core = self._core
        preview = {
            "selected": list(context_result.selected),
            "excluded": list(context_result.excluded),
            "totalTokens": context_result.total_tokens,
            "truncated": context_result.truncated,
            "message": context_result.message,
            "budgetTokens": request.context_budget_tokens or getattr(core._context_manager, "max_tokens", 0),
        }
        recorder = getattr(core, "_record_context_preview", None)
        if recorder is not None:
            recorder(preview)
        sources: Dict[str, int] = {}
        for file_ctx in context_result.files:
            src = getattr(file_ctx, "source", "auto")
            sources[src] = sources.get(src, 0) + 1
        src_parts = ", ".join(f"{key}={value}" for key, value in sorted(sources.items()))
        pending_events = getattr(core, "_pending_events", None)
        if isinstance(pending_events, list):
            pending_events.append(CoreEvent(
                type="progress",
                data={
                    "phase": "context_selection",
                    "message": (
                        f"context: {len(context_result.selected)} files selected "
                        f"(~{context_result.total_tokens} tokens)"
                        f"{' (truncated)' if context_result.truncated else ''} "
                        f"[{src_parts}] | {len(context_result.excluded)} excluded"
                    ),
                },
            ))

    def _apply_safe_pretokenization(self, context_result: Any, request: TurnInput) -> None:
        cfg = getattr(getattr(self._core, "config", None), "context", None)
        if not bool(getattr(cfg, "safe_pretokenization", False)):
            return
        counter = get_token_counter()
        total_tokens = 0
        for file_ctx in getattr(context_result, "files", []) or []:
            content = str(getattr(file_ctx, "content", "") or "")
            original_tokens = int(getattr(file_ctx, "tokens_estimate", 0) or 0)
            if original_tokens <= 0:
                original_tokens = counter.count(content).count
            compressed_tokens = original_tokens
            pretokenized = False
            if content and not self._is_edit_target(file_ctx, request):
                hint = self._language_hint(file_ctx)
                if is_safe_pretokenize_language(hint):
                    compressed = safe_pretokenize(content, hint)
                    if compressed != content:
                        candidate_tokens = counter.count(compressed).count
                        if 0 <= candidate_tokens < original_tokens:
                            file_ctx.content = compressed
                            file_ctx.size = len(compressed)
                            file_ctx.tokens_estimate = candidate_tokens
                            compressed_tokens = candidate_tokens
                            pretokenized = True
                            tracker = getattr(self._core, "_economy_tracker", None)
                            if tracker is not None and hasattr(tracker, "record_safe_pretokenization"):
                                tracker.record_safe_pretokenization(
                                    str(getattr(file_ctx, "path", "") or ""),
                                    original_tokens,
                                    compressed_tokens,
                                )
            setattr(file_ctx, "pretokenization_original_tokens", original_tokens)
            setattr(file_ctx, "pretokenization_compressed_tokens", compressed_tokens)
            setattr(file_ctx, "pretokenization_tokens_saved", max(0, original_tokens - compressed_tokens))
            setattr(file_ctx, "safe_pretokenized", pretokenized)
            total_tokens += int(getattr(file_ctx, "tokens_estimate", compressed_tokens) or compressed_tokens)
            if pretokenized:
                self._mark_selected_entry(
                    context_result,
                    str(getattr(file_ctx, "path", "") or ""),
                    original_tokens,
                    compressed_tokens,
                )
        context_result.total_tokens = total_tokens

    def _apply_diff_of_diff_cache(self, context_result: Any, request: TurnInput) -> None:
        """CB1: replace re-read file content with a collapsed diff vs last send.

        Skips edit targets (model needs full content), small files (no win),
        and any errors (graceful fall-back to full content).
        """
        cfg = getattr(getattr(self._core, "config", None), "context", None)
        if not bool(getattr(cfg, "diff_of_diff_cache", False)):
            return
        min_chars = int(getattr(cfg, "diff_of_diff_min_chars", 800) or 800)
        ttl = float(getattr(cfg, "diff_of_diff_ttl_seconds", 21600.0) or 21600.0)
        try:
            from .context.diff_cache import DiffCache
        except Exception:
            return
        cache = getattr(self._core, "_diff_of_diff_cache", None)
        if cache is None:
            override_path = getattr(cfg, "diff_of_diff_cache_path", "") or ""
            if override_path:
                cache = DiffCache(Path(override_path), ttl_seconds=ttl)
            else:
                cache = DiffCache(ttl_seconds=ttl)
            self._core._diff_of_diff_cache = cache
        # build a per-turn pinned-context hash so the cache key reflects the
        # surrounding context (pinned files + active turn). Two turns with the
        # same pinned set hit the same cache; different sets get different keys.
        import hashlib as _hashlib
        pinned_hash = _hashlib.sha256(
            "|".join(sorted(request.pinned_context_files or ())).encode("utf-8", errors="replace")
        ).hexdigest()[:16]
        for file_ctx in getattr(context_result, "files", []) or []:
            content = str(getattr(file_ctx, "content", "") or "")
            if not content or len(content) < min_chars:
                continue
            if self._is_edit_target(file_ctx, request):
                continue
            try:
                key = DiffCache.make_key(str(getattr(file_ctx, "path", "") or ""), pinned_hash)
                emission, _entry = cache.ensure_entry(key, content)
                if emission.mode == "diff":
                    file_ctx.content = emission.content
                    file_ctx.size = len(emission.content)
                    setattr(file_ctx, "diff_of_diff_mode", "diff")
                    setattr(file_ctx, "diff_of_diff_tokens_saved", emission.tokens_saved_estimate)
                    tracker = getattr(self._core, "_economy_tracker", None)
                    if tracker is not None and hasattr(tracker, "record_safe_pretokenization"):
                        # reuse the savings counter; CB1 surfaces under the same dashboard row
                        tracker.record_safe_pretokenization(
                            str(getattr(file_ctx, "path", "") or ""),
                            len(content),
                            len(emission.content),
                        )
            except Exception as exc:
                logger.debug("CB1 diff-of-diff skipped for %s: %s", getattr(file_ctx, "path", "?"), exc)
        # persist after the pass so cache survives restarts
        try:
            cache.persist()
        except Exception:
            pass

    @staticmethod
    def _language_hint(file_ctx: FileContext) -> str:
        language = str(getattr(file_ctx, "language", "") or "")
        if language:
            return language
        return Path(str(getattr(file_ctx, "path", "") or "")).suffix

    @staticmethod
    def _is_edit_target(file_ctx: FileContext, request: TurnInput) -> bool:
        if bool(getattr(file_ctx, "include_full_content", False)):
            return True
        source = str(getattr(file_ctx, "source", "") or "").lower()
        if source in {"explicit", "git"}:
            return True
        path = str(getattr(file_ctx, "path", "") or "").lower()
        name = Path(path).name
        prompt = request.prompt.lower()
        edit_verbs = ("edit", "change", "modify", "fix", "patch", "implement", "update", "rewrite", "refactor")
        return bool((path and path in prompt or name and name in prompt) and any(verb in prompt for verb in edit_verbs))

    @staticmethod
    def _mark_selected_entry(context_result: Any, path: str, original_tokens: int, compressed_tokens: int) -> None:
        for collection_name in ("selected", "excluded"):
            for entry in getattr(context_result, collection_name, []) or []:
                if str(entry.get("path", "")) != path:
                    continue
                entry["tokenEstimate"] = compressed_tokens
                entry["safePretokenized"] = True
                entry["originalTokens"] = original_tokens
                entry["compressedTokens"] = compressed_tokens
                entry["tokensSaved"] = max(0, original_tokens - compressed_tokens)

    def _assemble_rules(self, message: str, referenced_files: List[str]) -> str:
        core = self._core
        skill_context = core._build_instruction_skill_context()
        skill_plan = SkillRegistry(
            getattr(core, "_repo_root", Path.cwd()),
            search_paths=core._configured_skill_search_paths(),
        ).build_instruction_plan(message, skill_context)
        instruction_snapshot = core._inspect_instruction_snapshot(
            referenced_files,
            user_prompt=message,
            skill_context=skill_context,
            skill_plan=skill_plan,
        )
        core._last_instruction_snapshot = instruction_snapshot
        core._last_instruction_skill_plan = skill_plan
        context_contract = getattr(core, "_context_contract", None)
        if context_contract:
            contract_snapshot = context_contract.build_snapshot(
                referenced_files=referenced_files,
                plan_mode_enabled=bool(core.config and core.config.plan_mode.enabled),
                instruction_snapshot=instruction_snapshot,
            )
            rules = contract_snapshot.rendered_prompt_prefix
        else:
            rules = instruction_snapshot.render_prompt_prefix()
        if getattr(core, "provider", None):
            core.provider.update_prompt_prefix(rules)
        return rules

    def _skill_hint(self, message: str) -> str:
        core = self._core
        try:
            from .skill_surfacer import build_skill_hints, detect_relevant_skills
            skill_reg = SkillRegistry(
                getattr(core, "_repo_root", Path.cwd()),
                search_paths=core._configured_skill_search_paths(),
            )
            all_skills = skill_reg.list_skills()
            matched = detect_relevant_skills(message, [skill.name for skill in all_skills])
            if not matched:
                return ""
            descriptions = {skill.name: skill.description for skill in all_skills}
            return build_skill_hints(matched, descriptions) or ""
        except Exception:
            return ""

    async def _activate_tools(self, request: TurnInput) -> None:
        activator = getattr(self._core, "_activate_tools_for_prompt", None)
        if activator is not None:
            await activator(
                request.prompt,
                context_files=list(request.context_files),
                pinned_context_files=list(request.pinned_context_files),
            )

    def _tool_schemas(self) -> List[Dict[str, Any]]:
        declarations = getattr(self._core, "_active_tool_declarations", None)
        if isinstance(declarations, list):
            return [dict(declaration) for declaration in declarations]
        resolver = getattr(self._core, "_tool_declarations_for_shipping", None)
        if resolver is None:
            return []
        return [dict(declaration) for declaration in resolver()]

    def _history(self) -> List[Dict[str, Any]]:
        provider = getattr(self._core, "provider", None)
        if provider is None:
            return []
        try:
            return [dict(message) for message in provider.get_history()]
        except Exception:
            return []

    def _context_files(self, context_result: Any) -> Tuple[ContextFile, ...]:
        if context_result is None:
            return tuple()
        files: List[ContextFile] = []
        for file_ctx in getattr(context_result, "files", []) or []:
            files.append(self._context_file(file_ctx, bool(getattr(context_result, "truncated", False))))
        return tuple(files)

    def _context_file(self, file_ctx: FileContext, truncated: bool) -> ContextFile:
        reason = str(getattr(file_ctx, "selection_reason", "") or getattr(file_ctx, "source", "") or "selected")
        tokens = int(getattr(file_ctx, "tokens_estimate", 0) or 0)
        if tokens <= 0:
            tokens = get_token_counter().count(str(getattr(file_ctx, "content", "") or "")).count
        return ContextFile(
            path=str(getattr(file_ctx, "path", "") or ""),
            content=str(getattr(file_ctx, "content", "") or ""),
            tokens=tokens,
            reason=reason,
            compressed=bool(truncated or not getattr(file_ctx, "include_full_content", False)),
            original_tokens=int(getattr(file_ctx, "pretokenization_original_tokens", tokens) or tokens),
            compressed_tokens=int(getattr(file_ctx, "pretokenization_compressed_tokens", tokens) or tokens),
            tokens_saved=int(getattr(file_ctx, "pretokenization_tokens_saved", 0) or 0),
            pretokenized=bool(getattr(file_ctx, "safe_pretokenized", False)),
        )

    async def _compact_if_over_budget(
        self,
        *,
        history: List[Dict[str, Any]],
        system_prompt: str,
        rules: str,
        files: Tuple[ContextFile, ...],
        tool_schemas: List[Dict[str, Any]],
        message: str,
        provider_name: str,
        model_name: str,
        budget: int,
    ) -> List[Dict[str, Any]]:
        if budget <= 0 or not history:
            return history
        total = self._token_breakdown(
            system_prompt=system_prompt,
            rules=rules,
            files=files,
            history=history,
            tool_schemas=tool_schemas,
            messages=({"role": "user", "content": message},),
            provider_name=provider_name,
            model_name=model_name,
        )["total"]
        if total <= budget:
            return history
        core = self._core
        compactor = getattr(core, "_tiered_compactor", None)
        if compactor is not None:
            eco = getattr(getattr(core, "config", None), "economy", None)
            cc_cfg = getattr(getattr(core, "config", None), "context_compression", None)
            result = await compactor.compact(
                history,
                max_tokens=budget,
                mode="aggressive",
                economy_preset=str(getattr(eco, "preset", "balanced") or "balanced"),
                trigger="assembly_budget",
                auto_compact_threshold=float(getattr(cc_cfg, "auto_compact_threshold", 0.7) or 0.7),
                auto_compact_target=float(getattr(cc_cfg, "auto_compact_target", 0.4) or 0.4),
            )
            history = [dict(message) for message in result.history]
            self._set_provider_history(history)
        total = self._token_breakdown(
            system_prompt=system_prompt,
            rules=rules,
            files=files,
            history=history,
            tool_schemas=tool_schemas,
            messages=({"role": "user", "content": message},),
            provider_name=provider_name,
            model_name=model_name,
        )["total"]
        if total <= budget:
            return history
        compressor = getattr(core, "_context_compressor", None)
        cc_cfg = getattr(getattr(core, "config", None), "context_compression", None)
        provider = getattr(core, "provider", None)
        if compressor is not None and cc_cfg is not None:
            strip_chars = getattr(getattr(core, "config", None).economy, "tool_strip_chars", 200) if getattr(core, "config", None) else 200
            history = await compressor.compress_auto(
                history,
                cc_cfg,
                provider=provider,
                tool_strip_chars=strip_chars,
            )
            history = [dict(message) for message in history]
            self._set_provider_history(history)
        return history

    def _set_provider_history(self, history: List[Dict[str, Any]]) -> None:
        provider = getattr(self._core, "provider", None)
        if provider is None or not hasattr(provider, "set_history"):
            return
        try:
            provider.set_history(history)
        except Exception:
            logger.debug("provider history update failed", exc_info=True)

    def _token_breakdown(
        self,
        *,
        system_prompt: str,
        rules: str,
        files: Tuple[ContextFile, ...],
        history: Sequence[Dict[str, Any]],
        tool_schemas: Sequence[Dict[str, Any]],
        messages: Sequence[Dict[str, Any]],
        provider_name: str,
        model_name: str,
    ) -> Dict[str, int]:
        counter = get_token_counter()
        tools_text = self._stable_json(tool_schemas)
        system_tokens = counter.count(system_prompt, provider=provider_name, model=model_name).count
        rules_tokens = counter.count(rules, provider=provider_name, model=model_name).count
        file_tokens = sum(max(0, int(file.tokens)) for file in files)
        history_tokens = counter.count_messages(history, provider=provider_name, model=model_name).count
        tool_tokens = counter.count(tools_text, provider=provider_name, model=model_name).count
        message_tokens = counter.count_messages(messages, provider=provider_name, model=model_name).count
        total = system_tokens + rules_tokens + file_tokens + history_tokens + tool_tokens + message_tokens
        return {
            "system": system_tokens,
            "rules": rules_tokens,
            "files": file_tokens,
            "history": history_tokens,
            "tools": tool_tokens,
            "messages": message_tokens,
            "total": total,
        }

    def _snapshot_key(
        self,
        *,
        rules: str,
        files: Tuple[ContextFile, ...],
        history: Sequence[Dict[str, Any]],
        tool_schemas: Sequence[Dict[str, Any]],
        provider_name: str,
        model_name: str,
    ) -> str:
        history_hash = hashlib.sha256(self._stable_json(history).encode("utf-8", errors="replace")).hexdigest()
        payload = {
            "rules": rules,
            "files": [(file.path, file.content) for file in files],
            "historyHash": history_hash,
            "toolSchemas": tool_schemas,
            "provider": provider_name,
            "model": model_name,
        }
        return hashlib.sha256(self._stable_json(payload).encode("utf-8", errors="replace")).hexdigest()

    def _system_prompt(self) -> str:
        return str(getattr(self._core, "_system_instruction", "") or "")

    @staticmethod
    def _stable_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
