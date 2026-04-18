"""
PoorCLI Core Engine - Headless AI coding assistant

This module provides a headless engine used by the PoorCLI terminal client and
the Neovim plugin.
"""

import asyncio
import hashlib
import json
import os
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from .providers.base import ProviderResponse, FunctionCall, UsageMetadata
from .core_events import CoreEvent
from .providers.capability import ProviderCapability, provider_has_capability
from .context_assembly import ContextAssemblyOrchestrator, ContextSnapshot
from .token_counter import get_token_counter
from .economy import (
    EconomyTurnReport,
    distill_prompt,
)
from .token_budget_controller import (
    TurnOutcome as BudgetTurnOutcome,
    build_state_from_engine,
)
from .kv_cache_store import build_cache_friendly_prompt, is_local_inference
from .semantic_cache import (
    compute_context_hash,
)
from .prompts import (
    build_fim_prompt as _build_fim_prompt,
    get_system_instruction,
)
from .exceptions import (
    PoorCLIError,
    APIRateLimitError,
    APIError,
    setup_logger,
)

logger = setup_logger(__name__)

_DEFAULT_CONFIDENCE_PERCENT = 50
_CONFIDENCE_PERCENT_RE = re.compile(r"confidence[^\n\r]*?(\d{1,3})\s*%", re.IGNORECASE)
_CONFIDENCE_LINE_RE = re.compile(r"^confidence\b[^\n\r]*$", re.IGNORECASE)
_CONFIDENCE_BANDS: Tuple[Tuple[int, str], ...] = (
    (20, "Very Low"),
    (40, "Low"),
    (60, "Moderate"),
    (80, "High"),
    (100, "Very High"),
)
_MUTATING_TOOLS = {
    "write_file",
    "edit_file",
    "delete_file",
    "apply_patch_unified",
    "json_yaml_edit",
}
_MAX_RUN_TRANSITIONS = 160
_MAX_RUN_TURN_SUMMARIES = 80


# ── CoreEvent: structured events yielded by the agentic loop ─────────





