"""In-process sub-agent delegation for task decomposition."""

from __future__ import annotations
import asyncio
from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid
from .agent_definitions import AgentDefinition, effective_allowed_tools
from .exceptions import setup_logger
from .policy_hooks import emit_policy_hook_nowait

logger = setup_logger(__name__)


class SubAgentArchetype(str, Enum):
    GENERIC = "generic"
    RESEARCH = "research" # read-only exploration
    CODE = "code" # full edit capabilities
    TEST = "test" # run tests + read
    REVIEW = "review" # read + git diff analysis
    ADVISOR = "advisor" # plan/risk critique, no writes

_ARCHETYPE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "research": {
        "allowed_tools": {
            "read_file", "glob_files", "grep_files", "list_directory",
            "git_status", "git_diff", "git_log", "git_status_diff",
            "diff_files", "dependency_inspect", "fetch_url",
            "semantic_search", "process_logs",
        },
        "system_prompt": (
            "You are a research sub-agent. Your job is to explore and gather information.\n"
            "- Read files, search code, inspect dependencies, and analyze git state\n"
            "- Return only findings that change the parent agent's next action\n"
            "- Do NOT modify any files or run destructive commands\n"
        ),
    },
    "code": {
        "allowed_tools": None, # all tools except delegate_task
        "system_prompt": (
            "You are a coding sub-agent. Your job is to implement a specific change.\n"
            "- You are an explicit opt-in writer; expect the parent agent to synthesize final decisions\n"
            "- Read relevant files before editing\n"
            "- Make minimal, focused changes; do not refactor surrounding code\n"
            "- Verify your changes compile/lint if possible\n"
            "- Prefer edit_file over write_file for existing files\n"
        ),
    },
    "test": {
        "allowed_tools": {
            "read_file", "glob_files", "grep_files", "list_directory",
            "bash", "run_tests", "run_affected_tests", "git_status",
            "git_diff", "diff_files", "format_and_lint",
        },
        "system_prompt": (
            "You are a test sub-agent. Your job is to run tests and report results.\n"
            "- Run the relevant test suite for the project\n"
            "- Analyze failures and provide concise diagnostics\n"
            "- Do NOT fix code; just report what's broken and why\n"
        ),
    },
    "review": {
        "allowed_tools": {
            "read_file", "glob_files", "grep_files", "list_directory",
            "git_status", "git_diff", "git_log", "git_status_diff",
            "diff_files", "dependency_inspect",
        },
        "system_prompt": (
            "You are a clean-context code review sub-agent. Your job is to review changes from the diff outward.\n"
            "- Assume no prior conversation context; rediscover only needed files\n"
            "- Check for logic bugs, missed edge cases, security issues, and test gaps\n"
            "- Provide specific, actionable feedback with file:line references\n"
            "- Prefer JSON-lines findings or a tight findings-first list; no broad summary unless no issues\n"
            "- Do NOT modify any files\n"
        ),
    },
    "advisor": {
        "allowed_tools": {
            "read_file", "glob_files", "grep_files", "list_directory",
            "git_status", "git_diff", "git_log", "git_status_diff",
            "diff_files", "dependency_inspect", "semantic_search",
            "process_logs",
        },
        "system_prompt": (
            "You are a smart-friend advisor sub-agent. Your job is to improve the parent agent's judgment without writing code.\n"
            "- Return a short plan, risk critique, or missing-context request; do not produce patches\n"
            "- Look beyond the exact question when a hidden blocker or cheaper path is likely\n"
            "- If required context is absent, name the file/command the parent should inspect and stop\n"
            "- Keep output under 8 bullets unless asked otherwise\n"
            "- Do NOT modify any files or run destructive commands\n"
        ),
    },
}


