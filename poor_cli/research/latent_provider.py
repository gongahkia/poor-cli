"""LatentProvider abstraction — uniform interface across in-process + bridged backends.

Today there are two distinct ways to do latent-space hand-off:
- ``research/latent_communication.py`` — in-process Transformers (HF Local).
- ``research/latent_bridge.py`` — network bridge to a patched local server (vLLM, ...).

This module unifies them behind one ``LatentProvider`` interface so the agent
loop, sub_agent.py, parallel_agents.py, and any future caller can use latent
mode without branching on backend type.

Capability surface:
- ``encode(prompt) -> LatentMessage`` — produce hidden state + KV cache.
- ``generate_from_latent(latent_msg) -> str`` — finish to text.
- ``compatible_with(other) -> bool`` — same model/tokenizer guarantee.

Backend dispatch:
- ``InProcessLatentProvider`` wraps a LatentAgent (HF Local).
- ``BridgeLatentProvider`` wraps a LatentBackend (vLLM, etc.).
- ``build_latent_provider(config)`` chooses the right one given config.

Both halves are thin glue — the heavy lifting lives in the underlying modules.
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
# Bridged implementation (vLLM / SGLang / future)
# ──────────────────────────────────────────────────────────────────────────

class BridgeLatentProvider:
    """Wraps a LatentBackend for network-boundary inference servers."""

    def __init__(self, backend: Any):
        self._backend = backend
        cfg = getattr(backend, "config", None)
        self.spec = LatentSpec(
            backend=str(getattr(backend, "backend_name", "unknown")),
            model_id=str(getattr(cfg, "model_id", "") or "unknown"),
            hidden_dim=int(getattr(cfg, "hidden_dim", 0) or 0),
            dtype=str(getattr(cfg, "dtype", "") or ""),
            transport="http",
            extra={"server_version": str(getattr(cfg, "server_version", "") or "")},
        )

    async def encode(self, prompt: str) -> Any:
        return await self._backend.encode(prompt)

    async def generate_from_latent(self, latent_msg: Any, *, max_new_tokens: int = 512) -> str:
        result = await self._backend.generate_from_latent(latent_msg, max_new_tokens=max_new_tokens)
        return getattr(result, "text", "") or ""

    def compatible_with(self, other: "LatentProvider") -> bool:
        return _spec_compatible(self.spec, other.spec)


# ──────────────────────────────────────────────────────────────────────────
# Compatibility check
# ──────────────────────────────────────────────────────────────────────────

def _spec_compatible(a: LatentSpec, b: LatentSpec) -> bool:
    """Two providers are compatible when model + dtype + hidden_dim agree.

    Backend / transport may differ (in-process can pair with bridged on the
    same model). The actual KV-tensor cross-runtime feasibility is checked at
    transfer time by latent_bridge.compatibility_check.
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
    backend_obj: Optional[Any] = None,
) -> LatentProvider:
    """Construct the appropriate provider for a given backend.

    - ``backend == "hf_local"``: pass ``agent=<LatentAgent>``.
    - other backends: pass ``backend_obj=<LatentBackend>``.

    Raises ValueError when arguments don't match the chosen backend.
    """
    name = (backend or "").strip().lower()
    if name == "hf_local":
        if agent is None:
            raise ValueError("hf_local backend requires `agent=<LatentAgent>`")
        return InProcessLatentProvider(agent)
    if backend_obj is None:
        raise ValueError(f"backend '{backend}' requires `backend_obj=<LatentBackend>`")
    return BridgeLatentProvider(backend_obj)