class AgentLoop:
    async def _assemble_context_snapshot(
        self,
        message: str,
        *,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        activate_tools: bool = True,
    ) -> ContextSnapshot:
        assembler = getattr(self, "_context_assembly", None)
        if assembler is None:
            assembler = ContextAssemblyOrchestrator(self)
            self._context_assembly = assembler
        snapshot = await assembler.assemble(
            prompt=message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
            activate_tools=activate_tools,
        )
        self._last_context_snapshot = snapshot
        return snapshot

    def _block_cache_provider_message(self, message: Any, snapshot: ContextSnapshot) -> Any:
        if not isinstance(message, str) or not self.provider:
            return message
        if getattr(self.provider, "prompt_caching", True) is False:
            return message
        block_cache = getattr(self, "_block_cache", None)
        if block_cache is None:
            return message
        get_provider_name = getattr(self.provider, "get_provider_name", None)
        if callable(get_provider_name):
            provider_name = get_provider_name()
        else:
            model_cfg = getattr(getattr(self, "config", None), "model", None)
            provider_name = str(getattr(model_cfg, "provider", "") or "")
        block_capable = provider_name == "openai" or provider_has_capability(
            self.provider,
            ProviderCapability.PROMPT_CACHING_BLOCK,
        )
        return block_cache.provider_message(
            message,
            snapshot.files,
            provider_name=provider_name,
            block_capable=block_capable,
        )

    async def send_message_events(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        request_id: str = "",
        source_kind: str = "session",
        source_id: str = "",
        artifact_dir: str = "",
        run_metadata: Optional[Dict[str, Any]] = None,
        max_response_tokens: Optional[int] = None,
    ) -> AsyncIterator[CoreEvent]:
        """
        Send a message and yield CoreEvent objects (structured agentic events).

        This is the primary method for streaming clients. It yields tool_call_start,
        tool_result, text_chunk, cost_update, progress, and done events.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        await self._ensure_provider_ready()

        self._turn_tool_cache.clear() # reset per-turn read-only tool cache
        self._task_input_tokens = 0 # reset per-task counters
        self._task_output_tokens = 0
        self._task_cost_usd = 0.0
        self._task_cache_creation_input_tokens = 0
        self._task_cache_read_input_tokens = 0
        self._turn_cost_recorded = False
        self._turn_economy = EconomyTurnReport()
        # per-turn output token cap
        _saved_max_output = None
        if max_response_tokens and max_response_tokens > 0 and self.provider:
            _saved_max_output = getattr(self.provider, "economy_max_output_tokens", 0)
            self.provider.economy_max_output_tokens = max_response_tokens
        self._refresh_system_context()

        # Check cost guardrails before processing
        cost_reason = self._check_cost_guardrails()
        if cost_reason:
            yield CoreEvent.text_chunk(f"[Cost guardrail] {cost_reason}", request_id)
            yield CoreEvent.done(reason="cost_limit")
            return

        cancel_event = self._prepare_cancel_event(request_id)
        max_iterations = self.config.agentic.max_iterations if self.config else 25
        iteration = 0
        if self._context_manager:
            self._context_manager.advance_turn()
        turn_diagnostics = self._new_run_turn_diagnostics(max_iterations=max_iterations)
        resolved_source_id = str(source_id or request_id or "session").strip() or "session"
        self._append_turn_transition(
            turn_diagnostics,
            reason_code="run_started",
            iteration=0,
            details={
                "sourceKind": source_kind,
                "sourceId": resolved_source_id,
            },
        )
        run_state = self._start_run_record(
            source_kind=source_kind,
            source_id=resolved_source_id,
            artifact_dir=artifact_dir,
            metadata=run_metadata,
        )
        last_checkpoint_id: Optional[str] = None

        logger.info(f"Sending message (events): {message[:100]}...")
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
            request_id=request_id,
        )
        builtin_workspace_map = await self._maybe_builtin_workspace_map(message)
        if builtin_workspace_map is not None:
            if self.history_adapter:
                self.history_adapter.add_message("user", message)
                self.history_adapter.add_message("model", builtin_workspace_map)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="builtin_command",
                iteration=0,
                details={"command": "/workspace-map"},
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=builtin_workspace_map or "workspace map",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="builtin_command",
                ),
            )
            yield CoreEvent.text_chunk(builtin_workspace_map, request_id)
            yield CoreEvent.done(reason="builtin_command")
            return
        context_snapshot = await self._assemble_context_snapshot(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        full_message = context_snapshot.message
        turn_diagnostics["promptLayers"] = {
            "userPromptChars": len(message or ""),
            "fullMessageChars": len(full_message or ""),
            "explicitContextFileCount": len(context_files or []),
            "pinnedContextFileCount": len(pinned_context_files or []),
            "selectedContextFileCount": len(
                (self._last_context_preview.get("selected") if isinstance(self._last_context_preview, dict) else [])
                or []
            ),
            "gitContextInjected": "[Git context]" in (full_message or ""),
        }

        # Economy: context dedup — strip file blocks already in session
        try:
            if self.config and (self.config.economy.context_dedup or self.config.economy.dedup_context):
                full_message, dedup_saved = self._dedup_context_files(full_message)
                if dedup_saved > 0:
                    self._economy_tracker.record_dedup(dedup_saved)
                    self._turn_economy.dedup_tokens_saved += dedup_saved
        except (AttributeError, TypeError) as e:
            logger.warning("economy context_dedup failed: %s", e)

        # Economy: prompt distillation
        try:
            eco = self.config.economy if self.config else None
            if eco and eco.prompt_distill:
                tokens_before = get_token_counter().count(full_message).count
                full_message, tokens_saved = distill_prompt(full_message, "", eco)
                if tokens_saved > 0:
                    self._economy_tracker.record_distillation(tokens_before, tokens_before - tokens_saved)
                    self._turn_economy.distillation_tokens_saved += tokens_saved
        except (AttributeError, TypeError) as e:
            logger.warning("economy prompt_distill failed: %s", e)

        # Economy: smart model downshift for simple prompts
        try:
            self._maybe_downshift_model(message)
        except Exception as e:
            logger.warning("economy model_downshift failed: %s", e)

        # Economy: apply output token cap
        try:
            self._apply_economy_max_tokens()
        except Exception as e:
            logger.warning("economy max_tokens cap failed: %s", e)

        # Token budget controller: observe state and decide action
        self._turn_start_mono = time.monotonic()
        self._turn_tool_call_count = 0
        try:
            eco = self.config.economy if self.config else None
            preset = eco.preset if eco else "balanced"
            cp = self.get_context_pressure() if self.provider else {}
            complexity_str = self._turn_economy.routed_complexity or "simple"
            recent_5 = self._recent_turn_failures[-5:]
            recent_fails = sum(1 for f in recent_5 if f)
            self._budget_state = build_state_from_engine(
                complexity_str=complexity_str,
                context_pressure_pct=float(cp.get("pressure_pct", 0)),
                turn_number=iteration,
                economy_preset=preset,
                provider=self.config.model.provider if self.config else "",
                model_tier=self._turn_economy.routed_model or "balanced",
                recent_failures=recent_fails,
                recent_turns=max(len(recent_5), 1),
            )
            self._budget_action = self._budget_controller.decide(self._budget_state)
            # apply data-driven thinking budget override
            try:
                if self.provider and provider_has_capability(self.provider, ProviderCapability.EXTENDED_THINKING):
                    self._budget_action.max_thinking_tokens = self._thinking_optimizer.allocate(
                        self.provider,
                        self._budget_state.task_complexity,
                        self._budget_state.economy_mode,
                    )
                else:
                    self._budget_action.max_thinking_tokens = 0
            except Exception as e:
                logger.warning("thinking_optimizer override failed: %s", e)
            # wire thinking budget to provider
            if self.provider:
                self.provider.economy_max_thinking_tokens = self._budget_action.max_thinking_tokens
            logger.info(
                "budget_controller: tier=%s thinking=%d output=%d compress=%.2f compact=%s",
                self._budget_action.model_tier,
                self._budget_action.max_thinking_tokens,
                self._budget_action.max_output_tokens,
                self._budget_action.compression_ratio,
                self._budget_action.should_compact,
            )
        except Exception as e:
            logger.warning("budget controller decide failed: %s", e)
            self._budget_state = None
            self._budget_action = None

        # Economy: reset idle auto-compact timer
        try:
            self._reset_idle_compact_timer()
        except Exception as e:
            logger.warning("economy idle_compact_timer failed: %s", e)

        # Working memory: delta-mode substitution
        try:
            wm_mgr = self._ensure_working_memory_mgr()
            if wm_mgr and wm_mgr.memory is not None:
                history_tokens = get_token_counter().count(full_message).count
                active_files: Dict[str, str] = {}
                if self._context_manager:
                    for fc in getattr(self._context_manager, "_last_selected_files", []):
                        p = getattr(fc, "path", None)
                        c = getattr(fc, "content", None)
                        if p and c:
                            active_files[str(p)] = c
                tool_results = getattr(self, "_last_tool_results", None)
                caps = self.provider.get_capabilities() if self.provider else None
                max_ctx = int(caps.max_context_tokens) if caps and caps.max_context_tokens else 100_000
                pressure = history_tokens / max_ctx if max_ctx > 0 else 0.0
                delta_prompt, wm_metrics = wm_mgr.pre_turn(
                    user_message=message,
                    current_files=active_files,
                    context_pressure=pressure,
                    full_history_tokens=history_tokens,
                    tool_results=tool_results,
                )
                if delta_prompt: # delta mode active — substitute prompt
                    full_message = delta_prompt
                    self._pending_events.append(CoreEvent(
                        type="progress",
                        data={
                            "phase": "working_memory",
                            "message": f"delta mode: ~{wm_metrics.tokens_saved} tokens saved ({wm_metrics.savings_pct:.0f}%)",
                        },
                    ))
        except Exception as e:
            logger.warning("working memory pre-turn failed: %s", e)

        # Economy: compute context hash for semantic cache keying
        # PRD 004: fold in system-prompt and tool-schema fingerprints so edits
        # to either invalidate previously-cached answers.
        tool_schema_hash = None
        try:
            decls = getattr(self, "_active_tool_declarations", None)
            if decls:
                tool_schema_hash = hashlib.sha256(
                    json.dumps(decls, sort_keys=True, default=str).encode("utf-8", errors="replace")
                ).hexdigest()
        except Exception:
            tool_schema_hash = None
        self._last_context_hash = compute_context_hash(
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            model_name=self.provider.model_name if self.provider else "",
            system_prompt_hash=getattr(self, "_system_context_hash", None),
            tool_schema_hash=tool_schema_hash,
        )

        # Economy: response cache lookup (exact match, then semantic)
        cached_response = None
        try:
            cached_response = self._cache_lookup(full_message)
        except Exception as e:
            logger.warning("economy cache_lookup failed: %s", e)
        if cached_response is None:
            try:
                cached_response = await self._semantic_cache_lookup(message, self._last_context_hash)
            except Exception as e:
                logger.warning("semantic cache_lookup failed: %s", e)
        if cached_response is not None:
            self._economy_tracker.record_cache_hit()
            self._turn_economy.cache_hit = True
            yield CoreEvent.text_chunk(cached_response, request_id)
            savings = self._economy_tracker.get_summary()
            if any(v for v in savings.values()):
                yield CoreEvent.economy_savings(savings)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="cache_hit",
                iteration=0,
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary="cache hit",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="cache_hit",
                ),
            )
            self._restore_model()
            self._record_cost_turn(request_id, "cache_hit")
            yield CoreEvent.done(reason="cache_hit")
            return

        if self.history_adapter:
            self.history_adapter.add_message("user", message)

        # Apply pending background LLM compression from previous turn
        try:
            if self._pending_llm_compression and self._pending_llm_compression.done() and self.provider:
                compressed = self._pending_llm_compression.result()
                if compressed:
                    self.provider.set_history(compressed)
                    logger.info("Applied deferred LLM compression: %d messages", len(compressed))
                self._pending_llm_compression = None
        except Exception as e:
            logger.warning("deferred LLM compression failed: %s", e)
            self._pending_llm_compression = None

        # Compress conversation context if configured and threshold exceeded
        try:
            cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
            eco_compress = getattr(self.config.economy, "compress_after_turns", 0) if self.config else 0
            if cc_cfg and eco_compress > 0: # economy preset overrides compression threshold
                from dataclasses import replace as _dc_replace
                cc_cfg = _dc_replace(cc_cfg, compress_after_turns=eco_compress) # copy, don't mutate shared config
            if cc_cfg and getattr(cc_cfg, "enabled", False) and self.provider:
                history = self.provider.get_history()
                if self._context_compressor.should_compress(history, cc_cfg):
                    before = len(history)
                    from .context_compressor import CompactionStrategy
                    strategy = self._context_compressor.select_strategy(history, cc_cfg)
                    if strategy == CompactionStrategy.LLM:
                        # apply instant non-LLM compression now, defer LLM to background
                        compressed = self._context_compressor.compress(history, cc_cfg)
                        self.provider.set_history(compressed)
                        after = len(compressed)
                        self._pending_llm_compression = asyncio.create_task(
                            self._context_compressor.compress_with_llm(history, cc_cfg, self.provider)
                        )
                    else:
                        _strip_chars = getattr(self.config.economy, "tool_strip_chars", 200) if self.config else 200
                        compressed = await self._context_compressor.compress_auto(
                            history, cc_cfg, provider=self.provider,
                            tool_strip_chars=_strip_chars,
                        )
                        self.provider.set_history(compressed)
                        after = len(compressed)
                    logger.info("Compressed conversation context: %d -> %d messages", before, after)
                    compaction_events = turn_diagnostics.get("compactionEvents")
                    if isinstance(compaction_events, list):
                        compaction_events.append(
                            {
                                "strategy": "compress",
                                "messagesBefore": before,
                                "messagesAfter": after,
                            }
                        )
                    self._pending_events.append(CoreEvent(
                        type="progress",
                        data={"phase": "compression", "message": f"context compressed: {before} \u2192 {after} messages ({100 - after * 100 // max(before, 1)}% reduction)"},
                    ))
        except (AttributeError, TypeError) as e:
            logger.warning("context compression failed: %s", e)

        # Auto LLM compaction when token usage exceeds threshold
        try:
            cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
            if cc_cfg and getattr(cc_cfg, "enabled", False) and self.provider:
                threshold_ratio = getattr(cc_cfg, "token_threshold_for_llm_compact", 0.8)
                if threshold_ratio > 0:
                    caps = self.provider.get_capabilities()
                    max_ctx = caps.max_context_tokens
                    total_used = self._session_total_input_tokens + self._session_total_output_tokens
                    if max_ctx > 0 and total_used > max_ctx * threshold_ratio:
                        history = self.provider.get_history()
                        msgs_before = len(history)
                        if msgs_before > 2: # only compact if enough history
                            result = await self._compact_summarize(history, msgs_before)
                            logger.info("Auto LLM compact triggered: %s", result)
                            compaction_events = turn_diagnostics.get("compactionEvents")
                            if isinstance(compaction_events, list):
                                compaction_events.append(
                                    {
                                        "strategy": str(result.get("strategy", "llm_compact") or "llm_compact"),
                                        "messagesBefore": msgs_before,
                                        "messagesAfter": int(result.get("messages_after", 0) or 0),
                                    }
                                )
                            self._pending_events.append(CoreEvent(
                                type="progress",
                                data={"phase": "llm_compact", "message": f"auto LLM compact: {msgs_before} \u2192 {result.get('messages_after', 0)} messages"},
                            ))
        except (AttributeError, TypeError) as e:
            logger.warning("auto LLM compaction failed: %s", e)

        try:
            accumulated_text = ""

            def _observe_event(event: CoreEvent) -> None:
                nonlocal last_checkpoint_id
                if event.type != "tool_result":
                    return
                checkpoint_id = event.data.get("checkpointId")
                if checkpoint_id:
                    last_checkpoint_id = str(checkpoint_id)
                self._record_mutation_summary(
                    tool_name=str(event.data.get("toolName", "")),
                    result=event.data,
                )
                self._record_tool_cost_surface(str(event.data.get("toolName", "")), str(event.data.get("toolResult", "")))
                tool_name = event.data.get("toolName", "")
                if tool_name in ("write_todos", "update_todo") and self.tool_registry:
                    todos = self.tool_registry._todos
                    completed = sum(1 for t in todos if t.get("status") == "completed")
                    self._pending_events.append(CoreEvent.todo_update(todos, completed, len(todos)))

            # KV cache: reorder context for cache-friendly prefix (local inference only)
            if self._kv_cache_store and isinstance(full_message, str) and is_local_inference(self.config.model.provider if self.config else ""):
                try:
                    ctx_files = [(fc.path, fc.content) for fc in getattr(self._context_manager, "_last_selected_files", []) if hasattr(fc, "path") and hasattr(fc, "content")]
                    if ctx_files:
                        full_message = build_cache_friendly_prompt(ctx_files, message, store=self._kv_cache_store)
                except Exception as e:
                    logger.debug("kv cache prompt reorder skipped: %s", e)
            provider_message = self._maybe_apply_vision(full_message) # multimodal if images detected
            provider_message = self._block_cache_provider_message(provider_message, context_snapshot)
            async for chunk in self.provider.send_message_stream(provider_message):
                if cancel_event.is_set():
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="cancelled",
                        iteration=iteration,
                    )
                    self._finish_run_record(
                        run_state,
                        status="cancelled",
                        summary="cancelled",
                        error_message="cancelled",
                        checkpoint_id=last_checkpoint_id,
                        artifact_dir=artifact_dir,
                        metadata_updates=self._build_run_metadata_updates(
                            request_id=request_id,
                            diagnostics=turn_diagnostics,
                            completion_reason_code="cancelled",
                        ),
                    )
                    yield CoreEvent.done(reason="cancelled")
                    return

                if chunk.function_calls:
                    self._turn_tool_call_count += len(chunk.function_calls)
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="provider_requested_tools",
                        iteration=iteration,
                        details={"callCount": len(chunk.function_calls)},
                    )
                    # extract usage from structured UsageMetadata or metadata dict
                    u = chunk.usage
                    _sys, _hist, _tool = self._compute_token_breakdown()
                    if u:
                        estimated_cost = self._track_cost(
                            u.input_tokens,
                            u.output_tokens,
                            cache_creation_input_tokens=u.cache_creation_input_tokens,
                            cache_read_input_tokens=u.cache_read_input_tokens,
                        )
                        yield CoreEvent.cost_update(
                            input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                            estimated_cost=estimated_cost,
                            cache_creation_input_tokens=u.cache_creation_input_tokens,
                            cache_read_input_tokens=u.cache_read_input_tokens,
                            cumulative_input_tokens=self._session_total_input_tokens,
                            cumulative_output_tokens=self._session_total_output_tokens,
                            system_tokens=_sys, history_tokens=_hist, tool_result_tokens=_tool,
                        )
                    elif chunk.metadata:
                        usage = chunk.metadata.get("usage", {})
                        if usage:
                            estimated_cost = self._track_cost(
                                usage.get("input_tokens", 0),
                                usage.get("output_tokens", 0),
                                cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
                                cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
                            )
                            yield CoreEvent.cost_update(
                                input_tokens=usage.get("input_tokens", 0),
                                output_tokens=usage.get("output_tokens", 0),
                                estimated_cost=estimated_cost,
                                cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
                                cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
                                cumulative_input_tokens=self._session_total_input_tokens,
                                cumulative_output_tokens=self._session_total_output_tokens,
                                system_tokens=_sys, history_tokens=_hist, tool_result_tokens=_tool,
                            )
                    # emit context pressure alongside cost update
                    _total_ctx = _sys + _hist + _tool
                    _max_ctx = self.provider.get_capabilities().max_context_tokens if self.provider else 0
                    if _max_ctx > 0:
                        _pct = round(_total_ctx / _max_ctx * 100, 1)
                        yield CoreEvent.context_pressure(_total_ctx, _max_ctx, _pct)
                        # auto-compress if pressure exceeds threshold
                        try:
                            _compress_result = await self._auto_compress_on_pressure()
                            if _compress_result:
                                yield CoreEvent.progress("auto_compress", f"Context auto-compressed ({_compress_result})")
                        except Exception:
                            pass

                    tool_results = await self._handle_function_calls_events(
                        chunk,
                        iteration,
                        max_iterations,
                        request_id,
                        message,
                        turn_diagnostics=turn_diagnostics,
                        diff_review_interactive=(source_kind == "session"),
                    )
                    for ev in self._pending_events:
                        _observe_event(ev)
                        yield ev
                    self._pending_events = []

                    response, stream_events = await self._stream_and_collect(tool_results, request_id)
                    for ev in stream_events:
                        _observe_event(ev)
                        yield ev
                        if ev.type == "text_chunk":
                            accumulated_text += ev.data["chunk"]

                    while response.function_calls:
                        iteration += 1
                        if cancel_event.is_set():
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="cancelled",
                                iteration=iteration,
                            )
                            self._finish_run_record(
                                run_state,
                                status="cancelled",
                                summary="cancelled",
                                error_message="cancelled",
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="cancelled",
                                ),
                            )
                            yield CoreEvent.done(reason="cancelled")
                            return
                        if iteration >= max_iterations:
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="iteration_cap_reached",
                                iteration=iteration,
                            )
                            self._finish_run_record(
                                run_state,
                                status="failed",
                                summary="iteration cap reached",
                                error_message="iteration cap reached",
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="iteration_cap",
                                ),
                            )
                            yield CoreEvent.done(reason="iteration_cap")
                            return

                        # Context pressure check
                        pressure_reason = self._check_context_pressure()
                        if pressure_reason:
                            self._append_turn_transition(turn_diagnostics, reason_code="context_pressure", iteration=iteration)
                            self._finish_run_record(
                                run_state, status="stopped", summary="context pressure",
                                checkpoint_id=last_checkpoint_id, artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id, diagnostics=turn_diagnostics,
                                    completion_reason_code="context_pressure",
                                ),
                            )
                            yield CoreEvent.done(reason="context_pressure")
                            return

                        # Economy: tool call budget enforcement
                        eco_budget = getattr(self.config.economy, "tool_call_budget", 0) if self.config else 0
                        if eco_budget > 0 and iteration >= eco_budget:
                            self._economy_tracker.record_tool_calls_avoided(max_iterations - iteration)
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="economy_tool_budget_reached",
                                iteration=iteration,
                                details={"budget": int(eco_budget)},
                            )
                            self._finish_run_record(
                                run_state,
                                status="completed",
                                summary="economy tool budget reached",
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="economy_tool_budget",
                                ),
                            )
                            yield CoreEvent.text_chunk(f"\n[Economy] Tool call budget reached ({eco_budget})", request_id)
                            yield CoreEvent.economy_savings(self._economy_tracker.get_summary())
                            yield CoreEvent.done(reason="economy_tool_budget")
                            self._restore_model()
                            return

                        yield CoreEvent.progress("tool_loop", f"Iteration {iteration}/{max_iterations}", iteration, max_iterations)

                        tool_results = await self._handle_function_calls_events(
                            response,
                            iteration,
                            max_iterations,
                            request_id,
                            message,
                            turn_diagnostics=turn_diagnostics,
                            diff_review_interactive=(source_kind == "session"),
                        )
                        for ev in self._pending_events:
                            _observe_event(ev)
                            yield ev
                        self._pending_events = []

                        response, stream_events = await self._stream_and_collect(tool_results, request_id)
                        for ev in stream_events:
                            _observe_event(ev)
                            yield ev
                            if ev.type == "text_chunk":
                                accumulated_text += ev.data["chunk"]

                        # Emit 80% budget warning if approaching limits
                        cost_warning = self._check_cost_warning()
                        if cost_warning:
                            yield CoreEvent.text_chunk(f"\n[Budget warning] {cost_warning}", request_id)
                        # Check cost guardrails mid-loop
                        cost_reason = self._check_cost_guardrails()
                        if cost_reason:
                            self._append_turn_transition(
                                turn_diagnostics,
                                reason_code="cost_guardrail_triggered",
                                iteration=iteration,
                                details={"reason": str(cost_reason)},
                            )
                            self._finish_run_record(
                                run_state,
                                status="failed",
                                summary=cost_reason,
                                error_message=cost_reason,
                                checkpoint_id=last_checkpoint_id,
                                artifact_dir=artifact_dir,
                                metadata_updates=self._build_run_metadata_updates(
                                    request_id=request_id,
                                    diagnostics=turn_diagnostics,
                                    completion_reason_code="cost_limit",
                                ),
                            )
                            yield CoreEvent.text_chunk(f"\n[Cost guardrail] {cost_reason}", request_id)
                            yield CoreEvent.done(reason="cost_limit")
                            return

                    break

                else:
                    thinking = getattr(chunk, "thinking_content", None)
                    if thinking:
                        yield CoreEvent.thinking_chunk(thinking, request_id)
                    if chunk.content:
                        accumulated_text += chunk.content
                        yield CoreEvent.text_chunk(chunk.content, request_id)
                        # live estimated token count per chunk
                        est_out = get_token_counter().count(accumulated_text).count
                        yield CoreEvent.cost_update(
                            output_tokens=est_out,
                            is_estimate=True,
                            cumulative_input_tokens=self._session_total_input_tokens,
                            cumulative_output_tokens=self._session_total_output_tokens + est_out,
                        )

            accumulated_text, confidence_suffix = self._ensure_confidence_line(accumulated_text)
            if confidence_suffix:
                yield CoreEvent.text_chunk(confidence_suffix, request_id)

            # emit final confidence score so the client can display it
            _conf_pct = self._extract_confidence_percent(accumulated_text) or _DEFAULT_CONFIDENCE_PERCENT
            yield CoreEvent.cost_update(
                confidence_percent=_conf_pct,
                confidence_category=self._confidence_bucket(_conf_pct),
            )

            # architect mode: if architect responded with a plan, switch to editor for next turn
            if self._architect_mode and self._architect_mode.enabled and accumulated_text:
                if self._architect_mode.should_switch_to_editor(accumulated_text):
                    try:
                        await self._architect_mode.switch_to_editor(self, accumulated_text)
                    except Exception as e:
                        logger.warning("architect->editor switch failed: %s", e)
                elif self._architect_mode.phase == "editor":
                    try:
                        await self._architect_mode.reset_to_architect(self)
                    except Exception as e:
                        logger.warning("editor->architect reset failed: %s", e)

            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)

            # Working memory: post-turn update (confusion detection + memory persist)
            try:
                wm_mgr = self._working_memory_mgr
                if wm_mgr and accumulated_text:
                    history_text = ""
                    if self.history_adapter:
                        history_text = "\n".join(
                            f"{m.get('role','')}: {str(m.get('content',''))[:200]}"
                            for m in (self.get_history() if self._initialized and self.provider else [])
                        )
                    wm_mgr.post_turn(accumulated_text, history_text)
            except Exception as e:
                logger.warning("working memory post-turn failed: %s", e)

            self._append_turn_transition(
                turn_diagnostics,
                reason_code="completed",
                iteration=iteration,
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=accumulated_text or "completed",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="complete",
                ),
            )

            # Economy: store response in cache (exact + semantic)
            try:
                self._cache_store(full_message, accumulated_text)
            except Exception:
                pass
            try:
                await self._semantic_cache_store(message, self._last_context_hash, accumulated_text)
            except Exception:
                pass

            try:
                queued = self._schedule_auto_compaction()
                if queued:
                    yield CoreEvent.progress(
                        "auto_compact",
                        "auto compact queued"
                        f" ({queued.get('utilization_before_pct', 0)}% -> {queued.get('target_utilization_pct', 0)}%)",
                    )
            except Exception as e:
                logger.warning("auto compact scheduling failed: %s", e)

            # Token budget controller: observe outcome and log
            try:
                if self._budget_state and self._budget_action:
                    elapsed = time.monotonic() - self._turn_start_mono
                    task_ok = bool(accumulated_text and len(accumulated_text) > 10)
                    outcome = BudgetTurnOutcome(
                        task_succeeded=task_ok,
                        user_retried=False,
                        total_tokens_used=self._task_input_tokens + self._task_output_tokens,
                        input_tokens=self._task_input_tokens,
                        output_tokens=self._task_output_tokens,
                        response_time_seconds=round(elapsed, 2),
                        tool_calls_made=self._turn_tool_call_count,
                    )
                    self._budget_controller.observe(self._budget_state, self._budget_action, outcome)
                    self._budget_logger.log(self._budget_state, self._budget_action, outcome)
                    self._recent_turn_failures.append(not task_ok)
                    if len(self._recent_turn_failures) > 10:
                        self._recent_turn_failures = self._recent_turn_failures[-10:]
            except Exception as e:
                logger.warning("budget controller observe failed: %s", e)

            # Economy: emit savings summary and restore model
            savings = self._economy_tracker.get_summary()
            if any(v for v in savings.values()):
                yield CoreEvent.economy_savings(savings)
            # emit per-turn economy report
            from dataclasses import asdict as _turn_asdict
            _report = _turn_asdict(self._turn_economy)
            if any(v for v in _report.values()):
                yield CoreEvent.economy_turn_report(_report)
            self._restore_model()
            # restore per-turn output cap
            if _saved_max_output is not None and self.provider:
                self.provider.economy_max_output_tokens = _saved_max_output

            self._record_cost_turn(request_id, "complete")
            yield CoreEvent.done(reason="complete")
            logger.info(f"Message complete (events), {len(accumulated_text)} chars")

        except (APIRateLimitError, APIError) as e:
            self._last_provider_error = str(e)
            # Attempt provider fallback on rate-limit / server errors
            if self._fallback_manager and self.provider:
                previous_provider = self.config.model.provider if self.config else ""
                fallback_provider = await self._fallback_manager.try_fallback(
                    previous_provider,
                    e,
                    tools=self._tool_declarations_for_shipping(),
                    system_instruction=self._system_instruction,
                )
                if fallback_provider:
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="fallback_switch",
                        details={
                            "from": previous_provider,
                            "to": fallback_provider.get_provider_name(),
                        },
                    )
                    self._last_fallback_summary = {
                        "from": previous_provider,
                        "to": fallback_provider.get_provider_name(),
                        "reason": str(e),
                    }
                    logger.info("Falling back to %s", fallback_provider.get_provider_name())
                    yield CoreEvent.text_chunk(
                        f"[Fallback] Switching to {fallback_provider.get_provider_name()}\n", request_id
                    )
                    self.provider = fallback_provider
                    self._provider_ready = True
                    # Retry with fallback provider (non-recursive, single retry)
                    try:
                        async for chunk in self.provider.send_message_stream(full_message):
                            if chunk.content:
                                accumulated_text += chunk.content
                                yield CoreEvent.text_chunk(chunk.content, request_id)
                        self._append_turn_transition(
                            turn_diagnostics,
                            reason_code="completed",
                            iteration=iteration,
                            details={"viaFallback": True},
                        )
                        self._finish_run_record(
                            run_state,
                            status="completed",
                            summary=accumulated_text or "completed",
                            checkpoint_id=last_checkpoint_id,
                            artifact_dir=artifact_dir,
                            metadata_updates=self._build_run_metadata_updates(
                                request_id=request_id,
                                diagnostics=turn_diagnostics,
                                completion_reason_code="complete",
                            ),
                        )
                        yield CoreEvent.done(reason="complete")
                        return
                    except Exception as fallback_err:
                        self._last_provider_error = str(fallback_err)
                        logger.error("Fallback provider also failed: %s", fallback_err)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="provider_error",
                iteration=iteration,
                details={"message": str(e)},
            )
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="provider_error",
                ),
            )
            suggestions = self._error_recovery.get_suggestions(e)
            if suggestions:
                hint = self._error_recovery.format_suggestions(suggestions)
                yield CoreEvent.text_chunk(f"\n{hint}", request_id)
            raise PoorCLIError(f"Failed to send message: {e}")
        except Exception as e:
            logger.exception("Error sending message (events)")
            self._last_provider_error = str(e)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="exception",
                iteration=iteration,
                details={"message": str(e)},
            )
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    request_id=request_id,
                    diagnostics=turn_diagnostics,
                    completion_reason_code="exception",
                ),
            )
            raise PoorCLIError(f"Failed to send message: {e}")
        finally:
            self._clear_cancel_event(request_id)
            # always restore per-turn output cap, even on exception
            if _saved_max_output is not None and self.provider:
                self.provider.economy_max_output_tokens = _saved_max_output

    async def _stream_and_collect(
        self,
        message: Any,
        request_id: str = "",
    ) -> Tuple["ProviderResponse", List["CoreEvent"]]:
        """Stream a provider call, collecting events and building a response."""
        accumulated_text = ""
        accumulated_chars = 0
        _chunk_count = 0
        function_calls: Optional[List[FunctionCall]] = None
        metadata: Dict[str, Any] = {}
        events: List[CoreEvent] = []
        last_usage: Optional[UsageMetadata] = None
        async for chunk in self.provider.send_message_stream(message):
            if chunk.usage:
                last_usage = chunk.usage
            if chunk.function_calls:
                function_calls = chunk.function_calls
                if chunk.metadata:
                    metadata = chunk.metadata
            else:
                thinking = getattr(chunk, "thinking_content", None)
                if thinking:
                    events.append(CoreEvent.thinking_chunk(thinking, request_id))
                if chunk.content:
                    accumulated_text += chunk.content
                    accumulated_chars += len(chunk.content)
                    _chunk_count += 1
                    events.append(CoreEvent.text_chunk(chunk.content, request_id))
                    # throttled live estimated cost (every 10 chunks to reduce noise)
                    if _chunk_count % 10 == 0:
                        est_output = get_token_counter().count(accumulated_text).count
                        events.append(CoreEvent.cost_update(
                            output_tokens=est_output,
                            is_estimate=True,
                            cumulative_input_tokens=self._session_total_input_tokens,
                            cumulative_output_tokens=self._session_total_output_tokens + est_output,
                        ))
        # reconcile with actual usage at stream end
        actual_in = 0
        actual_out = 0
        cache_create = 0
        cache_read = 0
        if last_usage:
            actual_in = last_usage.input_tokens
            actual_out = last_usage.output_tokens
            cache_create = last_usage.cache_creation_input_tokens
            cache_read = last_usage.cache_read_input_tokens
        if not actual_in and not actual_out and metadata:
            usage = metadata.get("usage", {})
            if usage:
                actual_in = usage.get("input_tokens", 0)
                actual_out = usage.get("output_tokens", 0)
                cache_create = usage.get("cache_creation_input_tokens", 0)
                cache_read = usage.get("cache_read_input_tokens", 0)
        if actual_in or actual_out:
            estimated_cost = self._track_cost(
                actual_in,
                actual_out,
                cache_creation_input_tokens=cache_create,
                cache_read_input_tokens=cache_read,
            )
            events.append(CoreEvent.cost_update(
                input_tokens=actual_in,
                output_tokens=actual_out,
                estimated_cost=estimated_cost,
                cache_creation_input_tokens=cache_create,
                cache_read_input_tokens=cache_read,
                cumulative_input_tokens=self._session_total_input_tokens,
                cumulative_output_tokens=self._session_total_output_tokens,
            ))
        elif accumulated_chars > 0:
            # no actual usage available, finalize with estimate
            est_output = get_token_counter().count(accumulated_text).count
            estimated_cost = self._track_cost(0, est_output)
            events.append(CoreEvent.cost_update(
                output_tokens=est_output,
                estimated_cost=estimated_cost,
                is_estimate=True,
                cumulative_input_tokens=self._session_total_input_tokens,
                cumulative_output_tokens=self._session_total_output_tokens,
            ))
        response = ProviderResponse(
            content=accumulated_text,
            function_calls=function_calls,
            metadata=metadata,
        )
        return response, events

    async def send_message(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        source_kind: str = "session",
        source_id: str = "",
        artifact_dir: str = "",
        run_metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        Send a message and yield streaming text chunks.

        This method handles function calls internally and yields only text content.
        Legacy interface — streaming clients should use send_message_events().
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        await self._ensure_provider_ready()

        logger.info(f"Sending message: {message[:100]}...")
        run_state = self._start_run_record(
            source_kind=source_kind,
            source_id=str(source_id or "session").strip() or "session",
            artifact_dir=artifact_dir,
            metadata=run_metadata,
        )
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        builtin_workspace_map = await self._maybe_builtin_workspace_map(message)
        if builtin_workspace_map is not None:
            if self.history_adapter:
                self.history_adapter.add_message("user", message)
                self.history_adapter.add_message("model", builtin_workspace_map)
            self._finish_run_record(
                run_state,
                status="completed",
                summary=builtin_workspace_map or "workspace map",
                artifact_dir=artifact_dir,
            )
            yield builtin_workspace_map
            return
        context_snapshot = await self._assemble_context_snapshot(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        full_message = context_snapshot.message

        if self.history_adapter:
            self.history_adapter.add_message("user", message)

        try:
            accumulated_text = ""
            max_iterations = self.config.agentic.max_iterations if self.config else 25
            iteration = 0
            last_checkpoint_id: Optional[str] = None

            provider_message = self._block_cache_provider_message(full_message, context_snapshot)
            async for chunk in self.provider.send_message_stream(provider_message):
                if chunk.function_calls:
                    tool_results = await self._handle_function_calls_events(
                        chunk,
                        iteration,
                        max_iterations,
                        request_id="",
                        user_request=message,
                        diff_review_interactive=(source_kind == "session"),
                    )
                    for ev in self._pending_events:
                        if ev.type == "tool_result":
                            checkpoint_id = ev.data.get("checkpointId")
                            if checkpoint_id:
                                last_checkpoint_id = str(checkpoint_id)
                            self._record_mutation_summary(
                                tool_name=str(ev.data.get("toolName", "")),
                                result=ev.data,
                            )
                    self._pending_events = []
                    response = await self.provider.send_message(tool_results)
                    if response.content:
                        accumulated_text += response.content
                        yield response.content
                    while response.function_calls:
                        iteration += 1
                        if iteration >= max_iterations:
                            break
                        tool_results = await self._handle_function_calls_events(
                            response,
                            iteration,
                            max_iterations,
                            request_id="",
                            user_request=message,
                            diff_review_interactive=(source_kind == "session"),
                        )
                        for ev in self._pending_events:
                            if ev.type == "tool_result":
                                checkpoint_id = ev.data.get("checkpointId")
                                if checkpoint_id:
                                    last_checkpoint_id = str(checkpoint_id)
                                self._record_mutation_summary(
                                    tool_name=str(ev.data.get("toolName", "")),
                                    result=ev.data,
                                )
                        self._pending_events = []
                        response = await self.provider.send_message(tool_results)
                        if response.content:
                            accumulated_text += response.content
                            yield response.content
                    break
                elif chunk.content:
                    accumulated_text += chunk.content
                    yield chunk.content

            accumulated_text, confidence_suffix = self._ensure_confidence_line(accumulated_text)
            if confidence_suffix:
                yield confidence_suffix

            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)

            self._finish_run_record(
                run_state,
                status="completed",
                summary=accumulated_text or "completed",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
            )
            try:
                self._schedule_auto_compaction()
            except Exception as e:
                logger.warning("auto compact scheduling failed: %s", e)

            logger.info(f"Message complete, {len(accumulated_text)} chars")

        except Exception as e:
            logger.exception("Error sending message")
            self._last_provider_error = str(e)
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                artifact_dir=artifact_dir,
            )
            raise PoorCLIError(f"Failed to send message: {e}")

    async def send_message_sync(
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        source_kind: str = "session",
        source_id: str = "",
        artifact_dir: str = "",
        run_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Send a message and return complete response text.
        
        This is a non-streaming version that waits for the complete response.
        Handles function calls internally.
        
        Args:
            message: The message to send to the AI.
            context_files: Optional list of file paths to include as context.
        
        Returns:
            Complete response text from the AI.
        
        Raises:
            PoorCLIError: If not initialized or message sending fails.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        await self._ensure_provider_ready()
        
        logger.info(f"Sending message (sync): {message[:100]}...")
        run_state = self._start_run_record(
            source_kind=source_kind,
            source_id=str(source_id or "session").strip() or "session",
            artifact_dir=artifact_dir,
            metadata=run_metadata,
        )
        max_iterations = self.config.agentic.max_iterations if self.config else 25
        turn_diagnostics = self._new_run_turn_diagnostics(max_iterations=max_iterations)
        self._append_turn_transition(
            turn_diagnostics,
            reason_code="run_started",
            iteration=0,
            details={
                "sourceKind": source_kind,
                "sourceId": str(source_id or "session").strip() or "session",
            },
        )
        await self._record_user_prompt_submission(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        builtin_workspace_map = await self._maybe_builtin_workspace_map(message)
        if builtin_workspace_map is not None:
            if self.history_adapter:
                self.history_adapter.add_message("user", message)
                self.history_adapter.add_message("model", builtin_workspace_map)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="builtin_command",
                iteration=0,
                details={"command": "/workspace-map"},
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=builtin_workspace_map or "workspace map",
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    diagnostics=turn_diagnostics,
                    completion_reason_code="builtin_command",
                ),
            )
            return builtin_workspace_map
        
        context_snapshot = await self._assemble_context_snapshot(
            message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
        )
        full_message = context_snapshot.message
        
        # Save to history
        if self.history_adapter:
            self.history_adapter.add_message("user", message)
        
        try:
            provider_message = self._block_cache_provider_message(full_message, context_snapshot)
            response = await self.provider.send_message(provider_message)
            accumulated_text = response.content or ""
            iteration = 0
            last_checkpoint_id: Optional[str] = None
            iteration_cap_reached = False
            
            # Handle function calls
            while response.function_calls:
                self._append_turn_transition(
                    turn_diagnostics,
                    reason_code="provider_requested_tools",
                    iteration=iteration,
                    details={"callCount": len(response.function_calls)},
                )
                if iteration >= max_iterations:
                    self._append_turn_transition(
                        turn_diagnostics,
                        reason_code="iteration_cap_reached",
                        iteration=iteration,
                    )
                    iteration_cap_reached = True
                    break
                tool_results = await self._handle_function_calls_events(
                    response,
                    iteration,
                    max_iterations,
                    request_id="",
                    user_request=message,
                    turn_diagnostics=turn_diagnostics,
                    diff_review_interactive=(source_kind == "session"),
                )
                for ev in self._pending_events:
                    if ev.type == "tool_result":
                        checkpoint_id = ev.data.get("checkpointId")
                        if checkpoint_id:
                            last_checkpoint_id = str(checkpoint_id)
                        self._record_mutation_summary(
                            tool_name=str(ev.data.get("toolName", "")),
                            result=ev.data,
                        )
                self._pending_events = []
                response = await self.provider.send_message(tool_results)
                if response.content:
                    accumulated_text += response.content
                iteration += 1
            
            accumulated_text, _ = self._ensure_confidence_line(accumulated_text)

            # Save assistant response to history
            if self.history_adapter and accumulated_text:
                self.history_adapter.add_message("model", accumulated_text)

            completion_reason = "iteration_cap" if iteration_cap_reached else "complete"
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="completed" if not iteration_cap_reached else "iteration_cap_reached",
                iteration=iteration,
            )
            self._finish_run_record(
                run_state,
                status="completed",
                summary=accumulated_text or "completed",
                checkpoint_id=last_checkpoint_id,
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    diagnostics=turn_diagnostics,
                    completion_reason_code=completion_reason,
                ),
            )
            try:
                self._schedule_auto_compaction()
            except Exception as e:
                logger.warning("auto compact scheduling failed: %s", e)
            
            logger.info(f"Message complete (sync), {len(accumulated_text)} chars")
            return accumulated_text
            
        except Exception as e:
            logger.exception("Error sending message (sync)")
            self._last_provider_error = str(e)
            self._append_turn_transition(
                turn_diagnostics,
                reason_code="exception",
                details={"message": str(e)},
            )
            self._finish_run_record(
                run_state,
                status="failed",
                summary=str(e),
                error_message=str(e),
                artifact_dir=artifact_dir,
                metadata_updates=self._build_run_metadata_updates(
                    diagnostics=turn_diagnostics,
                    completion_reason_code="exception",
                ),
            )
            raise PoorCLIError(f"Failed to send message: {e}")


    def build_fim_prompt(
        self,
        code_before: str,
        code_after: str,
        instruction: str,
        file_path: str,
        language: str
    ) -> str:
        """
        Build a Fill-in-Middle (FIM) prompt for code completion.
        
        Args:
            code_before: Code before the cursor position.
            code_after: Code after the cursor position.
            instruction: Optional instruction for what to generate.
            file_path: Path to the current file.
            language: Programming language of the file.
        
        Returns:
            FIM prompt string for the AI.
        """
        filename = os.path.basename(file_path) if file_path else "unknown"
        
        # Determine provider for native FIM format selection
        provider_name = self.config.model.model_name if self.config else "generic"
        
        # Use the prompts module for consistent FIM formatting
        return _build_fim_prompt(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            filename=filename,
            language=language,
            provider=provider_name
        )

    async def inline_complete(
        self,
        code_before: str,
        code_after: str,
        instruction: str,
        file_path: str,
        language: str,
        *,
        request_id: str = "",
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Generate inline code completion (FIM - Fill in Middle).
        
        This is the main method for Windsurf-like ghost text completion.
        
        Args:
            code_before: Code before the cursor position.
            code_after: Code after the cursor position.
            instruction: Optional instruction for what to generate.
            file_path: Path to the current file.
            language: Programming language of the file.
        
        Yields:
            Code completion chunks as they arrive.
        
        Raises:
            PoorCLIError: If not initialized or completion fails.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        await self._ensure_provider_ready()

        cancel_event = self._prepare_cancel_event(request_id)
        logger.info(f"Inline complete for {file_path} ({language})")

        prompt = self.build_fim_prompt(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            file_path=file_path,
            language=language
        )

        completion_provider = self.provider
        try:
            if provider_name or model_name:
                completion_provider = await self._create_provider_instance(
                    provider_name,
                    model_name,
                    tools=[],
                    system_instruction=get_system_instruction("inline"),
                )

            async for chunk in completion_provider.send_message_stream(prompt):
                if cancel_event.is_set():
                    return
                if chunk.content:
                    yield chunk.content

            logger.info("Inline completion finished")

        except Exception as e:
            logger.exception("Error in inline completion")
            raise PoorCLIError(f"Inline completion failed: {e}")
        finally:
            self._clear_cancel_event(request_id)
