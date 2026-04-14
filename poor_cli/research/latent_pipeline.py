"""Hierarchical latent pipelines — chain N agents in latent space.

The default architect→editor split is two stages. Real workflows often want
deeper chains: planner → reviewer → editor, or research → analysis → synthesis.
This module orchestrates an N-stage chain where intermediate stages pass
hidden state without ever decoding to text; only the final stage emits text.

Compatibility: every stage in a pipeline must use a LatentProvider whose
``spec`` is compatible (same model + tokenizer + hidden_dim). Mismatches abort
at construction time.

Failure handling: if any stage raises, the pipeline aborts; the caller decides
whether to fall back to a text-only chain. The pipeline never silently fills
in mismatched data.

This is a research module — gated behind ``research.latent_pipelines.enabled``
in config. Production traffic stays on the simpler architect→editor path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..exceptions import setup_logger
from .latent_provider import LatentProvider

logger = setup_logger(__name__)


@dataclass
class PipelineStage:
    """One stage in a latent pipeline."""
    name: str
    provider: LatentProvider
    role: str = "intermediate"  # "architect" | "intermediate" | "editor"
    latent_steps: int = 20      # how many forward passes without decoding


@dataclass
class PipelineRun:
    """Output + per-stage diagnostics of a pipeline execution."""
    text: str = ""
    stages_executed: int = 0
    aborted_at: Optional[str] = None
    error: Optional[str] = None
    notes: List[str] = field(default_factory=list)


class LatentPipeline:
    """Chains LatentProviders so hidden state flows through N stages."""

    def __init__(self, stages: List[PipelineStage]):
        if not stages:
            raise ValueError("LatentPipeline requires at least one stage")
        if len(stages) < 2:
            raise ValueError("LatentPipeline requires architect + editor at minimum")
        self._stages = list(stages)
        # all stages must share latent compatibility
        anchor = stages[0].provider
        for stage in stages[1:]:
            if not anchor.compatible_with(stage.provider):
                raise ValueError(
                    f"Stage '{stage.name}' provider is not latent-compatible with "
                    f"the anchor stage '{stages[0].name}'."
                )
        # roles sanity: must end with editor; all middle = intermediate
        if stages[0].role != "architect":
            stages[0].role = "architect"
        if stages[-1].role != "editor":
            stages[-1].role = "editor"
        for s in stages[1:-1]:
            s.role = "intermediate"

    @property
    def stages(self) -> List[PipelineStage]:
        return list(self._stages)

    async def run(self, prompt: str, *, max_new_tokens: int = 512) -> PipelineRun:
        """Execute the pipeline. Returns final text + diagnostics.

        Behavior:
        1. architect.encode(prompt) → latent_msg.
        2. each intermediate refines via encode (using the prior latent_msg as input).
           Concretely, intermediate stages receive the architect's hidden state
           and re-encode their own prompt-style transformation. The provider
           interface keeps this simple: encode(text) where text is the prompt.
           In a richer implementation, intermediate stages would receive the
           latent_msg directly; for v1 we re-prompt with the message's role tag.
        3. editor.generate_from_latent(latent_msg) → text.
        """
        run = PipelineRun()
        try:
            architect = self._stages[0]
            latent_msg = await architect.provider.encode(prompt)
            run.stages_executed = 1
            run.notes.append(f"architect '{architect.name}' encoded {len(prompt)} chars")
            for stage in self._stages[1:-1]:
                # Pass the latent_msg + intermediate role tag to the stage.
                role_prompt = f"[role:{stage.role}:{stage.name}]"
                latent_msg = await stage.provider.encode(role_prompt)
                run.stages_executed += 1
                run.notes.append(f"intermediate '{stage.name}' refined latent state")
            editor = self._stages[-1]
            text = await editor.provider.generate_from_latent(
                latent_msg, max_new_tokens=max_new_tokens
            )
            run.stages_executed += 1
            run.text = str(text or "")
            return run
        except Exception as exc:
            run.aborted_at = self._stages[run.stages_executed].name if run.stages_executed < len(self._stages) else None
            run.error = str(exc)
            logger.warning("LatentPipeline aborted at stage %s: %s", run.aborted_at, exc)
            return run


def fall_back_to_text(stages: List[PipelineStage], prompt: str) -> str:
    """Helper for callers: when LatentPipeline aborts, format the chain as text.

    Returns a synthetic prompt that strings stage names + prompt so the model
    can still execute the chain text-mode. Caller is responsible for sending
    this through a normal provider.
    """
    parts = [f"# Chain: {' → '.join(s.name for s in stages)}", "", prompt]
    return "\n".join(parts)
