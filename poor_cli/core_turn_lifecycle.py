"""
PoorCLI Core Engine - Headless AI coding assistant

This module provides a headless engine used by the PoorCLI terminal client and
the Neovim plugin.
"""

import asyncio
import datetime
import difflib
import hashlib
import json
import subprocess
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .audit_log import AuditEventType, AuditSeverity
from .provider_probe import (
    suggested_privacy_posture,
)
from .provider_catalog import KEYLESS_LOCAL_PROVIDER_NAMES
from .providers.base import FunctionCall
from .providers.capability import ProviderCapability, provider_has_capability
from .providers.provider_factory import ProviderFactory
from .run_history import classify_error
from .core_events import CoreEvent
from .token_counter import get_token_counter
from .context_optimizer import CompactionPolicy
from .policy_hooks import HookExecutionResult
from .economy import (
    classify_prompt_complexity,
    apply_economy_preset,
    resolve_output_verbosity,
    build_savings_summary,
    SavingsHistoryStore,
)
from .vision import detect_image_paths_for_provider, build_multimodal_content_anthropic, build_multimodal_content_openai, build_multimodal_parts_gemini
from .semantic_cache import (
    get_semantic_cache,
)
from .tool_output_filter import merge_filter_stats
from .prompts import (
    build_tool_calling_system_instruction,
    detect_tone_from_user_memories,
)
from .automations import get_workflow_template, list_workflow_templates
from .exceptions import (
    PoorCLIError,
    ConfigurationError,
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





class TurnLifecycle:
    @staticmethod
    def _stringify_tool_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {str(key): value for key, value in arguments.items()}

    @staticmethod
    def _current_git_branch(repo_root: Optional[Path] = None) -> str:
        try:
            output = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str((repo_root or Path.cwd()).resolve()),
                stderr=subprocess.DEVNULL,
                text=True,
            )
            branch = output.strip()
            return branch or "unknown"
        except Exception:
            return "unknown"

    def _log_audit_event(
        self,
        event_type: AuditEventType,
        *,
        operation: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        if not self._audit_logger:
            return
        try:
            self._audit_logger.log_event(
                event_type=event_type,
                operation=operation,
                target=target,
                details=details,
                severity=severity,
                success=success,
                error_message=error_message,
            )
        except Exception as error:
            logger.debug("Audit logging failed: %s", error)

    async def _emit_policy_hooks(
        self,
        event: str,
        payload: Dict[str, Any],
    ) -> List[HookExecutionResult]:
        if not self._hook_manager:
            return []
        results = await self._hook_manager.run(event, payload)
        for result in results:
            self._log_audit_event(
                AuditEventType.HOOK_DENY if result.blocked else AuditEventType.HOOK_ALLOW,
                operation=f"hook:{event}",
                target=result.hook.source_path,
                details=result.to_dict(),
                severity=AuditSeverity.WARNING if result.blocked else AuditSeverity.INFO,
                success=not result.blocked,
                error_message=result.stderr or None,
            )
        return results

    def _should_request_plan_review(self, function_calls: List[FunctionCall]) -> bool:
        if not self.config or not self.config.plan_mode.enabled:
            return False

        high_risk_tools = {"delete_file", "bash", "move_file"}
        if any(call.name in high_risk_tools for call in function_calls):
            return True

        if len(function_calls) >= self.config.plan_mode.auto_plan_threshold:
            return True

        affected_files: set[str] = set()
        for call in function_calls:
            affected_files.update(self._inspect_tool_targets(call.name, call.arguments))
        return len(affected_files) >= self.config.plan_mode.auto_plan_threshold

    def _build_plan_payload(
        self,
        user_request: str,
        function_calls: List[FunctionCall],
    ) -> Dict[str, Any]:
        plan = self._plan_analyzer.create_plan_from_request(user_request)
        for call in function_calls:
            self._plan_analyzer.add_function_call_to_plan(
                plan,
                call.name,
                call.arguments,
            )

        steps = [step.description for step in plan.steps]
        summary = (
            f"{len(plan.steps)} step(s), risk={plan.overall_risk_level.value}, "
            f"files={len(plan.get_affected_files())}"
        )
        return {
            "planId": plan.plan_id,
            "summary": summary,
            "steps": steps,
            "originalRequest": user_request,
            "riskLevel": plan.overall_risk_level.value,
            "affectedFiles": plan.get_affected_files(),
        }

    async def _request_plan_review(
        self,
        user_request: str,
        function_calls: List[FunctionCall],
        request_id: str,
    ) -> bool:
        if not self._plan_callback or not self._should_request_plan_review(function_calls):
            return True

        payload = self._build_plan_payload(user_request, function_calls)
        payload["requestId"] = request_id
        self._pending_events.append(
            CoreEvent.plan_request(
                payload["summary"],
                payload["steps"],
                payload["originalRequest"],
                request_id=request_id,
            )
        )
        decision = await self._plan_callback(payload)
        return bool(decision)

    async def _record_user_prompt_submission(
        self,
        message: str,
        *,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
        request_id: str = "",
    ) -> None:
        payload = {
            "message": message,
            "requestId": request_id,
            "contextFiles": context_files or [],
            "pinnedContextFiles": pinned_context_files or [],
            "contextBudgetTokens": context_budget_tokens,
        }
        await self._emit_policy_hooks("user_prompt_submitted", payload)

    def _record_context_preview(self, preview: Dict[str, Any]) -> None:
        self._last_context_preview = dict(preview or {})

    def _record_mutation_summary(
        self,
        *,
        tool_name: str,
        result: Dict[str, Any],
    ) -> None:
        paths = result.get("paths") or []
        changed = result.get("changed")
        checkpoint_id = result.get("checkpointId")
        if not changed and not checkpoint_id:
            return
        active_provider = self.get_provider_info() if self._initialized else {}
        self._last_mutation_summary = {
            "intent": tool_name,
            "paths": paths,
            "checkpointId": checkpoint_id,
            "rollbackHint": f"/restore {checkpoint_id}" if checkpoint_id else "",
            "provider": {
                "name": active_provider.get("name", ""),
                "model": active_provider.get("model", ""),
                "routingMode": self.get_routing_mode() if self.config else "manual",
            },
            "fallback": dict(self._last_fallback_summary),
            "nextSuggestedAction": "/review" if paths else "/status",
        }

    def _provider_summary(self) -> Dict[str, Any]:
        if not self._initialized:
            return {}
        provider_info = self.get_provider_info()
        return {
            "name": provider_info.get("name", ""),
            "model": provider_info.get("model", ""),
            "routingMode": provider_info.get("routingMode", self.get_routing_mode()),
            "fallback": dict(self._last_fallback_summary),
            "lastError": self._last_provider_error,
        }

    @staticmethod
    def _cost_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "input_tokens": max(0, int(after.get("input_tokens", 0)) - int(before.get("input_tokens", 0))),
            "output_tokens": max(0, int(after.get("output_tokens", 0)) - int(before.get("output_tokens", 0))),
            "total_tokens": max(0, int(after.get("total_tokens", 0)) - int(before.get("total_tokens", 0))),
            "estimated_cost_usd": round(
                max(
                    0.0,
                    float(after.get("estimated_cost_usd", 0.0))
                    - float(before.get("estimated_cost_usd", 0.0)),
                ),
                6,
            ),
        }

    def _new_run_turn_diagnostics(self, *, max_iterations: int) -> Dict[str, Any]:
        return {
            "maxIterations": max(1, int(max_iterations)),
            "turnTransitions": [],
            "turnOrchestration": [],
            "compactionEvents": [],
            "promptLayers": {},
            "perfSpans": self._recent_perf_spans(limit=32, window_seconds=20.0),
        }

    def _record_perf_span(
        self,
        name: str,
        elapsed_ms: float,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "at": time.time(),
            "name": str(name or "").strip() or "unknown",
            "elapsedMs": round(max(0.0, float(elapsed_ms)), 3),
        }
        if details:
            entry["details"] = dict(details)
        history = getattr(self, "_perf_span_history", None)
        if isinstance(history, list):
            history.append(entry)
            if len(history) > 256:
                del history[:-256]
        active = getattr(self, "_active_turn_diagnostics", None)
        if isinstance(active, dict):
            self._append_perf_span(active, entry)

    @staticmethod
    def _append_perf_span(diagnostics: Dict[str, Any], entry: Dict[str, Any]) -> None:
        spans = diagnostics.get("perfSpans")
        if not isinstance(spans, list):
            spans = []
            diagnostics["perfSpans"] = spans
        spans.append(dict(entry))
        if len(spans) > 128:
            del spans[:-128]

    def _recent_perf_spans(
        self,
        *,
        limit: int = 32,
        window_seconds: float = 20.0,
    ) -> List[Dict[str, Any]]:
        history = getattr(self, "_perf_span_history", None)
        if not isinstance(history, list) or not history:
            return []
        cutoff = time.time() - max(0.0, float(window_seconds))
        recent = [entry for entry in history if float(entry.get("at", 0.0)) >= cutoff]
        if not recent:
            return []
        return [dict(entry) for entry in recent[-max(1, int(limit)):]]

    def _append_turn_transition(
        self,
        diagnostics: Optional[Dict[str, Any]],
        *,
        reason_code: str,
        iteration: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not diagnostics:
            return
        transitions = diagnostics.get("turnTransitions")
        if not isinstance(transitions, list):
            return
        payload: Dict[str, Any] = {
            "at": time.time(),
            "reasonCode": str(reason_code or "").strip() or "unspecified",
        }
        if iteration is not None:
            try:
                payload["iterationIndex"] = int(iteration)
            except (TypeError, ValueError):
                pass
        if details:
            payload["details"] = dict(details)
        transitions.append(payload)
        if len(transitions) > _MAX_RUN_TRANSITIONS:
            del transitions[:-_MAX_RUN_TRANSITIONS]

    def _append_turn_orchestration(
        self,
        diagnostics: Optional[Dict[str, Any]],
        *,
        iteration: int,
        call_count: int,
        concurrency_safe_count: int,
        sequential_count: int,
        max_parallel: int,
        plan_review: str,
        had_mutations: bool,
        auto_feedback_injected: bool,
        tool_names: List[str],
        tool_result_chars: int = 0,
        tool_result_chars_after_budget: int = 0,
        tool_result_budget_applied: bool = False,
        truncated_results: int = 0,
    ) -> None:
        if not diagnostics:
            return
        summaries = diagnostics.get("turnOrchestration")
        if not isinstance(summaries, list):
            return
        summaries.append(
            {
                "iterationIndex": max(0, int(iteration)),
                "callCount": max(0, int(call_count)),
                "concurrencySafeCount": max(0, int(concurrency_safe_count)),
                "sequentialCount": max(0, int(sequential_count)),
                "maxParallel": max(1, int(max_parallel)),
                "planReview": str(plan_review or "approved"),
                "hadMutations": bool(had_mutations),
                "autoFeedbackInjected": bool(auto_feedback_injected),
                "toolNames": [str(name) for name in tool_names if str(name).strip()],
                "toolResultChars": max(0, int(tool_result_chars)),
                "toolResultCharsAfterBudget": max(0, int(tool_result_chars_after_budget)),
                "toolResultBudgetApplied": bool(tool_result_budget_applied),
                "truncatedResultCount": max(0, int(truncated_results)),
            }
        )
        if len(summaries) > _MAX_RUN_TURN_SUMMARIES:
            del summaries[:-_MAX_RUN_TURN_SUMMARIES]

    @staticmethod
    def _extract_run_diagnostics(metadata: Any) -> Dict[str, Any]:
        payload = metadata if isinstance(metadata, dict) else {}
        transitions = payload.get("turnTransitions")
        if not isinstance(transitions, list):
            transitions = []
        orchestration = payload.get("turnOrchestration")
        if not isinstance(orchestration, list):
            orchestration = []
        compaction_events = payload.get("compactionEvents")
        if not isinstance(compaction_events, list):
            compaction_events = []
        prompt_layers = payload.get("promptLayers")
        if not isinstance(prompt_layers, dict):
            prompt_layers = {}
        perf_spans = payload.get("perfSpans")
        if not isinstance(perf_spans, list):
            perf_spans = []
        return {
            "completionReasonCode": str(payload.get("completionReasonCode", "") or "").strip(),
            "turnTransitions": transitions,
            "turnOrchestration": orchestration,
            "compactionEvents": compaction_events,
            "promptLayers": prompt_layers,
            "perfSpans": perf_spans,
            "maxIterations": int(payload.get("maxIterations", 0) or 0),
        }

    def _build_run_metadata_updates(
        self,
        *,
        request_id: str = "",
        diagnostics: Optional[Dict[str, Any]] = None,
        completion_reason_code: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        updates: Dict[str, Any] = {}
        if request_id:
            updates["requestId"] = request_id
        if diagnostics:
            transitions = diagnostics.get("turnTransitions")
            if isinstance(transitions, list):
                updates["turnTransitions"] = list(transitions)
            orchestration = diagnostics.get("turnOrchestration")
            if isinstance(orchestration, list):
                updates["turnOrchestration"] = list(orchestration)
            max_iterations = diagnostics.get("maxIterations")
            try:
                max_iterations_int = int(max_iterations)
            except (TypeError, ValueError):
                max_iterations_int = 0
            if max_iterations_int > 0:
                updates["maxIterations"] = max_iterations_int
            compaction_events = diagnostics.get("compactionEvents")
            if isinstance(compaction_events, list):
                updates["compactionEvents"] = list(compaction_events)
            prompt_layers = diagnostics.get("promptLayers")
            if isinstance(prompt_layers, dict):
                updates["promptLayers"] = dict(prompt_layers)
            perf_spans = diagnostics.get("perfSpans")
            if isinstance(perf_spans, list):
                updates["perfSpans"] = [dict(entry) for entry in perf_spans]
        if completion_reason_code:
            updates["completionReasonCode"] = str(completion_reason_code)
        if extra:
            updates.update(extra)
        return updates

    def _start_run_record(
        self,
        *,
        source_kind: str,
        source_id: str,
        artifact_dir: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self._run_history:
            return None
        metadata = dict(metadata or {})
        retry_of_run_id = str(metadata.get("retryOfRunId", "")).strip() or None
        replay_of_run_id = str(metadata.get("replayOfRunId", "")).strip() or None
        record = self._run_history.start_run(
            source_kind=source_kind,
            source_id=source_id,
            artifact_dir=artifact_dir,
            metadata=metadata,
            retry_of_run_id=retry_of_run_id,
            replay_of_run_id=replay_of_run_id,
        )
        self._last_run_id = record.run_id
        return {"record": record, "cost_before": self.get_session_cost_summary()}

    def _finish_run_record(
        self,
        run_state: Optional[Dict[str, Any]],
        *,
        status: str,
        summary: str = "",
        error_message: str = "",
        checkpoint_id: Optional[str] = None,
        artifact_dir: str = "",
        metadata_updates: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not run_state or not self._run_history:
            return
        record = run_state["record"]
        cost_before = run_state["cost_before"]
        cost_after = self.get_session_cost_summary()
        self._run_history.finish_run(
            record.run_id,
            status=status,
            error_class=classify_error(error_message),
            artifact_dir=artifact_dir or record.artifact_dir,
            checkpoint_id=checkpoint_id,
            provider_summary=self._provider_summary(),
            cost_summary=self._cost_delta(cost_before, cost_after),
            summary=summary,
            metadata_updates=metadata_updates,
        )

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Rough cost estimation based on provider/model."""
        cost_per_1k_input = 0.0005  # conservative default
        cost_per_1k_output = 0.0015
        if self.config:
            provider = self.config.model.provider
            model = self.config.model.model_name
            from poor_cli.provider_catalog import get_model_tier
            tier = get_model_tier(provider, model)
            if tier:
                cost_per_1k_input = tier.cost_1k_in
                cost_per_1k_output = tier.cost_1k_out
            elif provider in KEYLESS_LOCAL_PROVIDER_NAMES:
                return 0.0
        return (input_tokens / 1000) * cost_per_1k_input + (output_tokens / 1000) * cost_per_1k_output

    def _track_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        provider: Optional[str] = None,
    ) -> float:
        """Accumulate session and per-task cost tracking.

        ``provider``: optional provider name for SBP1 per-provider cache
        telemetry. Defaults to the current active provider, or the string
        ``"unknown"`` if nothing can be inferred.
        """
        est = self._estimate_cost(input_tokens, output_tokens)
        self._session_total_input_tokens += input_tokens
        self._session_total_output_tokens += output_tokens
        self._session_total_cost_usd += est
        self._session_cache_creation_input_tokens += cache_creation_input_tokens
        self._session_cache_read_input_tokens += cache_read_input_tokens
        is_hit = cache_read_input_tokens > 0
        is_call = input_tokens > 0 or cache_creation_input_tokens > 0
        if is_hit:
            self._session_provider_cache_hits += 1
        elif is_call:
            self._session_provider_cache_misses += 1
        savings = self._estimate_cost(cache_read_input_tokens, 0) if is_hit else 0.0
        if is_hit:
            self._session_estimated_cache_savings_usd += savings
        # SBP1 per-provider aggregation
        provider_name = provider or self._resolve_current_provider_name() or "unknown"
        per = self._session_provider_cache_stats.setdefault(provider_name, {
            "hits": 0, "misses": 0, "read_tokens": 0, "write_tokens": 0, "savings_usd": 0.0,
            "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
        })
        per["hits"] += 1 if is_hit else 0
        per["misses"] += 1 if (not is_hit and is_call) else 0
        per["read_tokens"] += cache_read_input_tokens
        per["write_tokens"] += cache_creation_input_tokens
        per["savings_usd"] = round(per["savings_usd"] + savings, 6)
        per["cost_usd"] = round(per["cost_usd"] + est, 6)
        per["input_tokens"] += input_tokens
        per["output_tokens"] += output_tokens
        self._task_input_tokens += input_tokens
        self._task_output_tokens += output_tokens
        self._task_cost_usd += est
        self._task_cache_creation_input_tokens = getattr(self, "_task_cache_creation_input_tokens", 0) + cache_creation_input_tokens
        self._task_cache_read_input_tokens = getattr(self, "_task_cache_read_input_tokens", 0) + cache_read_input_tokens
        return est

    def _resolve_current_provider_name(self) -> Optional[str]:
        provider = getattr(self, "provider", None)
        if provider is None:
            return None
        # prefer canonical short name
        name = getattr(provider, "name", None)
        if isinstance(name, str) and name:
            return name.lower()
        klass = provider.__class__.__name__
        if klass.endswith("Provider"):
            klass = klass[:-len("Provider")]
        return klass.lower() or None

    def _record_tool_cost_surface(self, tool_name: str, result_text: str) -> None:
        """Track tool-result token surface cost for dashboards only."""
        tool_name = str(tool_name or "tool")
        try:
            tokens = get_token_counter().count(str(result_text or "")).count
        except Exception:
            tokens = max(0, len(str(result_text or "")) // 4)
        usd = self._estimate_cost(tokens, 0)
        totals = getattr(self, "_cost_tool_totals", None)
        if totals is None:
            totals = {}
            self._cost_tool_totals = totals
        item = totals.setdefault(tool_name, {"tool": tool_name, "tokens": 0, "cost_usd": 0.0, "calls": 0})
        item["tokens"] = int(item.get("tokens", 0) or 0) + tokens
        item["cost_usd"] = round(float(item.get("cost_usd", 0.0) or 0.0) + usd, 6)
        item["calls"] = int(item.get("calls", 0) or 0) + 1

    def _record_cost_turn(self, request_id: str = "", reason: str = "complete") -> None:
        if getattr(self, "_turn_cost_recorded", False):
            return
        self._turn_cost_recorded = True
        turns = getattr(self, "_cost_turn_history", None)
        if turns is None:
            turns = []
            self._cost_turn_history = turns
        duration_ms = 0
        start = getattr(self, "_turn_start_mono", 0.0) or 0.0
        if start > 0:
            duration_ms = int(max(0.0, time.monotonic() - start) * 1000)
        cache_read = getattr(self, "_task_cache_read_input_tokens", 0)
        cache_create = getattr(self, "_task_cache_creation_input_tokens", 0)
        entry = {
            "turn_id": str(request_id or f"turn-{len(turns) + 1}"),
            "request_id": str(request_id or ""),
            "cost_usd": round(float(getattr(self, "_task_cost_usd", 0.0) or 0.0), 6),
            "input_tokens": int(getattr(self, "_task_input_tokens", 0) or 0),
            "output_tokens": int(getattr(self, "_task_output_tokens", 0) or 0),
            "cache_read_input_tokens": int(cache_read or 0),
            "cache_creation_input_tokens": int(cache_create or 0),
            "cache_hit": bool(cache_read and cache_read > 0) or bool(getattr(self, "_turn_economy", None) and self._turn_economy.cache_hit),
            "duration_ms": duration_ms,
            "tool_calls": int(getattr(self, "_turn_tool_call_count", 0) or 0),
            "reason": str(reason or "complete"),
        }
        entry["total_tokens"] = entry["input_tokens"] + entry["output_tokens"]
        turns.append(entry)
        if len(turns) > 500:
            del turns[:-500]

    def _check_cost_guardrails(self) -> Optional[str]:
        """Check if session or task cost/token limits are exceeded. Returns reason or None."""
        if not self.config:
            return None
        try:
            cg = self.config.cost_guardrails
            total_tokens = self._session_total_input_tokens + self._session_total_output_tokens
            max_tokens = getattr(cg, "session_max_tokens", 0) or 0
            max_cost = getattr(cg, "session_max_cost_usd", 0.0) or 0.0
            if max_tokens > 0 and total_tokens >= max_tokens:
                return f"Session token limit reached ({total_tokens}/{max_tokens})"
            if max_cost > 0 and self._session_total_cost_usd >= max_cost:
                return f"Session cost limit reached (${self._session_total_cost_usd:.4f}/${max_cost})"
            # per-task limits
            task_max = getattr(cg, "task_max_tokens", 0) or 0
            task_max_cost = getattr(cg, "task_max_cost_usd", 0.0) or 0.0
            task_tokens = self._task_input_tokens + self._task_output_tokens
            if task_max > 0 and task_tokens >= task_max:
                return f"Task token limit reached ({task_tokens}/{task_max})"
            if task_max_cost > 0 and self._task_cost_usd >= task_max_cost:
                return f"Task cost limit reached (${self._task_cost_usd:.4f}/${task_max_cost})"
        except (AttributeError, TypeError):
            pass
        return None

    def _check_cost_warning(self) -> Optional[str]:
        """Return warning message if approaching 80% of session limits, else None."""
        if not self.config or self._cost_warning_emitted:
            return None
        try:
            cg = self.config.cost_guardrails
            total_tokens = self._session_total_input_tokens + self._session_total_output_tokens
            max_tokens = getattr(cg, "session_max_tokens", 0) or 0
            max_cost = getattr(cg, "session_max_cost_usd", 0.0) or 0.0
            if max_tokens > 0 and total_tokens >= max_tokens * 0.8:
                self._cost_warning_emitted = True
                return f"Approaching session token limit ({total_tokens}/{max_tokens}, 80%)"
            if max_cost > 0 and self._session_total_cost_usd >= max_cost * 0.8:
                self._cost_warning_emitted = True
                return f"Approaching session cost limit (${self._session_total_cost_usd:.4f}/${max_cost}, 80%)"
        except (AttributeError, TypeError):
            pass
        return None

    def get_session_summary(self) -> Dict[str, Any]:
        summary = self.get_session_cost_summary()
        per_turn = list(getattr(self, "_cost_turn_history", []) or [])
        top_tools = sorted(
            (dict(v) for v in (getattr(self, "_cost_tool_totals", {}) or {}).values()),
            key=lambda item: float(item.get("cost_usd", 0.0) or 0.0),
            reverse=True,
        )[:10]
        daily = {}
        for entry in self.get_cost_history(500):
            day = str(entry.get("timestamp", ""))[:10]
            if len(day) == 10:
                daily[day] = round(float(daily.get(day, 0.0) or 0.0) + float(entry.get("cost_usd", 0.0) or 0.0), 6)
        import datetime
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        daily[today] = round(float(daily.get(today, 0.0) or 0.0) + float(summary.get("estimated_cost_usd", 0.0) or 0.0), 6)
        recent_days = sorted(daily.keys())[-30:]
        daily_30 = {day: daily[day] for day in recent_days}
        last_week = [daily[day] for day in sorted(daily.keys())[-7:]]
        last_week_avg = (sum(last_week) / len(last_week)) if last_week else 0.0
        projected_monthly = round(float(daily.get(today, 0.0) or 0.0) * 30, 6)
        projected_last_week = round(last_week_avg * 30, 6)
        session = {
            "total_usd": summary.get("estimated_cost_usd", 0.0),
            "total_tokens": {
                "in": summary.get("input_tokens", 0),
                "out": summary.get("output_tokens", 0),
                "thinking": 0,
                "cached_read": summary.get("cache_read_input_tokens", 0),
                "cached_write": summary.get("cache_creation_input_tokens", 0),
            },
            "turns": len(per_turn),
            "cache_hit_rate": summary.get("cache_hit_rate_pct", 0.0),
        }
        return {
            "session": session,
            "summary": summary,
            "per_turn": per_turn,
            "perTurn": per_turn,
            "last_turn": per_turn[-1] if per_turn else {},
            "lastTurn": per_turn[-1] if per_turn else {},
            "top_tools": top_tools,
            "topTools": top_tools,
            "projected_monthly_usd": projected_monthly,
            "projectedMonthlyUSD": projected_monthly,
            "projected_monthly_last_week_usd": projected_last_week,
            "projectedMonthlyLastWeekUSD": projected_last_week,
            "daily": daily_30,
            "cache": {
                "hit_rate_pct": summary.get("cache_hit_rate_pct", 0.0),
                "hits": summary.get("cache_hit_count", 0),
                "misses": summary.get("cache_miss_count", 0),
                "read_tokens": summary.get("cache_read_input_tokens", 0),
                "write_tokens": summary.get("cache_creation_input_tokens", 0),
                # SBP1: per-provider breakdown
                "by_provider": self._build_provider_cache_breakdown(),
            },
        }

    def _build_provider_cache_breakdown(self) -> Dict[str, Any]:
        """SBP1: return {provider_name: {hits, misses, hit_rate_pct, ...}}."""
        per = dict(getattr(self, "_session_provider_cache_stats", {}) or {})
        out: Dict[str, Any] = {}
        for name, stats in per.items():
            hits = int(stats.get("hits", 0) or 0)
            misses = int(stats.get("misses", 0) or 0)
            total = hits + misses
            hit_rate = round(hits / total * 100, 1) if total > 0 else 0.0
            out[name] = {
                "hits": hits,
                "misses": misses,
                "hit_rate_pct": hit_rate,
                "read_tokens": int(stats.get("read_tokens", 0) or 0),
                "write_tokens": int(stats.get("write_tokens", 0) or 0),
                "savings_usd": round(float(stats.get("savings_usd", 0.0) or 0.0), 6),
                "cost_usd": round(float(stats.get("cost_usd", 0.0) or 0.0), 6),
                "input_tokens": int(stats.get("input_tokens", 0) or 0),
                "output_tokens": int(stats.get("output_tokens", 0) or 0),
            }
        return out

    def get_session_cost_summary(self) -> Dict[str, Any]:
        """Return current session cost/token totals."""
        input_tokens = getattr(self, "_session_total_input_tokens", 0)
        output_tokens = getattr(self, "_session_total_output_tokens", 0)
        cost_usd = getattr(self, "_session_total_cost_usd", 0.0)
        cache_create = getattr(self, "_session_cache_creation_input_tokens", 0)
        cache_read = getattr(self, "_session_cache_read_input_tokens", 0)
        cache_hits = getattr(self, "_session_provider_cache_hits", 0)
        cache_misses = getattr(self, "_session_provider_cache_misses", 0)
        cache_savings = getattr(self, "_session_estimated_cache_savings_usd", 0.0)
        total_requests = cache_hits + cache_misses
        hit_rate = round(cache_hits / total_requests * 100, 1) if total_requests else 0.0
        filter_stats = self.get_tool_filter_stats()
        economy_summary = (
            self._economy_tracker.get_summary()
            if getattr(self, "_economy_tracker", None) is not None
            else {}
        )
        pretok = {
            "tokens_saved": int(economy_summary.get("tokens_saved_by_safe_pretokenization", 0) or 0),
            "files": int(economy_summary.get("safe_pretokenization_files", 0) or 0),
            "original_tokens": int(economy_summary.get("safe_pretokenization_original_tokens", 0) or 0),
            "compressed_tokens": int(economy_summary.get("safe_pretokenization_compressed_tokens", 0) or 0),
            "by_file": economy_summary.get("safe_pretokenization_by_file", {}) or {},
        }
        block_cache_stats = (
            self._block_cache.get_stats()
            if getattr(self, "_block_cache", None) is not None
            else {"blocks": 0, "hits": 0, "misses": 0, "hit_rate_pct": 0.0, "rolling_hit_rate_pct": 0.0}
        )
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated_cost_usd": round(cost_usd, 6),
            "tool_filtering": filter_stats,
            "tool_filtering_tokens_saved": filter_stats.get("tokens_saved", 0),
            "safe_pretokenization": pretok,
            "safe_pretokenization_tokens_saved": pretok["tokens_saved"],
            "block_cache": block_cache_stats,
            "cache_creation_input_tokens": cache_create,
            "cache_read_input_tokens": cache_read,
            "cache_hit_count": cache_hits,
            "cache_miss_count": cache_misses,
            "cache_hit_rate_pct": hit_rate,
            "estimated_cache_savings_usd": round(cache_savings, 6),
            "request_count": total_requests,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
            "estimatedCost": round(cost_usd, 6),
            "toolFiltering": filter_stats,
            "toolFilteringTokensSaved": filter_stats.get("tokens_saved", 0),
            "safePretokenization": pretok,
            "safePretokenizationTokensSaved": pretok["tokens_saved"],
            "blockCache": block_cache_stats,
            "cacheCreationInputTokens": cache_create,
            "cacheReadInputTokens": cache_read,
            "cacheHitCount": cache_hits,
            "cacheMissCount": cache_misses,
            "cacheHitRatePct": hit_rate,
            "estimatedCacheSavingsUSD": round(cache_savings, 6),
            "requestCount": total_requests,
        }

    def get_economy_savings(self) -> Dict[str, Any]:
        """Return accumulated economy savings summary."""
        tracker = getattr(self, "_economy_tracker", None)
        summary = tracker.get_summary() if tracker else {}
        if tracker:
            sources = {
                "distillation": int(summary.get("tokens_saved_by_distillation", 0) or 0),
                "model_downshift": int(summary.get("tokens_saved_by_downshift", 0) or 0),
                "context_dedup": int(summary.get("tokens_saved_by_dedup", 0) or 0),
                "terse_prompt": int(summary.get("tokens_saved_by_terse", 0) or 0),
                "truncation": int(summary.get("tokens_saved_by_truncation", 0) or 0),
                "failure_amnesia": int(summary.get("tokens_saved_by_failure_amnesia", 0) or 0),
                "safe_pretokenization": int(summary.get("tokens_saved_by_safe_pretokenization", 0) or 0),
                "shell_filter": int(summary.get("tokens_saved_by_shell_filter", 0) or 0),
            }
            by_source = [
                {
                    "source": source,
                    "tokens_saved": tokens,
                    "usd_saved": round((tokens / 1000) * 0.001, 6),
                }
                for source, tokens in sources.items()
                if tokens > 0
            ]
            total_saved = sum(sources.values())
            summary["tokensSaved"] = total_saved
            summary["costSaved"] = round(tracker.get_money_saved(), 6)
            summary["cacheHits"] = int(summary.get("cache_hits", 0) or 0)
            summary["by_source"] = by_source
            summary["session_delta"] = {"tokens_saved": total_saved, "usd_saved": summary["costSaved"]}
        sc = getattr(self, "_semantic_cache", None)
        if sc:
            summary["semantic_cache"] = sc.get_stats()
        if getattr(self, "_block_cache", None) is not None:
            summary["block_cache"] = self._block_cache.get_stats()
        return summary

    def _savings_history(self) -> SavingsHistoryStore:
        store = getattr(self, "_savings_history_store", None)
        if store is None:
            store = SavingsHistoryStore()
            self._savings_history_store = store
        return store

    def get_savings_summary(self, days: int = 30, *, include_history: bool = True) -> Dict[str, Any]:
        """Return estimated savings dashboard data."""
        tracker = getattr(self, "_economy_tracker", None)
        economy_summary = tracker.get_summary() if tracker else {}
        session_summary = self.get_session_cost_summary()
        semantic_stats = self._semantic_cache.get_stats() if getattr(self, "_semantic_cache", None) else {}
        block_stats = self._block_cache.get_stats() if getattr(self, "_block_cache", None) is not None else {}
        summary = build_savings_summary(
            economy_summary,
            session_summary,
            semantic_cache_stats=semantic_stats,
            block_cache_stats=block_stats,
            token_usd_estimator=lambda tokens: self._estimate_cost(tokens, 0),
        )
        if include_history:
            history = self.get_savings_history(days)
            today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            current_usd = float(summary.get("usd_saved", 0.0) or 0.0)
            if current_usd > 0:
                daily = dict(history.get("daily", {}) or {})
                daily[today] = round(float(daily.get(today, 0.0) or 0.0) + current_usd, 6)
                history["daily"] = {day: daily[day] for day in sorted(daily.keys())[-max(1, int(days or 30)):]}
                week = datetime.date.fromisoformat(today).isocalendar()
                week_key = f"{week.year}-W{week.week:02d}"
                weekly = list(history.get("top_contributors_by_week", []) or [])
                current = {str(item.get("source") or ""): float(item.get("usd_saved", 0.0) or 0.0) for item in summary.get("all_sources", [])}
                found = False
                for item in weekly:
                    if item.get("week") == week_key:
                        totals = {str(row.get("source") or ""): float(row.get("usd_saved", 0.0) or 0.0) for row in item.get("top", [])}
                        for source, usd in current.items():
                            totals[source] = round(totals.get(source, 0.0) + usd, 6)
                        item["top"] = [
                            {"source": source, "usd_saved": usd}
                            for source, usd in sorted(totals.items(), key=lambda row: row[1], reverse=True)[:3]
                            if usd > 0
                        ]
                        found = True
                        break
                if not found:
                    weekly.append({
                        "week": week_key,
                        "top": [
                            {"source": source, "usd_saved": usd}
                            for source, usd in sorted(current.items(), key=lambda row: row[1], reverse=True)[:3]
                            if usd > 0
                        ],
                    })
                history["top_contributors_by_week"] = weekly[-6:]
            summary["history"] = history
            summary["top_contributors_by_week"] = history.get("top_contributors_by_week", [])
        return summary

    def get_savings_history(self, days: int = 30) -> Dict[str, Any]:
        """Return persisted savings history."""
        try:
            return self._savings_history().history(days=days)
        except Exception as e:
            logger.debug("Failed to load savings history: %s", e)
            return {"daily": {}, "by_day_source": {}, "top_contributors_by_week": []}

    def get_budget_controller_stats(self) -> Dict[str, Any]:
        """Return token budget controller analytics."""
        stats = self._budget_controller.get_stats()
        stats["log_summary"] = self._budget_logger.summary()
        return stats

    def clear_semantic_cache(self) -> Dict[str, Any]:
        """Clear the semantic response cache."""
        if getattr(self, "_semantic_cache", None):
            removed = self._semantic_cache.invalidate_all()
            return {"cleared": removed}
        return {"cleared": 0, "note": "semantic cache not initialized"}

    def get_routing_stats(self) -> Dict[str, Any]:
        """Return model routing analytics."""
        if getattr(self, "_model_router", None):
            return self._model_router.get_routing_stats()
        return {"total_decisions": 0}

    def export_cost_report(self) -> Dict[str, Any]:
        """Export full session cost report for accounting."""
        return {
            "session": self.get_session_cost_summary(),
            "economy_savings": self._economy_tracker.get_summary() if getattr(self, "_economy_tracker", None) else {},
            "routing": self.get_routing_stats(),
            "tool_filtering": self.get_tool_filter_stats(),
            "context_breakdown": self.get_context_breakdown() if self.provider else {},
            "context_pressure": self.get_context_pressure() if self.provider else {},
            "cache_stats": self.get_cache_stats(),
            "model": {
                "provider": self.config.model.provider if self.config else "",
                "model_name": self.config.model.model_name if self.config else "",
                "economy_preset": self.config.economy.preset if self.config else "",
            },
        }

    def apply_budget_template(self, template_name: str) -> Dict[str, Any]:
        """Apply a named budget template to cost guardrails."""
        from .config import BUDGET_TEMPLATES
        values = BUDGET_TEMPLATES.get(template_name)
        if not values:
            return {"error": f"Unknown template. Available: {', '.join(BUDGET_TEMPLATES.keys())}"}
        if not self.config:
            return {"error": "not initialized"}
        for k, v in values.items():
            if hasattr(self.config.cost_guardrails, k):
                setattr(self.config.cost_guardrails, k, v)
        self._cost_warning_emitted = False # reset warning for new budget
        from dataclasses import asdict as _asdict
        return {"template": template_name, "guardrails": _asdict(self.config.cost_guardrails)}

    @staticmethod
    def list_budget_templates() -> Dict[str, Dict[str, Any]]:
        """Return all available budget templates."""
        from .config import BUDGET_TEMPLATES
        return dict(BUDGET_TEMPLATES)

    def _persist_cost_history(self) -> None:
        """Append session cost summary to persistent cost history."""
        total = self._session_total_input_tokens + self._session_total_output_tokens
        if total == 0:
            return
        import datetime
        savings_snapshot = self.get_savings_summary(include_history=False)
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "provider": self.config.model.provider if self.config else "",
            "model": self.config.model.model_name if self.config else "",
            "input_tokens": self._session_total_input_tokens,
            "output_tokens": self._session_total_output_tokens,
            "cost_usd": round(self._session_total_cost_usd, 6),
            "cache_creation_input_tokens": self._session_cache_creation_input_tokens,
            "cache_read_input_tokens": self._session_cache_read_input_tokens,
            "cache_hit_count": self._session_provider_cache_hits,
            "cache_miss_count": self._session_provider_cache_misses,
            "estimated_cache_savings_usd": round(self._session_estimated_cache_savings_usd, 6),
            "economy_preset": self.config.economy.preset if self.config else "",
            "savings_usd": round(float(savings_snapshot.get("usd_saved", 0.0) or 0.0), 6),
            "savings_tokens": int(savings_snapshot.get("tokens_saved", 0) or 0),
            "savings_by_source": savings_snapshot.get("all_sources", []),
        }
        try:
            self._COST_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            history: List[Dict[str, Any]] = []
            if self._COST_HISTORY_FILE.exists():
                history = json.loads(self._COST_HISTORY_FILE.read_text(encoding="utf-8"))
            history.append(entry)
            # keep last 500 entries
            if len(history) > 500:
                history = history[-500:]
            self._COST_HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
            self._savings_history().record_snapshot(
                savings_snapshot,
                timestamp=entry["timestamp"],
            )
        except Exception as e:
            logger.debug("Failed to persist cost history: %s", e)

    @staticmethod
    def get_cost_history(limit: int = 50) -> List[Dict[str, Any]]:
        """Load recent cost history entries."""
        path = Path.home() / ".poor-cli" / "cost_history.json"
        if not path.exists():
            return []
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            return history[-limit:]
        except Exception:
            return []

    def get_tokens_visualization(self, width: int = 50) -> Dict[str, Any]:
        """Return text-based context window bar chart."""
        bd = self.get_context_breakdown()
        total = bd.get("total_tokens", 0)
        max_ctx = bd.get("max_context_tokens", 1)
        free = max(0, max_ctx - total)
        def _bar(label: str, tokens: int) -> str:
            pct = tokens / max(max_ctx, 1)
            filled = max(1, int(pct * width)) if tokens > 0 else 0
            return f"[{label}: {'█' * filled}{' ' * (width - filled)}] {tokens:>7} tok ({pct*100:.1f}%)"
        bars = [
            _bar("sys ", bd.get("system_tokens", 0)),
            _bar("hist", bd.get("history_tokens", 0)),
            _bar("tool", bd.get("tool_result_tokens", 0)),
            _bar("free", free),
        ]
        return {"visualization": "\n".join(bars), "breakdown": bd}

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return tool cache + response cache + semantic cache stats."""
        tool_stats = self.tool_registry.get_tool_cache_stats() if self.tool_registry else {}
        provider_hits = getattr(self, "_session_provider_cache_hits", 0)
        provider_misses = getattr(self, "_session_provider_cache_misses", 0)
        provider_requests = provider_hits + provider_misses
        provider_hit_rate = round(provider_hits / provider_requests * 100, 1) if provider_requests else 0.0
        semantic_stats = self._semantic_cache.get_stats() if getattr(self, "_semantic_cache", None) else {}
        block_cache_stats = (
            self._block_cache.get_stats()
            if getattr(self, "_block_cache", None) is not None
            else {"blocks": 0, "hits": 0, "misses": 0, "hit_rate_pct": 0.0, "rolling_hit_rate_pct": 0.0}
        )
        return {
            **tool_stats,
            "response_cache_entries": len(getattr(self, "_response_cache", {})),
            "response_cache_enabled": bool(self.config and self.config.economy.response_cache),
            "provider_cache_hits": provider_hits,
            "provider_cache_misses": provider_misses,
            "provider_cache_hit_rate_pct": provider_hit_rate,
            "provider_cache_creation_input_tokens": getattr(self, "_session_cache_creation_input_tokens", 0),
            "provider_cache_read_input_tokens": getattr(self, "_session_cache_read_input_tokens", 0),
            "provider_estimated_cache_savings_usd": round(
                getattr(self, "_session_estimated_cache_savings_usd", 0.0), 6
            ),
            "block_cache": block_cache_stats,
            "semantic_cache": semantic_stats,
            "file_cache": getattr(self, "_context_manager", None) and hasattr(self._context_manager, "_file_cache") and self._context_manager._file_cache.get_cache_info() or {},
        }

    def get_tool_filter_stats(self) -> Dict[str, int]:
        registry_stats = {}
        if self.tool_registry and hasattr(self.tool_registry, "get_output_filter_stats"):
            registry_stats = self.tool_registry.get_output_filter_stats()
        mcp_stats = {}
        mcp_manager = getattr(self, "_mcp_manager", None)
        if mcp_manager and hasattr(mcp_manager, "get_output_filter_stats"):
            mcp_stats = mcp_manager.get_output_filter_stats()
        return merge_filter_stats(registry_stats, mcp_stats)

    def get_context_pressure(self) -> Dict[str, Any]:
        """Return context window utilization metrics."""
        if not self.provider:
            return {"used_tokens": 0, "max_tokens": 0, "pressure_pct": 0, "strategy_hint": "ok"}
        provider, model = self._token_provider_model()
        counter = get_token_counter()
        caps = self.provider.get_capabilities()
        max_ctx = caps.max_context_tokens
        try:
            history = self.provider.get_history()
            used = sum(counter.count(str(m.get("content", "")), provider=provider, model=model).count for m in history)
        except Exception:
            used = 0
        sys_tokens = self._static_prefix_tokens()
        total = used + sys_tokens
        pct = round(total / max(max_ctx, 1) * 100, 1)
        hint = "compress" if pct > 70 else ("warn" if pct > 50 else "ok")
        return {"used_tokens": total, "max_tokens": max_ctx, "pressure_pct": pct, "strategy_hint": hint}

    def get_context_breakdown(self) -> Dict[str, Any]:
        """Return token breakdown by category: system, history, tool results."""
        provider, model = self._token_provider_model()
        counter = get_token_counter()
        sys_tokens = self._static_prefix_tokens()
        if not self.provider:
            return {"system_tokens": sys_tokens, "history_tokens": 0, "tool_result_tokens": 0,
                    "total_tokens": sys_tokens, "max_context_tokens": 0, "pressure_pct": 0, "turn_count": 0}
        try:
            history = self.provider.get_history()
        except Exception:
            history = []
        hist_tokens = 0
        tool_tokens = 0
        user_turns = 0
        for m in history:
            toks = counter.count(str(m.get("content", "")), provider=provider, model=model).count
            if m.get("role") in ("tool", "function"):
                tool_tokens += toks
            else:
                hist_tokens += toks
            if m.get("role") == "user":
                user_turns += 1
        caps = self.provider.get_capabilities()
        max_ctx = caps.max_context_tokens
        total = sys_tokens + hist_tokens + tool_tokens
        return {"system_tokens": sys_tokens, "history_tokens": hist_tokens,
                "tool_result_tokens": tool_tokens, "total_tokens": total,
                "max_context_tokens": max_ctx,
                "pressure_pct": round(total / max(max_ctx, 1) * 100, 1) if max_ctx else 0,
                "turn_count": user_turns}

    def get_compaction_status(self) -> Dict[str, Any]:
        payload = dict(getattr(self, "_last_compaction_status", {}) or {})
        if not payload:
            payload = {"state": "idle"}
        task = getattr(self, "_auto_history_compact_task", None)
        payload["backgroundActive"] = bool(task and not task.done())
        return payload

    def estimate_cost(self, message: str) -> Dict[str, Any]:
        """Estimate token cost of a message before sending (no API call)."""
        provider, model = self._token_provider_model()
        counter = get_token_counter()
        sys_tokens = self._static_prefix_tokens()
        if self.provider:
            try:
                history = self.provider.get_history()
                hist_tokens = sum(counter.count(str(m.get("content", "")), provider=provider, model=model).count for m in history)
            except Exception:
                hist_tokens = 0
        else:
            hist_tokens = 0
        prompt_tokens = counter.count(message, provider=provider, model=model).count
        total_input = sys_tokens + hist_tokens + prompt_tokens
        est_output = min(total_input, 4000)
        cost = self._estimate_cost(total_input, est_output)
        caps = self.provider.get_capabilities() if self.provider else None
        max_ctx = caps.max_context_tokens if caps else 0
        return {"estimated_input_tokens": total_input, "estimated_output_tokens": est_output,
                "estimated_cost_usd": round(cost, 6),
                "context_pressure_after_pct": round(total_input / max(max_ctx, 1) * 100, 1) if max_ctx else 0,
                "breakdown": {"system": sys_tokens, "history": hist_tokens, "prompt": prompt_tokens}}

    def compare_model_cost(self, target_provider: str, target_model: str) -> Dict[str, Any]:
        """Compare cost between current model and a target model."""
        if not self.config:
            return {"error": "not initialized"}
        from .provider_catalog import get_model_tier
        current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
        target_tier = get_model_tier(target_provider, target_model)
        if not current_tier or not target_tier:
            return {"error": "model tier not found in catalog"}
        ratio_in = target_tier.cost_1k_in / max(current_tier.cost_1k_in, 0.0001)
        ratio_out = target_tier.cost_1k_out / max(current_tier.cost_1k_out, 0.0001)
        proj_target = (self._session_total_input_tokens / 1000 * target_tier.cost_1k_in +
                       self._session_total_output_tokens / 1000 * target_tier.cost_1k_out)
        return {
            "current": {"provider": self.config.model.provider, "model": self.config.model.model_name,
                        "cost_1k_in": current_tier.cost_1k_in, "cost_1k_out": current_tier.cost_1k_out},
            "target": {"provider": target_provider, "model": target_model,
                       "cost_1k_in": target_tier.cost_1k_in, "cost_1k_out": target_tier.cost_1k_out},
            "input_cost_ratio": round(ratio_in, 2), "output_cost_ratio": round(ratio_out, 2),
            "session_cost_current_usd": round(self._session_total_cost_usd, 6),
            "session_cost_if_target_usd": round(proj_target, 6),
        }

    def set_economy_preset(self, preset: str) -> Dict[str, Any]:
        """Switch economy preset. Regenerates system instruction if verbosity/batched flags changed."""
        if not self.config:
            return {"error": "not initialized"}
        from dataclasses import asdict as _asdict
        old_verbosity = resolve_output_verbosity(self.config.economy)
        old_batched = self.config.economy.prefer_batched_reads
        apply_economy_preset(self.config.economy, preset)
        new_verbosity = resolve_output_verbosity(self.config.economy)
        new_batched = self.config.economy.prefer_batched_reads
        if (new_verbosity != old_verbosity or new_batched != old_batched) and self.provider:
            _sandbox_preset = getattr(self.config.sandbox, "default_preset", "workspace-write")
            _plan = bool(self.config.plan_mode.enabled)
            _max_sys = 1000 if self.config.model.provider in KEYLESS_LOCAL_PROVIDER_NAMES else 0
            self._system_instruction = build_tool_calling_system_instruction(
                str(Path.cwd()), provider=self.config.model.provider,
                terse_mode=new_verbosity == "caveman", batched_reads=new_batched,
                sandbox_preset=_sandbox_preset, plan_mode=_plan,
                include_agent_tools=not _plan, max_system_tokens=_max_sys,
            )
        return _asdict(self.config.economy)

    def _maybe_apply_vision(self, message: str) -> Any:
        """Detect image paths and convert to multimodal payload if provider supports vision."""
        if not self.provider:
            return message
        images = detect_image_paths_for_provider(message, self.provider)
        if not images:
            return message
        provider_name = (self.config.model.provider if self.config else "").lower()
        if "anthropic" in provider_name or "claude" in provider_name:
            return build_multimodal_content_anthropic(message, images)
        elif "gemini" in provider_name or "google" in provider_name:
            return build_multimodal_parts_gemini(message, images)
        elif "openai" in provider_name or "openrouter" in provider_name or "gpt" in provider_name:
            return build_multimodal_content_openai(message, images)
        return message # fallback: send as plain text

    def _maybe_downshift_model(self, prompt: str) -> None:
        """Switch to a cheaper model for simple prompts or when approaching budget limit."""
        if not self.config or not self.provider:
            return
        eco = self.config.economy
        # budget-aware forced downshift: switch to cheapest regardless of complexity
        budget_pct = getattr(eco, "budget_downshift_pct", 0)
        if budget_pct > 0:
            cg = self.config.cost_guardrails
            max_cost = getattr(cg, "session_max_cost_usd", 0.0) or 0.0
            if max_cost > 0 and self._session_total_cost_usd >= max_cost * (budget_pct / 100):
                from .provider_catalog import get_downshift_model, get_model_tier
                result = get_downshift_model(self.config.model.provider)
                if result:
                    cheap_model_name, cheap_tier = result
                    if cheap_model_name != self.config.model.model_name:
                        current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
                        self._original_model_name = self.config.model.model_name
                        self._downshifted = True
                        self._turn_economy.downshifted = True
                        self._turn_economy.downshift_model = cheap_model_name
                        self.provider.switch_model(cheap_model_name)
                        if current_tier:
                            self._economy_tracker.record_downshift(
                                current_tier.cost_1k_in + current_tier.cost_1k_out,
                                cheap_tier.cost_1k_in + cheap_tier.cost_1k_out,
                            )
                        logger.info("Budget-aware downshift to %s (%.0f%% of budget used)", cheap_model_name, budget_pct)
                        return
        # use model router if available
        if self._model_router and self._model_router.enabled:
            decision = self._model_router.select_model(
                prompt=prompt,
                provider=self.config.model.provider,
                current_model=self.config.model.model_name,
                economy_preset=eco.preset,
                user_explicit_model=self._user_explicit_model,
            )
            self._economy_tracker.record_routing_decision(escalated=decision.escalated)
            self._turn_economy.routed = True
            self._turn_economy.routed_model = decision.selected_model
            self._turn_economy.routed_complexity = decision.complexity.value
            if decision.selected_model != self.config.model.model_name:
                from .provider_catalog import get_model_tier
                current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
                self._original_model_name = self.config.model.model_name
                self._downshifted = True
                self._turn_economy.downshifted = True
                self._turn_economy.downshift_model = decision.selected_model
                self.provider.switch_model(decision.selected_model)
                if current_tier:
                    new_tier = get_model_tier(self.config.model.provider, decision.selected_model)
                    if new_tier:
                        self._economy_tracker.record_downshift(
                            current_tier.cost_1k_in + current_tier.cost_1k_out,
                            new_tier.cost_1k_in + new_tier.cost_1k_out,
                        )
            return
        # fallback: legacy auto_downshift
        if not eco.auto_downshift:
            return
        if len(prompt) >= eco.downshift_threshold_chars:
            return
        if eco.downshift_exclude_tools:
            complexity = classify_prompt_complexity(prompt)
            if complexity != "simple":
                return
        from .provider_catalog import get_downshift_model, get_model_tier
        result = get_downshift_model(self.config.model.provider)
        if not result:
            return
        cheap_model_name, cheap_tier = result
        if cheap_model_name == self.config.model.model_name:
            return # already on cheapest
        current_tier = get_model_tier(self.config.model.provider, self.config.model.model_name)
        self._original_model_name = self.config.model.model_name
        self._downshifted = True
        self._turn_economy.downshifted = True
        self._turn_economy.downshift_model = cheap_model_name
        self.provider.switch_model(cheap_model_name)
        if current_tier:
            self._economy_tracker.record_downshift(
                current_tier.cost_1k_in + current_tier.cost_1k_out,
                cheap_tier.cost_1k_in + cheap_tier.cost_1k_out,
            )

    def _restore_model(self) -> None:
        """Restore original model after a downshift."""
        if self._downshifted and self._original_model_name and self.provider:
            self.provider.switch_model(self._original_model_name)
            self._original_model_name = None
            self._downshifted = False

    def _cache_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()

    def _cache_lookup(self, prompt: str) -> Optional[str]:
        """Return cached response if valid (exact match only), else None."""
        if not self.config or not self.config.economy.response_cache:
            return None
        key = self._cache_key(prompt)
        entry = self._response_cache.get(key)
        if entry is None:
            return None
        cached_text, ts = entry
        ttl = self.config.economy.response_cache_ttl
        if time.monotonic() - ts > ttl:
            del self._response_cache[key]
            return None
        return cached_text

    async def _semantic_cache_lookup(self, prompt: str, context_hash: str) -> Optional[str]:
        """Try semantic similarity cache. Returns cached response or None."""
        if self._prompt_likely_needs_tools(prompt):
            return None
        try:
            if self._semantic_cache is None:
                self._semantic_cache = get_semantic_cache()
            result = await self._semantic_cache.get(prompt, context_hash)
            if result:
                self._semantic_cache.record_savings(result.response)
                logger.info("semantic cache hit (sim=%.4f)", result.similarity)
                return result.response
        except Exception as e:
            logger.warning("semantic cache lookup failed: %s", e)
        return None

    async def _semantic_cache_store(self, prompt: str, context_hash: str, response: str) -> None:
        """Store response in semantic cache."""
        if self._prompt_likely_needs_tools(prompt):
            return
        try:
            if self._semantic_cache is None:
                self._semantic_cache = get_semantic_cache()
            model = self.provider.model_name if self.provider else ""
            await self._semantic_cache.put(prompt, context_hash, response, model_name=model)
        except Exception as e:
            logger.warning("semantic cache store failed: %s", e)

    def _cache_store(self, prompt: str, response: str) -> None:
        if not self.config or not self.config.economy.response_cache:
            return
        if self._prompt_likely_needs_tools(prompt): # skip caching mutation-likely prompts
            return
        key = self._cache_key(prompt)
        self._response_cache[key] = (response, time.monotonic())

    def _prompt_likely_needs_tools(self, prompt: str) -> bool:
        """Heuristic: return True if prompt likely triggers tool calls (unsafe to cache).

        Uses classify_prompt_complexity instead of raw keyword matching to avoid
        false positives on explanatory prompts like "what does the write function do?"
        """
        complexity = classify_prompt_complexity(prompt)
        return complexity != "simple"

    def _dedup_context_files(self, context_text: str) -> Tuple[str, int]:
        """Remove file content blocks already seen this session. Returns (deduped, tokens_saved)."""
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
                tokens_saved += get_token_counter().count(line).count
                continue
            output_lines.append(line)
        return "\n".join(output_lines), tokens_saved

    def _apply_diff_only_read(self, tool_name: str, tool_args: Dict[str, Any], result: str) -> str:
        """For read_file results, return only changed lines vs last read if diff_only_reads enabled."""
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
            return result # first read — return full
        if previous == result:
            return f"[unchanged since last read: {path}]"
        diff = difflib.unified_diff(
            previous.splitlines(keepends=True),
            result.splitlines(keepends=True),
            fromfile=f"{path} (previous)",
            tofile=f"{path} (current)",
            n=3,
        )
        diff_text = "".join(diff)
        if not diff_text:
            return f"[unchanged since last read: {path}]"
        return f"[diff-only read: {path}]\n{diff_text}"

    def _reset_idle_compact_timer(self) -> None:
        """Reset the idle auto-compact timer."""
        if not self.config:
            return
        seconds = self.config.economy.idle_compact_seconds
        if seconds <= 0:
            return
        # cancel existing timer
        if self._idle_compact_task is not None:
            self._idle_compact_task.cancel()
            self._idle_compact_task = None
        try:
            loop = asyncio.get_running_loop()
            self._idle_loop = loop
            self._idle_compact_task = loop.call_later(seconds, self._idle_compact_fire)
        except RuntimeError:
            pass # no running loop

    def _idle_compact_fire(self) -> None:
        """Fired when idle timer expires — schedule compression."""
        if self._idle_loop is None or not self.provider:
            return
        async def _do_compact():
            try:
                cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
                if not cc_cfg or not getattr(cc_cfg, "enabled", False):
                    return
                history = self.provider.get_history()
                if len(history) <= 2:
                    return
                if self._context_compressor.should_compress(history, cc_cfg):
                    before = len(history)
                    compressed = self._context_compressor.compress(history, cc_cfg)
                    self.provider.set_history(compressed)
                    after = len(compressed)
                    logger.info("Idle auto-compact: %d -> %d messages", before, after)
            except Exception:
                pass
        self._idle_loop.create_task(_do_compact())

    def _apply_economy_max_tokens(self) -> None:
        """Set economy output token cap on the provider if configured."""
        if not self.config or not self.provider:
            return
        cap = self.config.economy.economy_max_tokens
        if cap > 0:
            self.provider.economy_max_output_tokens = cap
        else:
            self.provider.economy_max_output_tokens = 0

    def _git_context_summary_cached(self) -> str:
        """Return git context, reusing cache when git state unchanged."""
        try:
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True, timeout=3,
            ).strip()
        except Exception:
            head = ""
        try:
            status = subprocess.check_output(
                ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True, timeout=3,
            ).strip()[:500]
        except Exception:
            status = ""
        git_hash = hashlib.sha256(f"{head}|{status}".encode()).hexdigest()
        if self._git_context_cache and self._git_context_cache[0] == git_hash:
            return self._git_context_cache[1]
        text = self._git_context_summary()
        self._git_context_cache = (git_hash, text)
        return text

    @staticmethod
    def _git_context_summary() -> str:
        """Build git-aware context (staged diff + recent commits) for injection."""
        parts = []
        try:
            staged = subprocess.check_output(
                ["git", "diff", "--cached", "--stat"], stderr=subprocess.DEVNULL, text=True, timeout=5,
            ).strip()
            if staged:
                parts.append(f"Staged changes:\n{staged}")
        except Exception:
            pass
        try:
            log = subprocess.check_output(
                ["git", "log", "--oneline", "-5"], stderr=subprocess.DEVNULL, text=True, timeout=5,
            ).strip()
            if log:
                parts.append(f"Recent commits:\n{log}")
        except Exception:
            pass
        return "\n\n".join(parts)

    def _ensure_working_memory_mgr(self) -> Any:
        """Lazy-init WorkingMemoryManager."""
        if self._working_memory_mgr is not None:
            return self._working_memory_mgr
        try:
            from .working_memory import WorkingMemoryManager
            caps = self.provider.get_capabilities() if self.provider else None
            max_ctx = int(caps.max_context_tokens) if caps and caps.max_context_tokens else 100_000
            self._working_memory_mgr = WorkingMemoryManager(
                repo_root=getattr(self, "_repo_root", Path.cwd()),
                max_context_tokens=max_ctx,
            )
            self._working_memory_mgr.init_session()
        except Exception as e:
            logger.warning("working memory init failed: %s", e)
            self._working_memory_mgr = None
        return self._working_memory_mgr

    async def _ensure_repo_graph(self, timeout: float = 0.1) -> None:
        """Wait briefly for background repo graph indexing to complete."""
        if self._repo_graph_task and not self._repo_graph_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._repo_graph_task), timeout=timeout)
            except (asyncio.TimeoutError, Exception):
                pass # graph not ready yet, proceed without it

    async def _maybe_builtin_workspace_map(self, message: str) -> Optional[str]:
        stripped = str(message or "").strip()
        if not stripped.startswith("/workspace-map"):
            return None
        token_budget = 2000
        suffix = stripped[len("/workspace-map"):].strip()
        if suffix:
            try:
                token_budget = max(128, int(suffix.split()[0]))
            except ValueError:
                pass
        if self._repo_graph is None:
            return "[workspace-map unavailable: repo graph disabled]"
        await self._ensure_repo_graph(timeout=5.0)
        try:
            stats = self._repo_graph.get_stats()
        except Exception:
            stats = {"files": 0}
        if not stats.get("files"):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._repo_graph.build_index)
        return self._repo_graph.build_repo_map(token_budget=token_budget)

    def _token_provider_model(self) -> Tuple[str, str]:
        """Return (provider, model) for token counting of current session."""
        provider = self.config.model.provider if self.config else ""
        model = self.config.model.model_name if self.config and self.config.model else ""
        return provider, model

    def _static_prefix_tokens(self) -> int:
        """Estimate tokens consumed by stable provider prefix content."""
        provider, model = self._token_provider_model()
        prefix = ""
        if self.provider and hasattr(self.provider, "get_prompt_prefix"):
            try:
                raw_prefix = self.provider.get_prompt_prefix()
                prefix = raw_prefix if isinstance(raw_prefix, str) else ""
            except Exception:
                prefix = ""
        sys_text = getattr(self, "_system_instruction", None) or ""
        sys_text = sys_text if isinstance(sys_text, str) else ""
        counter = get_token_counter()
        return (
            counter.count(sys_text, provider=provider, model=model).count
            + counter.count(prefix, provider=provider, model=model).count
        )

    def _compute_token_breakdown(self) -> Tuple[int, int, int]:
        """Compute (system_tokens, history_tokens, tool_result_tokens) for current state."""
        provider, model = self._token_provider_model()
        counter = get_token_counter()
        sys_tok = self._static_prefix_tokens()
        hist_tok = 0
        tool_tok = 0
        if self.provider:
            try:
                for m in self.provider.get_history():
                    toks = counter.count(str(m.get("content", "")), provider=provider, model=model).count
                    if m.get("role") in ("tool", "function"):
                        tool_tok += toks
                    else:
                        hist_tok += toks
            except Exception:
                pass
        return sys_tok, hist_tok, tool_tok

    def _check_context_pressure(self) -> Optional[str]:
        """Check if context window is under pressure. Returns reason string or None."""
        if not self.provider or not self.config:
            return None
        caps = self.provider.get_capabilities()
        max_ctx = caps.max_context_tokens
        if max_ctx <= 0:
            return None
        try:
            provider, model = self._token_provider_model()
            counter = get_token_counter()
            history = self.provider.get_history()
            current_tokens = sum(counter.count(str(m.get("content", "")), provider=provider, model=model).count for m in history)
        except Exception:
            return None
        current_tokens += self._static_prefix_tokens()
        remaining_ratio = max(0.0, 1.0 - (current_tokens / max_ctx))
        stop_ratio = getattr(self.config.agentic, "context_pressure_stop_ratio", 0.2)
        warn_ratio = getattr(self.config.agentic, "context_pressure_warn_ratio", 0.5)
        if remaining_ratio < stop_ratio:
            return "context_pressure"
        if remaining_ratio < warn_ratio:
            logger.warning("Context pressure: %.0f%% remaining (warn threshold %.0f%%)", remaining_ratio * 100, warn_ratio * 100)
        return None

    async def _auto_compress_on_pressure(self) -> Optional[str]:
        """Auto-compress if context pressure exceeds economy threshold. Returns strategy used or None."""
        if not self.config or not self.provider:
            return None
        threshold = getattr(self.config.economy, "auto_compress_pressure_pct", 0)
        if not threshold or threshold <= 0:
            return None
        pressure = self.get_context_pressure()
        if pressure["pressure_pct"] < threshold:
            return None
        cc_cfg = getattr(self.config, "context_compression", None)
        if not cc_cfg or not getattr(cc_cfg, "enabled", False):
            return None
        history = self.provider.get_history()
        if len(history) <= 4:
            return None
        _strip_chars = getattr(self.config.economy, "tool_strip_chars", 200)
        compressed = await self._context_compressor.compress_auto(
            history, cc_cfg, provider=self.provider, tool_strip_chars=_strip_chars,
        )
        if len(compressed) < len(history):
            self.provider.set_history(compressed)
            logger.info("Auto-compress on pressure (%.1f%%): %d -> %d messages",
                        pressure["pressure_pct"], len(history), len(compressed))
            return "auto_pressure"
        return None

    def _refresh_system_context(self) -> bool:
        """Rebuild system instruction if git/instruction state changed. Returns True if updated."""
        if not self._initialized or not self.provider or not self.config:
            return False
        started = time.monotonic()
        terse = resolve_output_verbosity(self.config.economy) == "caveman"
        batched = getattr(self.config.economy, "prefer_batched_reads", False)
        repo_root = getattr(self, "_repo_root", Path.cwd())
        _sandbox_preset = getattr(self.config.sandbox, "default_preset", "workspace-write")
        _plan = bool(self.config.plan_mode.enabled)
        git_state_hash = self._git_state_hash(repo_root)
        memory_index = self._memory_manager.load_index() if self._memory_manager else ""
        memory_index_hash = hashlib.sha256(
            str(memory_index or "").encode("utf-8", errors="replace")
        ).hexdigest()
        instruction_snapshot_hash = self._instruction_snapshot_hash()
        refresh_inputs = (
            git_state_hash,
            memory_index_hash,
            instruction_snapshot_hash,
            str(self.config.model.provider),
            str(self.config.model.model_name),
            str(_sandbox_preset),
            str(_plan),
            str(terse),
            str(batched),
        )
        if refresh_inputs == getattr(self, "_system_refresh_inputs", None):
            return False
        core_module = sys.modules.get("poor_cli.core")
        build_instruction = getattr(core_module, "build_tool_calling_system_instruction", build_tool_calling_system_instruction)
        detect_tone = getattr(core_module, "detect_tone_from_user_memories", detect_tone_from_user_memories)
        new_instruction = build_instruction(
            str(repo_root), provider=self.config.model.provider,
            terse_mode=terse, batched_reads=batched,
            sandbox_preset=_sandbox_preset,
            plan_mode=_plan,
            include_gh_tools=getattr(self.config.tools, "enable_git_tools", True),
            include_agent_tools=not _plan,
        )
        if memory_index:
            new_instruction += (
                "\n\n## Persistent Memory\n"
                "The following memories were saved in previous sessions.\n\n"
                f"{memory_index}\n"
            )
        tone_helper = getattr(self, "_tone_suffix_for_memory_index", None)
        if callable(tone_helper):
            tone_suffix = tone_helper(memory_index, detect_tone)
            if tone_suffix:
                new_instruction += tone_suffix
        new_hash = hashlib.sha256(new_instruction.encode("utf-8", errors="replace")).hexdigest()
        self._system_refresh_inputs = refresh_inputs
        if new_hash == self._system_context_hash:
            self._record_perf_span(
                "core._refresh_system_context",
                (time.monotonic() - started) * 1000.0,
                details={"updated": False},
            )
            return False
        self._git_context_cache = None # git state changed, invalidate
        self._system_instruction = new_instruction
        self.provider.update_system_instruction(self._system_instruction)
        self._system_context_hash = new_hash
        context_contract = getattr(self, "_context_contract", None)
        if context_contract:
            context_contract.invalidate_cache()
        self._record_perf_span(
            "core._refresh_system_context",
            (time.monotonic() - started) * 1000.0,
            details={"updated": True},
        )
        logger.debug("System context refreshed (hash=%s)", new_hash[:12])
        return True

    @staticmethod
    def _git_state_hash(repo_root: Path) -> str:
        try:
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_root),
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            ).strip()
        except Exception:
            head = ""
        try:
            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(repo_root),
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            ).strip()
        except Exception:
            status = ""
        return hashlib.sha256(f"{head}|{status}".encode("utf-8", errors="replace")).hexdigest()

    def _instruction_snapshot_hash(self) -> str:
        snapshot = getattr(self, "_last_instruction_snapshot", None)
        if snapshot is None:
            return ""
        try:
            payload = snapshot.to_dict()
        except Exception:
            return ""
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8", errors="replace")
        ).hexdigest()

    def list_workflow_templates(self) -> List[Dict[str, Any]]:
        if not self.config:
            return list_workflow_templates()
        templates = list_workflow_templates()
        defaults = getattr(getattr(self.config, "workflow", None), "defaults", {}) or {}
        if not isinstance(defaults, dict):
            return templates
        merged: List[Dict[str, Any]] = []
        for template in templates:
            override = defaults.get(template["name"], {})
            if isinstance(override, dict):
                merged.append({**template, **override})
            else:
                merged.append(template)
        return merged

    def get_workflow_template(self, name: str) -> Optional[Dict[str, Any]]:
        template = get_workflow_template(name)
        if template is None:
            return None
        defaults = getattr(getattr(self.config, "workflow", None), "defaults", {}) if self.config else {}
        override = defaults.get(template["name"], {}) if isinstance(defaults, dict) else {}
        if isinstance(override, dict):
            template = {**template, **override}
        return template

    def get_last_run_id(self) -> Optional[str]:
        return self._last_run_id

    def list_runs(
        self,
        *,
        source_kind: Optional[str] = None,
        source_id: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        if not self._run_history:
            return []
        payloads: List[Dict[str, Any]] = []
        for record in self._run_history.list_runs(
            source_kind=source_kind,
            source_id=source_id,
            limit=limit,
        ):
            payload = record.to_dict()
            diagnostics = self._extract_run_diagnostics(payload.get("metadata", {}))
            payload["diagnostics"] = diagnostics
            payload["completionReasonCode"] = diagnostics.get("completionReasonCode", "")
            payload["transitionCount"] = len(diagnostics.get("turnTransitions", []))
            payload["turnCount"] = len(diagnostics.get("turnOrchestration", []))
            payloads.append(payload)
        return payloads

    def build_status_view(self) -> Dict[str, Any]:
        provider_info = self.get_provider_info() if self._initialized else {}
        provider_status = dict(getattr(self, "_provider_readiness_cache", {}) or {})
        if not provider_status:
            schedule_probe = getattr(self, "_schedule_provider_readiness_probe", None)
            if callable(schedule_probe):
                schedule_probe()
        recent_runs = self.list_runs(limit=5)
        active_runs = [run for run in recent_runs if run.get("status") == "running"]
        last_run = recent_runs[0] if recent_runs else None
        last_mutation = dict(self._last_mutation_summary)
        last_context = dict(self._last_context_preview)
        trusted_security = {
            "trustedWorkspaceBoundary": bool(
                getattr(getattr(self.config, "security", None), "enforce_trusted_workspace", True)
            ),
            "trustedRoots": list(
                getattr(getattr(self.config, "security", None), "trusted_roots", []) or []
            ),
        }
        from .credentials import get_credential_store

        return {
            "session": {
                "initialized": bool(self._initialized),
                "provider": provider_info.get("name", ""),
                "model": provider_info.get("model", ""),
                "routingMode": self.get_routing_mode(),
                "permissionMode": getattr(
                    getattr(getattr(self.config, "security", None), "permission_mode", None),
                    "value",
                    str(getattr(getattr(self.config, "security", None), "permission_mode", "")),
                ),
            },
            "trust": {
                "sandboxPreset": getattr(getattr(self.config, "sandbox", None), "default_preset", ""),
                "policy": self.get_policy_status(),
                "audit": self.get_policy_status().get("audit", {}),
                "mcp": self.get_mcp_status(),
                "security": trusted_security,
                "checkpointing": bool(getattr(getattr(self.config, "checkpoint", None), "enabled", False)),
            },
            "provider": {
                "active": provider_info,
                "readiness": provider_status,
                "fallback": dict(self._last_fallback_summary),
                "lastError": self._last_provider_error,
                "privacyPosture": suggested_privacy_posture(provider_status),
                "keyring": get_credential_store().status(),
            },
            "context": {
                "lastPreview": last_context,
                "pressure": self.get_context_pressure() if self.provider else {},
                "compaction": self.get_compaction_status(),
            },
            "runs": {
                "recent": recent_runs,
                "activeCount": len(active_runs),
                "lastRun": last_run,
                "lastRunDiagnostics": (last_run or {}).get("diagnostics", {}),
            },
            "recovery": {
                "cost": self.get_session_cost_summary(),
                "lastMutation": last_mutation,
            },
        }

    def build_doctor_report(self) -> Dict[str, Any]:
        status_view = self.build_status_view()
        provider_status = status_view["provider"]["readiness"]
        checks: List[Dict[str, Any]] = []
        ready_provider_count = len([payload for payload in provider_status.values() if payload.get("ready")])
        checks.append(
            {
                "id": "providers",
                "title": "Provider readiness",
                "status": "ok" if ready_provider_count else "degraded",
                "message": f"{ready_provider_count} provider(s) ready",
                "action": "Run `/setup`, `/api-key status`, or switch to `ollama` private mode.",
            }
        )
        checks.append(
            {
                "id": "sandbox",
                "title": "Execution safety",
                "status": "warning"
                if status_view["trust"]["sandboxPreset"] == "full-access"
                else "ok",
                "message": f"Sandbox preset `{status_view['trust']['sandboxPreset']}`",
                "action": "Prefer `review-only` or `workspace-write` for normal coding sessions.",
            }
        )
        checks.append(
            {
                "id": "routing",
                "title": "Routing mode",
                "status": "ok",
                "message": f"Routing mode `{status_view['session']['routingMode']}`",
                "action": "Use `private` to force Ollama-only routing when local privacy matters.",
            }
        )
        checks.append(
            {
                "id": "context",
                "title": "Context visibility",
                "status": "ok" if status_view["context"]["lastPreview"] else "warning",
                "message": "Context explanation available"
                if status_view["context"]["lastPreview"]
                else "No context preview captured yet",
                "action": "Run `/context explain` or preview context before a large request.",
            }
        )
        checks.append(
            {
                "id": "recovery",
                "title": "Recovery state",
                "status": "ok",
                "message": "Checkpointing enabled"
                if status_view["trust"]["checkpointing"]
                else "Checkpointing disabled",
                "action": "Enable checkpoints for safer mutation-heavy sessions.",
            }
        )
        overall = "ok" if all(check["status"] == "ok" for check in checks) else "degraded"
        return {
            "summary": {
                "overall": overall,
                "routingMode": status_view["session"]["routingMode"],
                "privacyPosture": status_view["provider"]["privacyPosture"],
                "readyProviderCount": ready_provider_count,
            },
            "checks": checks,
            "statusView": status_view,
        }

    def inspect_instruction_stack(
        self,
        referenced_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return the active deterministic instruction stack."""
        if not referenced_files and self._last_instruction_snapshot is not None:
            return self._last_instruction_snapshot.to_dict()
        snapshot = self._inspect_instruction_snapshot(
            referenced_files,
            skill_context=self._build_instruction_skill_context(),
            skill_plan=self._last_instruction_skill_plan,
        )
        self._last_instruction_snapshot = snapshot
        return snapshot.to_dict()

    def get_policy_status(self) -> Dict[str, Any]:
        """Return repo-local policy and audit status."""
        hooks = self._hook_manager.status() if self._hook_manager else {
            "hooksDir": str(Path.cwd() / ".poor-cli" / "hooks"),
            "totalHooks": 0,
            "supportedSchemaVersions": [1],
            "validationErrors": [],
            "events": {},
        }
        return {
            "hooks": hooks,
            "audit": {
                "enabled": self._audit_logger is not None,
                "path": str(self._audit_logger.audit_dir) if self._audit_logger else "",
            },
        }

    def get_mcp_status(self) -> Dict[str, Any]:
        """Return MCP connectivity and tool registration status."""
        if self._mcp_manager is None:
            return {
                "configuredServers": 0,
                "connectedServers": 0,
                "toolCount": 0,
                "servers": {},
            }
        return self._mcp_manager.status()

    async def shutdown(self) -> None:
        """Release external resources owned by the core."""
        # flush budget controller logs
        try:
            self._budget_logger.close()
        except Exception:
            pass
        # persist session cost to history
        self._persist_cost_history()
        # emit session_end hook
        try:
            await self._emit_policy_hooks("session_end", {
                "inputTokens": getattr(self, "_session_total_input_tokens", 0),
                "outputTokens": getattr(self, "_session_total_output_tokens", 0),
            })
        except Exception:
            pass
        # clean up headless browser if used
        try:
            from .browser_tool import shutdown_browser
            await shutdown_browser()
        except Exception:
            pass
        # auto-save memorable patterns from this session
        if self.provider and self._initialized:
            try:
                from .auto_memory import auto_save_session_memories
                history = self.provider.get_history()
                if history:
                    saved = await auto_save_session_memories(history, provider=self.provider)
                    if saved:
                        logger.info("auto-saved %d memories on shutdown", len(saved))
            except Exception as exc:
                logger.debug("auto-memory on shutdown failed: %s", exc)
        if self._mcp_manager is not None:
            await self._mcp_manager.shutdown()
        # cancel background tasks
        for task in (
            self._repo_graph_task,
            self._pending_llm_compression,
            self._auto_history_compact_task,
            getattr(self, "_provider_probe_task", None),
        ):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._repo_graph_task = None
        self._pending_llm_compression = None
        self._auto_history_compact_task = None
        self._provider_probe_task = None
        # close pooled HTTP session in tool registry
        if self.tool_registry and hasattr(self.tool_registry, "close"):
            try:
                await self.tool_registry.close()
            except Exception:
                pass

    async def clear_history(self) -> None:
        """
        Clear conversation history.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info("Clearing history")
        
        if hasattr(self.provider, 'clear_history'):
            await self.provider.clear_history()
        
        if self.history_adapter:
            self.history_adapter.clear_history()

    def _resolve_tiered_compaction_mode(self, strategy: str) -> str:
        requested = str(strategy or "compact").strip().lower() or "compact"
        if requested in {"gentle", "aggressive", "balanced"}:
            return requested
        preset = str(getattr(getattr(self.config, "economy", None), "preset", "balanced") or "balanced").strip().lower()
        if requested == "auto":
            pressure_pct = float(self.get_context_pressure().get("pressure_pct", 0) or 0)
            if pressure_pct >= 85:
                return "aggressive"
        if preset == "frugal":
            return "aggressive"
        if preset == "quality":
            return "gentle"
        return "balanced"

    def _resolve_auto_compaction_settings(self) -> Tuple[float, float]:
        cc_cfg = getattr(self.config, "context_compression", None) if self.config else None
        eco_cfg = getattr(self.config, "economy", None) if self.config else None
        threshold = float(getattr(cc_cfg, "auto_compact_threshold", 0.7) or 0.0)
        target = float(getattr(cc_cfg, "auto_compact_target", 0.4) or 0.0)
        eco_threshold = float(getattr(eco_cfg, "auto_compress_pressure_pct", 0.0) or 0.0)
        if eco_threshold > 0:
            threshold = eco_threshold / 100.0
        elif str(getattr(eco_cfg, "preset", "") or "").strip().lower() == "quality":
            threshold = 0.0
        return max(0.0, threshold), max(0.0, target)

    def _record_compaction_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        recorded = dict(payload or {})
        recorded["timestamp"] = time.time()
        self._last_compaction_status = recorded
        return recorded

    async def _summarize_compaction_chunk(
        self,
        messages: List[Dict[str, Any]],
        draft_summary: str,
        policy: CompactionPolicy,
    ) -> str:
        del policy
        if not self.provider:
            return draft_summary
        conversation_text = self._history_to_text(messages)
        if not conversation_text.strip():
            return draft_summary
        prompt = (
            "Summarize the following conversation chunk into this exact structure:\n"
            "## Session Summary (turns 1-N)\n"
            "- User asked: ...\n"
            "- Files modified/referenced: ...\n"
            "- Key decisions: ...\n"
            "- Tool outcomes: ...\n"
            "- Unresolved: ...\n"
            "- Dropped noise lessons: ...\n"
            "Be factual and terse. Keep concrete file paths.\n\n"
            f"Draft summary:\n{draft_summary}\n\n"
            f"Conversation:\n{conversation_text}"
        )
        response = await self.provider.send_message(prompt)
        rendered = response.content.strip() if response and response.content else ""
        return rendered or draft_summary

    async def _compact_tiered_context(
        self,
        history: List[Dict[str, Any]],
        messages_before: int,
        *,
        strategy: str,
        trigger: str,
        allow_model_summary: bool,
    ) -> Dict[str, Any]:
        self._save_transcript(history)
        mode = self._resolve_tiered_compaction_mode(strategy)
        if not history:
            return self._record_compaction_status(
                {
                    "state": "done",
                    "strategy": "compact",
                    "mode": mode,
                    "trigger": trigger,
                    "summary": "(empty history)",
                    "messages_before": messages_before,
                    "messages_after": 0,
                    "tokens_before": 0,
                    "tokens_after": 0,
                    "removed_tokens": 0,
                    "tier_counts": {},
                    "pruned_turns": 0,
                    "pruning_summary": "",
                    "pruning_reasons": {},
                    "pruning_sidecar_path": None,
                }
            )
        max_ctx = 0
        if self.provider:
            try:
                max_ctx = int(self.provider.get_capabilities().max_context_tokens or 0)
            except Exception:
                max_ctx = 0
        threshold, target = self._resolve_auto_compaction_settings()
        callback = self._summarize_compaction_chunk if allow_model_summary else None
        result = await self._tiered_compactor.compact(
            history,
            max_tokens=max_ctx,
            mode=mode,
            economy_preset=str(getattr(getattr(self.config, "economy", None), "preset", "balanced") or "balanced"),
            trigger=trigger,
            summary_callback=callback,
            auto_compact_threshold=threshold,
            auto_compact_target=target,
        )
        pruning_sidecar_path = self._save_pruning_sidecar(result.pruned_turns)
        if self.provider:
            self.provider.set_history(result.history)
        if self.history_adapter:
            self.history_adapter.clear_history()
            for message in result.history:
                self.history_adapter.add_message(message["role"], message["content"])
        if result.pruning_summary:
            if not isinstance(getattr(self, "_pending_events", None), list):
                self._pending_events = []
            self._pending_events.append(
                CoreEvent(
                    type="progress",
                    data={"phase": "history_pruning", "message": result.pruning_summary},
                )
            )
        return self._record_compaction_status(
            {
                "state": "done",
                "strategy": "compact",
                "mode": result.mode,
                "trigger": trigger,
                "summary": result.summary,
                "messages_before": result.messages_before,
                "messages_after": result.messages_after,
                "tokens_before": result.tokens_before,
                "tokens_after": result.tokens_after,
                "removed_tokens": result.removed_tokens,
                "tier_counts": result.tier_counts,
                "utilization_before_pct": round(result.utilization_before * 100, 1),
                "utilization_after_pct": round(result.utilization_after * 100, 1),
                "pruned_turns": result.pruned_count,
                "pruning_summary": result.pruning_summary,
                "pruning_reasons": result.pruning_reasons,
                "pruning_sidecar_path": pruning_sidecar_path,
            }
        )

    async def _run_auto_compaction(self) -> Optional[Dict[str, Any]]:
        if not self.provider:
            return None
        history = self.provider.get_history()
        if len(history) <= 4:
            return None
        return await self._compact_tiered_context(
            history,
            len(history),
            strategy="auto",
            trigger="auto",
            allow_model_summary=False,
        )

    def _schedule_auto_compaction(self) -> Optional[Dict[str, Any]]:
        if not self.config or not self.provider:
            return None
        cc_cfg = getattr(self.config, "context_compression", None)
        if not cc_cfg or not getattr(cc_cfg, "enabled", False):
            return None
        threshold, target = self._resolve_auto_compaction_settings()
        if threshold <= 0 or target <= 0:
            return None
        pressure = self.get_context_pressure()
        pressure_ratio = float(pressure.get("pressure_pct", 0) or 0) / 100.0
        if pressure_ratio < threshold:
            return None
        task = getattr(self, "_auto_history_compact_task", None)
        if task and not task.done():
            return None
        queued = self._record_compaction_status(
            {
                "state": "queued",
                "strategy": "compact",
                "mode": self._resolve_tiered_compaction_mode("auto"),
                "trigger": "auto",
                "utilization_before_pct": round(pressure_ratio * 100, 1),
                "target_utilization_pct": round(target * 100, 1),
            }
        )
        loop = asyncio.get_running_loop()
        self._auto_history_compact_task = loop.create_task(self._run_auto_compaction())

        def _done_callback(task_obj: asyncio.Task) -> None:
            try:
                completed = task_obj.result()
            except Exception as exc:
                logger.warning("auto compaction failed: %s", exc)
                self._record_compaction_status(
                    {
                        "state": "error",
                        "strategy": "compact",
                        "mode": queued.get("mode", "balanced"),
                        "trigger": "auto",
                        "error": str(exc),
                    }
                )
                return
            if completed:
                logger.info(
                    "Auto compact: %d -> %d messages",
                    int(completed.get("messages_before", 0) or 0),
                    int(completed.get("messages_after", 0) or 0),
                )

        self._auto_history_compact_task.add_done_callback(_done_callback)
        return queued

    async def compact_context(self, strategy: str) -> Dict[str, Any]:
        """Apply a context management strategy to reduce conversation size."""
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        history = self.get_history()
        messages_before = len(history)
        if strategy in {"auto", "compact", "gentle", "aggressive", "balanced"}:
            result = await self._compact_tiered_context(
                history,
                messages_before,
                strategy=strategy,
                trigger="manual",
                allow_model_summary=True,
            )
        elif strategy == "compress":
            result = self._compact_compress(history, messages_before)
        elif strategy == "handoff":
            result = await self._compact_handoff(history, messages_before)
        else:
            raise PoorCLIError(f"Unknown compaction strategy: {strategy}")
        # reset working memory after compaction — delta state is stale
        try:
            if self._working_memory_mgr:
                summary = result.get("summary", "") if isinstance(result, dict) else ""
                self._working_memory_mgr.reset(new_summary=summary)
                logger.info("working memory reset after compact (%s)", strategy)
        except Exception as e:
            logger.warning("working memory reset failed: %s", e)
        return result

    def _save_transcript(self, history: List[Dict[str, Any]]) -> Optional[str]:
        from ._turn_transcripts import save_transcript
        return save_transcript(self, history)

    def _save_pruning_sidecar(self, pruned_turns: List[Dict[str, Any]]) -> Optional[str]:
        from ._turn_transcripts import save_pruning_sidecar
        return save_pruning_sidecar(self, pruned_turns)

    async def _compact_summarize(self, history: List[Dict[str, Any]], messages_before: int) -> Dict[str, Any]:
        """Summarize conversation in-place, re-seed provider."""
        self._save_transcript(history)
        conversation_text = self._history_to_text(history)
        if not conversation_text.strip():
            return {"strategy": "compact", "summary": "(empty history)", "messages_before": messages_before, "messages_after": 0}
        prompt = (
            "Summarize the following conversation concisely. "
            "Preserve key decisions, file paths, code changes, and current task state. "
            "Output only the summary, no preamble.\n\n"
            f"{conversation_text}"
        )
        response = await self.provider.send_message(prompt) # one-shot call outside the chat session
        summary = response.content.strip() if response.content else "(no summary generated)"
        await self.provider.clear_history()
        if self.history_adapter:
            self.history_adapter.clear_history()
        await self.provider.send_message(f"[Context from previous conversation]\n{summary}") # inject summary as context
        if self.history_adapter:
            self.history_adapter.add_message("user", f"[Context from previous conversation]\n{summary}")
        return {"strategy": "compact", "summary": summary, "messages_before": messages_before, "messages_after": 1}

    def _compact_compress(self, history: List[Dict[str, Any]], messages_before: int) -> Dict[str, Any]:
        """Strip tool calls/results, keep user+assistant text only."""
        self._save_transcript(history)
        compressed = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("system", "tool", "function"): # skip non-conversation messages
                continue
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif "text" in part:
                            text_parts.append(str(part["text"]))
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = "\n".join(text_parts)
            if not content or not content.strip():
                continue
            parts = msg.get("parts") # gemini uses 'parts' key
            if parts and not content:
                text_parts = [p for p in parts if isinstance(p, str)]
                content = "\n".join(text_parts)
            if role == "model":
                role = "assistant"
            if role in ("user", "assistant"):
                compressed.append({"role": role, "content": content})
        self.provider.set_history(compressed)
        if self.history_adapter:
            self.history_adapter.clear_history()
            for msg in compressed:
                self.history_adapter.add_message(msg["role"], msg["content"])
        return {"strategy": "compress", "summary": f"Kept {len(compressed)} text messages", "messages_before": messages_before, "messages_after": len(compressed)}

    async def _compact_handoff(self, history: List[Dict[str, Any]], messages_before: int) -> Dict[str, Any]:
        """Generate summary, start completely new session."""
        self._save_transcript(history)
        conversation_text = self._history_to_text(history)
        if not conversation_text.strip():
            await self.clear_history()
            return {"strategy": "handoff", "summary": "(empty history)", "messages_before": messages_before, "messages_after": 0}
        prompt = (
            "Create a handoff summary for a new conversation thread. Include:\n"
            "- Current task and goal\n"
            "- Key decisions made\n"
            "- Files modified or relevant\n"
            "- Open items or next steps\n"
            "Be concise. Output only the summary.\n\n"
            f"{conversation_text}"
        )
        response = await self.provider.send_message(prompt)
        summary = response.content.strip() if response.content else "(no summary generated)"
        await self.clear_history()
        handoff_msg = f"[Handoff from previous session]\n{summary}" # seed new session with handoff context
        await self.provider.send_message(handoff_msg)
        if self.history_adapter:
            self.history_adapter.add_message("user", handoff_msg)
        return {"strategy": "handoff", "summary": summary, "messages_before": messages_before, "messages_after": 1}

    def _history_to_text(self, history: List[Dict[str, Any]]) -> str:
        """Convert history to readable text for summarization."""
        lines = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(str(part["text"]))
                content = "\n".join(text_parts)
            parts = msg.get("parts")
            if parts and not content:
                text_parts = [p for p in parts if isinstance(p, str)]
                content = "\n".join(text_parts)
            if content and content.strip():
                lines.append(f"{role}: {content[:2000]}") # cap per message
        return "\n\n".join(lines[-50:]) # last 50 messages max


    def _build_full_message(self, message: str, context_files: Optional[List[str]] = None) -> str:
        """Legacy sync helper retained for compatibility."""
        return message

    async def _select_context_files(
        self,
        message: str,
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
        self,
        message: str,
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> str:
        """Build a backend-owned context message with excerpted files."""
        from .context_assembly import ContextAssemblyOrchestrator
        assembler = getattr(self, "_context_assembly", None)
        if assembler is None:
            assembler = ContextAssemblyOrchestrator(self)
            self._context_assembly = assembler
        snapshot = await assembler.assemble(
            prompt=message,
            context_files=context_files,
            pinned_context_files=pinned_context_files,
            context_budget_tokens=context_budget_tokens,
            activate_tools=False,
        )
        self._last_context_snapshot = snapshot
        return snapshot.message

    async def preview_context(
        self,
        message: str = "",
        context_files: Optional[List[str]] = None,
        pinned_context_files: Optional[List[str]] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Preview backend-owned context selection without sending a chat turn."""
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        if not self._context_manager:
            return {"files": [], "totalTokens": 0, "truncated": False, "message": "Context manager unavailable"}
        preview = await self._context_manager.preview_context(
            message=message,
            explicit_files=context_files or [],
            pinned_files=pinned_context_files or [],
            repo_root=str(Path.cwd()),
            max_tokens=context_budget_tokens,
            max_files=12,
        )
        self._record_context_preview(preview)
        return preview

    @staticmethod
    def _confidence_bucket(percent: int) -> str:
        """Map confidence percentage to one of five confidence categories."""
        bounded = max(0, min(percent, 100))
        for upper_bound, category in _CONFIDENCE_BANDS:
            if bounded <= upper_bound:
                return category
        return "Very High"

    @staticmethod
    def _extract_confidence_percent(response_text: str) -> Optional[int]:
        """Extract the model-reported confidence percentage when present."""
        matches = list(_CONFIDENCE_PERCENT_RE.finditer(response_text))
        if not matches:
            return None
        raw_percent = int(matches[-1].group(1))
        return max(0, min(raw_percent, 100))

    def _build_confidence_line(self, percent: int) -> str:
        """Build the normalized confidence line shown to users."""
        category = self._confidence_bucket(percent)
        return f"Confidence: {category} ({percent}%)"

    @staticmethod
    def _has_trailing_confidence_line(response_text: str) -> bool:
        """Check whether the final non-empty line already contains confidence output."""
        lines = response_text.splitlines()
        if not lines:
            return False
        return bool(_CONFIDENCE_LINE_RE.match(lines[-1].strip()))

    def _ensure_confidence_line(self, response_text: str) -> Tuple[str, str]:
        """
        Ensure every non-empty response ends with a confidence score line.

        Returns:
            Tuple of (final_text, appended_suffix). appended_suffix is empty when
            no new confidence text was added.
        """
        trimmed = response_text.rstrip()
        if not trimmed:
            return response_text, ""

        if self._has_trailing_confidence_line(trimmed):
            return trimmed, ""

        percent = self._extract_confidence_percent(trimmed)
        if percent is None:
            percent = _DEFAULT_CONFIDENCE_PERCENT

        confidence_line = self._build_confidence_line(percent)
        if trimmed.endswith(confidence_line):
            return trimmed, ""

        separator = "\n\n"
        appended_suffix = f"{separator}{confidence_line}"
        return f"{trimmed}{appended_suffix}", appended_suffix

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get conversation history in normalized format.
        
        Returns:
            List of dicts with 'role' and 'content' keys.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        history = []
        
        if hasattr(self.provider, 'get_history'):
            raw_history = self.provider.get_history()
            for entry in raw_history:
                if isinstance(entry, dict):
                    history.append({
                        "role": entry.get("role", "unknown"),
                        "content": entry.get("content", "")
                    })
        
        return history

    async def switch_provider(
        self,
        provider_name: str,
        model_name: Optional[str] = None
    ) -> None:
        """
        Switch to a different AI provider.
        
        Args:
            provider_name: Name of the provider to switch to.
            model_name: Optional model name. If None, uses provider default.
        
        Raises:
            ConfigurationError: If switch fails.
        """
        logger.info(f"Switching to provider: {provider_name}")
        
        # Get API key for new provider
        api_key = self._config_manager.get_api_key(provider_name)
        
        if not api_key and provider_name not in KEYLESS_LOCAL_PROVIDER_NAMES:
            raise ConfigurationError(f"No API key found for provider: {provider_name}")
        
        # Determine model name
        if not model_name:
            provider_config = self.config.model.providers.get(provider_name)
            if provider_config:
                model_name = provider_config.default_model
            else:
                raise ConfigurationError(f"Unknown provider: {provider_name}")
        
        # Get provider config for additional settings
        provider_config = self._config_manager.get_provider_config(provider_name)
        extra_kwargs = {}
        if provider_config and provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url
        
        # Create the candidate provider, but do not swap global state
        # until initialization succeeds. This avoids ending up on a broken
        # provider instance when initialization fails (e.g., Ollama unreachable).
        candidate_provider = ProviderFactory.create(
            provider_name=provider_name,
            api_key=api_key or "",
            model_name=model_name,
            **extra_kwargs
        )

        # Initialize provider with tools before committing the switch.
        tool_declarations = self.tool_registry.get_tool_declarations()
        init_tools = (
            tool_declarations
            if provider_has_capability(candidate_provider, ProviderCapability.TOOL_CALLING)
            else []
        )
        if not provider_has_capability(candidate_provider, ProviderCapability.TOOL_CALLING):
            logger.info(
                "Provider %s/%s does not support function calling; switching without tools",
                provider_name,
                model_name,
            )
        await candidate_provider.initialize(
            tools=init_tools,
            system_instruction=self._system_instruction
        )

        # Commit provider + config only after successful initialization.
        self.provider = candidate_provider
        self._provider_ready = True
        self.config.model.provider = provider_name
        self.config.model.model_name = model_name
        self._user_explicit_model = True

        logger.info(f"Switched to {provider_name}/{model_name}")

    def set_system_instruction(self, instruction: str) -> None:
        """
        Update the system instruction.
        
        Note: Takes effect on next message, not retroactively.
        
        Args:
            instruction: New system instruction.
        """
        self._system_instruction = instruction
        self._system_refresh_inputs = None
        logger.info("System instruction updated")

    @staticmethod
    def _checkpoint_metadata(
        checkpoint: Any,
        restored_files: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Normalize checkpoint metadata for API-style responses."""
        payload = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "created_at": checkpoint.created_at,
            "description": checkpoint.description,
            "operation_type": checkpoint.operation_type,
            "file_count": checkpoint.get_file_count(),
            "total_size_bytes": checkpoint.get_total_size(),
            "tags": checkpoint.tags,
        }
        if restored_files is not None:
            payload["restored_files"] = restored_files
        return payload

    async def create_checkpoint(
        self,
        file_paths: List[str],
        description: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create a checkpoint for the given files.
        
        Args:
            file_paths: List of file paths to checkpoint.
            description: Description of the checkpoint.
        
        Returns:
            Checkpoint metadata or None if checkpointing is disabled.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        if not self.checkpoint_manager:
            logger.warning("Checkpoint manager not enabled")
            return None
        
        logger.info(f"Creating checkpoint for {len(file_paths)} files")
        
        try:
            checkpoint = await asyncio.to_thread(
                self.checkpoint_manager.create_checkpoint,
                file_paths,
                description
            )
            self._log_audit_event(
                AuditEventType.CHECKPOINT_CREATE,
                operation="checkpoint:create",
                target=",".join(file_paths),
                details={
                    "checkpointId": checkpoint.checkpoint_id,
                    "description": description,
                    "filePaths": file_paths,
                },
            )
            return self._checkpoint_metadata(checkpoint)
        except Exception as e:
            logger.error(f"Checkpoint creation failed: {e}")
            raise PoorCLIError(f"Failed to create checkpoint: {e}")

    async def restore_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Restore a checkpoint.
        
        Args:
            checkpoint_id: ID of the checkpoint to restore.
        
        Returns:
            Checkpoint restore metadata.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        if not self.checkpoint_manager:
            logger.warning("Checkpoint manager not enabled")
            return {}
        
        logger.info(f"Restoring checkpoint: {checkpoint_id}")
        
        try:
            checkpoint = self.checkpoint_manager.get_checkpoint(checkpoint_id)
            if checkpoint is None:
                raise PoorCLIError(f"Checkpoint not found: {checkpoint_id}")

            restored_files = await asyncio.to_thread(
                self.checkpoint_manager.restore_checkpoint,
                checkpoint_id,
            )
            self._log_audit_event(
                AuditEventType.CHECKPOINT_RESTORE,
                operation="checkpoint:restore",
                target=checkpoint_id,
                details={
                    "checkpointId": checkpoint_id,
                    "restoredFiles": restored_files,
                },
            )
            await self._emit_policy_hooks(
                "checkpoint_restored",
                {
                    "checkpointId": checkpoint_id,
                    "restoredFiles": restored_files,
                },
            )
            return self._checkpoint_metadata(checkpoint, restored_files=restored_files)
        except Exception as e:
            logger.error(f"Checkpoint restore failed: {e}")
            raise PoorCLIError(f"Failed to restore checkpoint: {e}")
