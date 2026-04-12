"""In-process sub-agent delegation for task decomposition."""

from __future__ import annotations
import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional
from .exceptions import setup_logger

logger = setup_logger(__name__)


class SubAgentArchetype(str, Enum):
    GENERIC = "generic"
    RESEARCH = "research" # read-only exploration
    CODE = "code" # full edit capabilities
    TEST = "test" # run tests + read
    REVIEW = "review" # read + git diff analysis

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
            "- Synthesize findings into a clear, structured summary\n"
            "- Do NOT modify any files or run destructive commands\n"
        ),
    },
    "code": {
        "allowed_tools": None, # all tools except delegate_task
        "system_prompt": (
            "You are a coding sub-agent. Your job is to implement a specific change.\n"
            "- Read relevant files before editing\n"
            "- Make minimal, focused changes — do not refactor surrounding code\n"
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
            "- Analyze failures and provide clear diagnostics\n"
            "- Do NOT fix code — just report what's broken and why\n"
        ),
    },
    "review": {
        "allowed_tools": {
            "read_file", "glob_files", "grep_files", "list_directory",
            "git_status", "git_diff", "git_log", "git_status_diff",
            "diff_files", "dependency_inspect",
        },
        "system_prompt": (
            "You are a code review sub-agent. Your job is to review changes.\n"
            "- Read the diff and relevant source files\n"
            "- Check for bugs, security issues, and style problems\n"
            "- Provide specific, actionable feedback with file:line references\n"
            "- Do NOT modify any files\n"
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
    ):
        self._parent = parent_core
        self._archetype = archetype
        arch_cfg = _ARCHETYPE_CONFIGS.get(archetype, {})
        if archetype != "generic" and arch_cfg.get("allowed_tools") is not None:
            self._allowed_tools = arch_cfg["allowed_tools"]
        else:
            self._allowed_tools = allowed_tools
        self._denied_tools = denied_tools or set()
        agentic_cfg = getattr(parent_core.config, "agentic", None) if parent_core.config else None
        max_depth = getattr(agentic_cfg, "sub_agent_max_depth", 2) if agentic_cfg else 2
        cfg_max_iter = getattr(agentic_cfg, "sub_agent_max_iterations", 10) if agentic_cfg else 10
        self._max_iterations = min(max_iterations, cfg_max_iter, 25)
        self._timeout = getattr(agentic_cfg, "sub_agent_timeout", timeout) if agentic_cfg else timeout
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._depth = getattr(parent_core, "_sub_agent_depth", 0) + 1
        if self._depth > max_depth:
            raise RuntimeError(f"sub-agent recursion depth exceeded (max {max_depth})")

    async def run(
        self,
        prompt: str,
        context_files: Optional[List[str]] = None,
    ) -> str:
        """Run sub-agent and return final text response."""
        from .providers.provider_factory import ProviderFactory
        config = self._parent.config
        api_key = self._parent._config_manager.get_api_key(config.model.provider)
        provider_config = self._parent._config_manager.get_provider_config(config.model.provider)
        extra_kwargs: Dict[str, Any] = {}
        if provider_config and provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url
        if config.model.provider in ("anthropic", "claude"):
            extra_kwargs["prompt_caching"] = getattr(config.model, "prompt_caching", True)
        provider = ProviderFactory.create(
            provider_name=config.model.provider,
            api_key=api_key or "",
            model_name=config.model.model_name,
            **extra_kwargs,
        )
        tool_declarations = self._parent.tool_registry.get_tool_declarations()
        denied = self._denied_tools | {"delegate_task"} # always prevent recursion
        if self._allowed_tools is not None:
            filtered_tools = [t for t in tool_declarations if t.get("name") in self._allowed_tools and t.get("name") not in denied]
        else:
            filtered_tools = [t for t in tool_declarations if t.get("name") not in denied]
        system_instruction = self._build_system_instruction(filtered_tools)
        await provider.initialize(tools=filtered_tools, system_instruction=system_instruction)
        # build context prefix
        ctx_parts = []
        if context_files:
            for fp in context_files[:10]: # cap files
                try:
                    from pathlib import Path
                    content = Path(fp).read_text(encoding="utf-8", errors="ignore")[:8000]
                    ctx_parts.append(f"[File: {fp}]\n{content}")
                except Exception:
                    ctx_parts.append(f"[File: {fp}] (unreadable)")
        full_prompt = prompt
        if ctx_parts:
            full_prompt = "\n\n".join(ctx_parts) + f"\n\n{prompt}"
        accumulated = ""
        iteration = 0
        try:
            async for chunk in provider.send_message_stream(full_prompt):
                self._accumulate_usage(chunk)
                if chunk.content:
                    accumulated += chunk.content
                if chunk.function_calls:
                    tool_results = []
                    for fc in chunk.function_calls:
                        try:
                            result = await self._parent.tool_registry.execute_tool(fc.name, fc.arguments)
                        except Exception as e:
                            result = f"error: {e}"
                        tool_results.append({"id": fc.id, "result": result})
                    formatted = provider.format_tool_results(tool_results)
                    response = None
                    async for next_chunk in provider.send_message_stream(formatted):
                        self._accumulate_usage(next_chunk)
                        if next_chunk.content:
                            accumulated += next_chunk.content
                        if next_chunk.function_calls:
                            response = next_chunk
                    while response and response.function_calls:
                        iteration += 1
                        if iteration >= self._max_iterations:
                            accumulated += "\n[sub-agent iteration cap reached]"
                            break
                        tool_results = []
                        for fc in response.function_calls:
                            try:
                                result = await self._parent.tool_registry.execute_tool(fc.name, fc.arguments)
                            except Exception as e:
                                result = f"error: {e}"
                            tool_results.append({"id": fc.id, "result": result})
                        formatted = provider.format_tool_results(tool_results)
                        response = None
                        async for next_chunk in provider.send_message_stream(formatted):
                            if next_chunk.content:
                                accumulated += next_chunk.content
                            if next_chunk.function_calls:
                                response = next_chunk
        except asyncio.TimeoutError:
            accumulated += "\n[sub-agent timed out]"
        except Exception as e:
            logger.error("sub-agent error: %s", e, exc_info=True)
            accumulated += f"\n[sub-agent error: {e}]"
        # append cost summary so parent can see sub-agent token usage
        if self._total_input_tokens or self._total_output_tokens:
            accumulated += f"\n[sub-agent tokens: {self._total_input_tokens}in/{self._total_output_tokens}out]"
        return accumulated.strip() or "(no response from sub-agent)"

    def _build_system_instruction(self, filtered_tools: List[Dict[str, Any]]) -> str:
        """Build system instruction based on archetype and available tools."""
        arch_cfg = _ARCHETYPE_CONFIGS.get(self._archetype, {})
        arch_prompt = arch_cfg.get("system_prompt", "")
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
            "- Stay focused on the specific task — do not refactor surrounding code",
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

    def get_usage(self) -> Dict[str, int]:
        return {"input_tokens": self._total_input_tokens, "output_tokens": self._total_output_tokens}
