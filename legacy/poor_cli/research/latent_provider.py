"""LatentProvider abstraction for implemented in-process latent backends.

Today poor-cli only ships in-process latent hand-off:
- ``research/latent_communication.py`` — in-process Transformers (HF Local).

This module unifies them behind one ``LatentProvider`` interface so the agent
loop, sub_agent.py, parallel_agents.py, and any future caller can use the
implemented latent mode without branching on backend type.

Capability surface:
- ``encode(prompt) -> LatentMessage`` — produce hidden state + KV cache.
- ``generate_from_latent(latent_msg) -> str`` — finish to text.
- ``compatible_with(other) -> bool`` — same model/tokenizer guarantee.

Backend dispatch:
- ``InProcessLatentProvider`` wraps a LatentAgent (HF Local).
- ``build_latent_provider(config)`` chooses the right one given config.

This is thin glue; the heavy lifting lives in the underlying module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from ..exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class LatentSpec:
    """Identity of the latent capability — used for compatibility checks."""
    backend: str            # "hf_local" | "vllm" | "sglang" | ...
    model_id: str
    hidden_dim: int
    dtype: str
    transport: str          # "in_process" | "http"
    extra: dict


class LatentProvider(Protocol):
    """Uniform latent-mode provider interface."""

    spec: LatentSpec

    async def encode(self, prompt: str) -> Any:
        """Run architect forward pass, return latent message."""

    async def generate_from_latent(self, latent_msg: Any, *, max_new_tokens: int = 512) -> str:
        """Finish the latent message into text."""

    def compatible_with(self, other: "LatentProvider") -> bool:
        """Return True when two providers share model + tokenizer + dtype."""


# ──────────────────────────────────────────────────────────────────────────
# In-process implementation (HF Local)
# ──────────────────────────────────────────────────────────────────────────

class InProcessLatentProvider:
    """Wraps a LatentAgent for the HF Local backend."""

    def __init__(self, agent: Any):
        self._agent = agent
        model = getattr(agent, "model", None)
        cfg = getattr(model, "config", None) if model is not None else None
        hidden_dim = int(getattr(cfg, "hidden_size", 0) or 0)
        dtype = str(getattr(model, "dtype", "")) if model is not None else ""
        self.spec = LatentSpec(
            backend="hf_local",
            model_id=str(getattr(cfg, "_name_or_path", "") or "unknown"),
            hidden_dim=hidden_dim,
            dtype=dtype,
            transport="in_process",
            extra={},
        )

    async def encode(self, prompt: str) -> Any:
        from .latent_communication import LatentAgent  # noqa: F401 — type hint only
        return self._agent.encode(prompt)

    async def generate_from_latent(self, latent_msg: Any, *, max_new_tokens: int = 512) -> str:
        return self._agent.decode_from_latent(latent_msg, max_new_tokens=max_new_tokens)

    def compatible_with(self, other: "LatentProvider") -> bool:
        return _spec_compatible(self.spec, other.spec)


# ──────────────────────────────────────────────────────────────────────────
# Compatibility check
# ──────────────────────────────────────────────────────────────────────────

def _spec_compatible(a: LatentSpec, b: LatentSpec) -> bool:
    """Two providers are compatible when model + dtype + hidden_dim agree.

    Backend / transport may differ in future implementations; currently only
    HF Local in-process transport is supported.
    """
    if a.model_id != b.model_id and a.model_id != "unknown" and b.model_id != "unknown":
        return False
    if a.dtype != b.dtype and a.dtype and b.dtype:
        return False
    if a.hidden_dim and b.hidden_dim and a.hidden_dim != b.hidden_dim:
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────

def build_latent_provider(
    *,
    backend: str,
    agent: Optional[Any] = None,
) -> LatentProvider:
    """Construct the appropriate provider for a given backend.

    - ``backend == "hf_local"``: pass ``agent=<LatentAgent>``.

    Raises ValueError when arguments don't match the chosen backend.
    """
    name = (backend or "").strip().lower()
    if name == "hf_local":
        if agent is None:
            raise ValueError("hf_local backend requires `agent=<LatentAgent>`")
        return InProcessLatentProvider(agent)
    raise ValueError(f"latent backend '{backend}' is not implemented")