class SubAgent:
    """Lightweight in-process sub-agent wrapping a fresh provider conversation."""

    def __init__(
        self,
        parent_core: Any, # PoorCLICore (avoid circular import)
        max_iterations: int = 10,
        timeout: float = 120.0,
        allowed_tools: Optional[set] = None,
        denied_tools: Optional[set] = None,
        archetype: str = "generic",
        communication_mode: str = "text",
        agent_definition: Optional[AgentDefinition] = None,
    ):
        self._parent = parent_core
        self._agent_definition = agent_definition
        self._archetype = f"agent:{agent_definition.name}" if agent_definition else archetype
        if communication_mode not in ("text", "latent"):
            raise ValueError("communication_mode must be 'text' or 'latent'")
        self._communication_mode = communication_mode
        self._hard_denied_tools = {"delegate_task", "spawn_parallel_agents"}
        arch_cfg = _ARCHETYPE_CONFIGS.get(archetype, {})
        if agent_definition is not None:
            available = [
                str(declaration.get("name", ""))
                for declaration in parent_core.tool_registry.get_tool_declarations()
                if isinstance(declaration, dict)
            ]
            self._allowed_tools = effective_allowed_tools(agent_definition, available)
        elif archetype != "generic" and arch_cfg.get("allowed_tools") is not None:
            self._allowed_tools = set(arch_cfg["allowed_tools"])
        else:
            self._allowed_tools = set(allowed_tools) if allowed_tools is not None else None
        agentic_cfg = getattr(parent_core.config, "agentic", None) if parent_core.config else None
        max_depth = getattr(agentic_cfg, "sub_agent_max_depth", 2) if agentic_cfg else 2
        cfg_max_iter = getattr(agentic_cfg, "sub_agent_max_iterations", 10) if agentic_cfg else 10
        self._max_iterations = min(max_iterations, cfg_max_iter, 25)
        self._timeout = getattr(agentic_cfg, "sub_agent_timeout", timeout) if agentic_cfg else timeout
        default_denied = set() if agent_definition is not None else set(
            getattr(agentic_cfg, "sub_agent_default_denied_tools", []) if agentic_cfg else []
        )
        explicit_denied = set(denied_tools or set())
        if agent_definition is not None:
            explicit_denied |= set(agent_definition.denied_tools)
        self._denied_tools = default_denied | explicit_denied | self._hard_denied_tools
        self._max_input_tokens = int(getattr(agentic_cfg, "sub_agent_max_input_tokens", 0) or 0)
        cfg_max_output = int(getattr(agentic_cfg, "sub_agent_max_output_tokens", 0) or 0)
        if agent_definition is not None:
            cfg_max_output = min(cfg_max_output or agent_definition.max_output_tokens, agent_definition.max_output_tokens)
        self._max_output_tokens = cfg_max_output
        self._max_cost_usd = float(getattr(agentic_cfg, "sub_agent_max_cost_usd", 0.0) or 0.0)
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._estimated_cost_usd: float = 0.0
        self._depth = getattr(parent_core, "_sub_agent_depth", 0) + 1
        if self._depth > max_depth:
            raise RuntimeError(f"sub-agent recursion depth exceeded (max {max_depth})")

    def _resolve_filtered_tools(self) -> List[Dict[str, Any]]:
        tool_declarations = self._parent.tool_registry.get_tool_declarations()
        ordered = sorted(
            [dict(declaration) for declaration in tool_declarations if isinstance(declaration, dict)],
            key=lambda declaration: str(declaration.get("name", "")),
        )
        if self._allowed_tools is not None:
            return [
                declaration
                for declaration in ordered
                if str(declaration.get("name", "")) in self._allowed_tools
                and str(declaration.get("name", "")) not in self._denied_tools
            ]
        return [
            declaration
            for declaration in ordered
            if str(declaration.get("name", "")) not in self._denied_tools
        ]

    @staticmethod
    def _cancelled(cancel_event: Optional[Any]) -> bool:
        if cancel_event is None:
            return False
        is_set = getattr(cancel_event, "is_set", None)
        if callable(is_set):
            try:
                return bool(is_set())
            except Exception:
                return False
        return False

    def _budget_limit_message(self) -> str:
        if self._max_input_tokens > 0 and self._total_input_tokens >= self._max_input_tokens:
            return f"sub-agent input token budget reached ({self._total_input_tokens}/{self._max_input_tokens})"
        if self._max_output_tokens > 0 and self._total_output_tokens >= self._max_output_tokens:
            return f"sub-agent output token budget reached ({self._total_output_tokens}/{self._max_output_tokens})"
        if self._max_cost_usd > 0 and self._estimated_cost_usd >= self._max_cost_usd:
            return f"sub-agent cost budget reached (${self._estimated_cost_usd:.4f}/${self._max_cost_usd:.4f})"
        return ""

    def _recompute_estimated_cost(self) -> None:
        estimator = getattr(self._parent, "_estimate_cost", None)
        if callable(estimator):
            try:
                self._estimated_cost_usd = float(estimator(self._total_input_tokens, self._total_output_tokens) or 0.0)
                return
            except Exception:
                pass
        self._estimated_cost_usd = (self._total_input_tokens / 1000.0) * 0.0005 + (self._total_output_tokens / 1000.0) * 0.0015

    async def run(
        self,
        prompt: str,
        context_files: Optional[List[str]] = None,
        cancel_event: Optional[Any] = None,
    ) -> str:
        """Run sub-agent and return final text response."""
        subagent_id = f"subagent-{uuid.uuid4().hex[:8]}"
        started = time.monotonic()
        parent_request_id = str(getattr(self._parent, "_active_request_id", "") or "")
        hook_manager = getattr(self._parent, "_hook_manager", None)
        emit_policy_hook_nowait(
            hook_manager,
            "subagent_start",
            {
                "subagentId": subagent_id,
                "archetype": self._archetype,
                "parentRequestId": parent_request_id,
            },
        )
        status = "completed"
        if self._cancelled(cancel_event):
            status = "cancelled"
            emit_policy_hook_nowait(
                hook_manager,
                "subagent_stop",
                {
                    "subagentId": subagent_id,
                    "archetype": self._archetype,
                    "parentRequestId": parent_request_id,
                    "status": status,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )
            return "[sub-agent cancelled before start]"
        from .providers.provider_factory import ProviderFactory
        config = self._parent.config
        provider_name = self._agent_definition.provider if self._agent_definition and self._agent_definition.provider else config.model.provider
        model_name = self._agent_definition.model if self._agent_definition and self._agent_definition.model else config.model.model_name
        api_key = self._parent._config_manager.get_api_key(provider_name)
        provider_config = self._parent._config_manager.get_provider_config(provider_name)
        extra_kwargs: Dict[str, Any] = {}
        if provider_config and provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url
        if provider_name in ("anthropic", "claude"):
            extra_kwargs["prompt_caching"] = getattr(config.model, "prompt_caching", True)
        provider = ProviderFactory.create(
            provider_name=provider_name,
            api_key=api_key or "",
            model_name=model_name,
            **extra_kwargs,
        )
        filtered_tools = self._resolve_filtered_tools()
        system_instruction = self._build_system_instruction(filtered_tools)
        ctx_parts = []
        if context_files:
            for fp in context_files[:10]:
                try:
                    from pathlib import Path
                    content = Path(fp).read_text(encoding="utf-8", errors="ignore")[:8000]
                    ctx_parts.append(f"[File: {fp}]\n{content}")
                except Exception:
                    ctx_parts.append(f"[File: {fp}] (unreadable)")
        full_prompt = "\n\n".join(ctx_parts) + f"\n\n{prompt}" if ctx_parts else prompt

        async def _run_impl() -> str:
            if self._communication_mode == "latent" and not filtered_tools:
                from .latent_channel import LatentChannel
                channel = LatentChannel(provider, config)
                if channel.available():
                    try:
                        await provider.initialize(tools=None, system_instruction=system_instruction)
                        text, bench = await channel.run(full_prompt)
                        self._total_input_tokens += getattr(bench, "input_tokens", 0) or 0
                        self._total_output_tokens += getattr(bench, "output_tokens", 0) or 0
                        self._recompute_estimated_cost()
                        limit = self._budget_limit_message()
                        if limit:
                            return f"{text.strip()}\n[{limit}]"
                        return text.strip() or "(no response from latent sub-agent)"
                    except Exception as e:
                        logger.warning("latent sub-agent failed; falling back to text: %s", e)
                else:
                    logger.info("latent channel unavailable; falling back to text")
            elif self._communication_mode == "latent" and filtered_tools:
                logger.info("latent sub-agent requested with tools; falling back to text")

            await provider.initialize(tools=filtered_tools, system_instruction=system_instruction)
            accumulated = ""
            iteration = 0
            async for chunk in provider.send_message_stream(full_prompt):
                if self._cancelled(cancel_event):
                    return (accumulated + "\n[sub-agent cancelled]").strip()
                self._accumulate_usage(chunk)
                limit = self._budget_limit_message()
                if limit:
                    return (accumulated + f"\n[{limit}]").strip()
                if chunk.content:
                    accumulated += chunk.content
                if not chunk.function_calls:
                    continue
                tool_results = []
                for fc in chunk.function_calls:
                    if self._cancelled(cancel_event):
                        return (accumulated + "\n[sub-agent cancelled]").strip()
                    try:
                        result = await self._parent.tool_registry.execute_tool(fc.name, fc.arguments)
                    except Exception as e:
                        result = f"error: {e}"
                    tool_results.append({"id": fc.id, "result": result})
                formatted = provider.format_tool_results(tool_results)
                response = None
                async for next_chunk in provider.send_message_stream(formatted):
                    if self._cancelled(cancel_event):
                        return (accumulated + "\n[sub-agent cancelled]").strip()
                    self._accumulate_usage(next_chunk)
                    limit = self._budget_limit_message()
                    if limit:
                        return (accumulated + f"\n[{limit}]").strip()
                    if next_chunk.content:
                        accumulated += next_chunk.content
                    if next_chunk.function_calls:
                        response = next_chunk
                while response and response.function_calls:
                    iteration += 1
                    if iteration >= self._max_iterations:
                        return (accumulated + "\n[sub-agent iteration cap reached]").strip()
                    tool_results = []
                    for fc in response.function_calls:
                        if self._cancelled(cancel_event):
                            return (accumulated + "\n[sub-agent cancelled]").strip()
                        try:
                            result = await self._parent.tool_registry.execute_tool(fc.name, fc.arguments)
                        except Exception as e:
                            result = f"error: {e}"
                        tool_results.append({"id": fc.id, "result": result})
                    formatted = provider.format_tool_results(tool_results)
                    response = None
                    async for next_chunk in provider.send_message_stream(formatted):
                        if self._cancelled(cancel_event):
                            return (accumulated + "\n[sub-agent cancelled]").strip()
                        self._accumulate_usage(next_chunk)
                        limit = self._budget_limit_message()
                        if limit:
                            return (accumulated + f"\n[{limit}]").strip()
                        if next_chunk.content:
                            accumulated += next_chunk.content
                        if next_chunk.function_calls:
                            response = next_chunk
            return accumulated.strip() or "(no response from sub-agent)"

        try:
            text = await asyncio.wait_for(_run_impl(), timeout=max(1.0, float(self._timeout)))
        except asyncio.TimeoutError:
            status = "timeout"
            text = "[sub-agent timed out]"
        except Exception as e:
            status = "error"
            logger.error("sub-agent error: %s", e, exc_info=True)
            text = f"[sub-agent error: {e}]"
        if text.startswith("[sub-agent cancelled"):
            status = "cancelled"
        if self._total_input_tokens or self._total_output_tokens:
            text += (
                f"\n[sub-agent tokens: {self._total_input_tokens}in/{self._total_output_tokens}out]"
                f"\n[sub-agent est_cost_usd: {self._estimated_cost_usd:.6f}]"
            )
        emit_policy_hook_nowait(
            hook_manager,
            "subagent_stop",
            {
                "subagentId": subagent_id,
                "archetype": self._archetype,
                "parentRequestId": parent_request_id,
                "status": status,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return text.strip() or "(no response from sub-agent)"

    def _build_system_instruction(self, filtered_tools: List[Dict[str, Any]]) -> str:
        """Build system instruction based on archetype and available tools."""
        arch_cfg = _ARCHETYPE_CONFIGS.get(self._archetype, {})
        arch_prompt = self._agent_definition.system_prompt if self._agent_definition else arch_cfg.get("system_prompt", "")
        sandbox_preset = getattr(self._parent, "_sandbox_preset", "workspace-write")
        tool_names = sorted(t.get("name", "") for t in filtered_tools)
        parts = [
            f"You are a {self._archetype} sub-agent within a larger coding assistant.",
            "",
        ]
        if arch_prompt:
            parts.append(arch_prompt)
        parts.extend([
            "## Constraints",
            f"- Sandbox: {sandbox_preset} (do not attempt operations beyond this scope)",
            "- Do not delegate further sub-tasks",
            "- The parent agent is the coordinator and default single writer",
            "- Stay focused on the specific task; do not refactor surrounding code",
            "- Prefer reading files before editing them",
            "- For bash commands: use short, targeted commands; avoid destructive operations",
            "",
            f"## Available tools\n{', '.join(tool_names)}",
        ])
        return "\n".join(parts)

    def _accumulate_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self._total_input_tokens += getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
        self._total_output_tokens += getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
        self._recompute_estimated_cost()

    def get_usage(self) -> Dict[str, Any]:
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "estimated_cost_usd": round(float(self._estimated_cost_usd), 8),
        }
