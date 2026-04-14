"""
Parallel agent pool with git worktree isolation.

Runs multiple agents concurrently, each in its own worktree, then
collects and merges results. Integrates with AgentManager for lifecycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .agent_runner import AgentManager, AgentRecord
from .exceptions import setup_logger, ValidationError

logger = setup_logger(__name__)

DEFAULT_MAX_PARALLEL = 4
POLL_INTERVAL_SECONDS = 2


@dataclass
class SubTask:
    """A single sub-task within a parallel agent run."""
    prompt: str
    sandbox_preset: str = "workspace-write"
    max_runtime: int = 1800
    max_cost_usd: float = 2.0
    communication_mode: str = "text"

    def __post_init__(self) -> None:
        if self.communication_mode not in ("text", "latent"):
            raise ValidationError("communication_mode must be 'text' or 'latent'")


@dataclass
class ParallelRunResult:
    """Aggregated result of a parallel agent pool run."""
    agents: List[AgentRecord]
    results: Dict[str, str] # agent_id -> result text
    all_completed: bool
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agents": [a.to_dict() for a in self.agents],
            "results": self.results,
            "allCompleted": self.all_completed,
            "summary": self.summary,
        }


class ParallelAgentPool:
    """Orchestrates multiple isolated agents running in parallel."""

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
    ):
        self._mgr = AgentManager(repo_root)
        self._max_parallel = max_parallel

    async def run(
        self,
        tasks: Sequence[SubTask],
        source: str = "parallel-pool",
    ) -> ParallelRunResult:
        """
        Launch all sub-tasks as isolated agents and wait for completion.

        Each agent gets its own git worktree. Results are collected
        once all agents finish (or hit timeout/cost limits).
        """
        if len(tasks) > self._max_parallel:
            raise ValidationError(
                f"too many parallel tasks ({len(tasks)}); max is {self._max_parallel}"
            )

        # create and start all agents
        agents: List[AgentRecord] = []
        for task in tasks:
            try:
                agent = self._mgr.create_agent(
                    prompt=task.prompt,
                    sandbox_preset=task.sandbox_preset,
                    source=source,
                    use_worktree=True,
                    max_runtime=task.max_runtime,
                    max_cost_usd=task.max_cost_usd,
                    metadata={"communication_mode": task.communication_mode},
                    auto_start=True,
                )
                agents.append(agent)
                logger.info("launched parallel agent %s", agent.agent_id)
            except Exception as exc:
                logger.error("failed to create parallel agent: %s", exc)

        # poll until all agents are done
        agent_ids = [a.agent_id for a in agents]
        final_agents = await self._wait_for_completion(agent_ids)

        # collect results
        results: Dict[str, str] = {}
        for agent in final_agents:
            results[agent.agent_id] = self._mgr.get_result(agent.agent_id)

        all_completed = all(a.status == "completed" for a in final_agents)
        completed_count = sum(1 for a in final_agents if a.status == "completed")
        summary = f"{completed_count}/{len(final_agents)} agents completed"
        if any(task.communication_mode == "latent" for task in tasks):
            summary += "; latent requested, isolated worktree agents used text fallback"

        return ParallelRunResult(
            agents=final_agents,
            results=results,
            all_completed=all_completed,
            summary=summary,
        )

    async def _wait_for_completion(
        self,
        agent_ids: List[str],
        max_poll_time: int = 3600,
    ) -> List[AgentRecord]:
        """Poll agents until all reach a terminal state."""
        terminal = {"completed", "failed", "cancelled"}
        elapsed = 0
        while elapsed < max_poll_time:
            agents = [self._mgr.get_agent(aid) for aid in agent_ids]
            agents = [a for a in agents if a is not None]
            if all(a.status in terminal for a in agents):
                return agents
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
        # timeout: return current state
        return [a for a in (self._mgr.get_agent(aid) for aid in agent_ids) if a]

    def split_task(self, prompt: str, n: int = 2) -> List[SubTask]:
        """
        Naive task splitting — creates N copies of the prompt with scoping hints.

        For real decomposition, this should be done by the AI model. This is a
        utility for the simplest case where the user wants parallel exploration.
        """
        tasks = []
        for i in range(n):
            scoped = f"[Approach {i+1} of {n}] {prompt}"
            tasks.append(SubTask(prompt=scoped))
        return tasks

    def cleanup_all(self, agent_ids: List[str]) -> int:
        """Clean up worktrees for completed agents. Returns count cleaned."""
        cleaned = 0
        for aid in agent_ids:
            if self._mgr.cleanup_worktree(aid):
                cleaned += 1
        return cleaned
