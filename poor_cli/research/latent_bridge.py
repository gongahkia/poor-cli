"""M5 custom latent bridge for local inference servers — research prototype.

The existing `research/latent_communication.py` does in-process hidden-state
passing with HF Transformers. That doesn't generalize: vLLM, SGLang, HF TGI,
llama-server, LM Studio, Ollama are NETWORK services behind OpenAI-compatible
REST APIs — their hidden states never escape the server process.

This module is a feasibility study + architectural skeleton for bridging
latent state between agents running on a local inference server. It does NOT
run out of the box — shipping real latent hand-off over a network requires
a server-side extension (documented below) that is out of scope to install
by default.

Deliverables per M5:
1. ``LatentBackend`` — abstract interface for per-backend latent bridges.
2. ``VLLMLatentBackend`` — concrete stub targeting vLLM (most likely-feasible
   backend because it already exposes an OpenAI-compatible streaming surface
   and has internal KV-cache APIs exposed via the Python client).
3. ``LatentBridgeConfig`` — shared config: model_id, tokenizer_id,
   embedding_dim, dtype, device-topology metadata.
4. ``LatentTensorSpec`` — the on-wire tensor format we would use.
5. ``compatibility_check`` — same-model / same-tokenizer / same-embedding-space
   assertions before any transfer.
6. A reference FastAPI extension spec (see ``docs/M5_LATENT_BRIDGE.md``).
7. Benchmarks harness (stub) for text vs latent.

Shipping blockers (documented for follow-up):
- vLLM's PagedAttention uses block-indexed KV cache. Extracting the KV
  blocks belonging to a specific request requires a server-side patch that
  exposes the request's ``past_key_values`` tensor.
- Cross-process tensor transfer needs a serialization format. We use
  safetensors over HTTP with a shared dtype/shape header.
- Latent-space compatibility requires architectural identity (same model +
  same tokenizer + same weights). ``compatibility_check`` enforces this.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..exceptions import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Tensor on-wire spec
# ---------------------------------------------------------------------------

@dataclass
class LatentTensorSpec:
    """Wire format for a latent tensor passed between agents.

    Shape + dtype + endianness + checksum live in the header so a receiver
    can validate before memory allocation. Payload is raw bytes; the sender
    is responsible for safe serialization (safetensors or torch.save).

    For a hidden-state batch the canonical shape is ``[1, seq, hidden_dim]``.
    For a KV cache the shape is a list of
    ``[num_layers, 2 (K/V), batch, heads, seq, head_dim]`` layer entries.
    """
    name: str                         # "hidden_states" | "kv_cache" | "inputs_embeds"
    dtype: str                        # "bfloat16" | "float16" | "float32"
    shape: List[int]
    byte_order: str = "little"
    checksum: str = ""                # sha256 hex of payload
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_header(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "byte_order": self.byte_order,
            "checksum": self.checksum,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_header(cls, data: Dict[str, Any]) -> "LatentTensorSpec":
        return cls(
            name=str(data.get("name", "")),
            dtype=str(data.get("dtype", "float32")),
            shape=[int(s) for s in data.get("shape", [])],
            byte_order=str(data.get("byte_order", "little")),
            checksum=str(data.get("checksum", "")),
            metadata=dict(data.get("metadata", {})),
        )

    def verify_checksum(self, payload: bytes) -> bool:
        if not self.checksum:
            return True  # no checksum = no assertion
        return hashlib.sha256(payload).hexdigest() == self.checksum

    @staticmethod
    def compute_checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Compatibility check
# ---------------------------------------------------------------------------

@dataclass
class LatentBridgeConfig:
    """Shared configuration across bridge endpoints.

    Both the architect and editor endpoints must agree on every field before
    any latent transfer. Mismatches abort the transfer (not fall back to text;
    that's the caller's choice).
    """
    model_id: str                    # e.g. "Qwen/Qwen2.5-7B"
    tokenizer_id: str                # usually equal to model_id
    hidden_dim: int                  # transformer hidden size
    num_layers: int                  # depth (for KV cache shape)
    num_heads: int                   # attention heads
    head_dim: int                    # hidden_dim / num_heads
    dtype: str                       # "bfloat16" recommended
    vocab_size: int                  # for embedding-space identity
    backend: str                     # "vllm" | "sglang" | "hf_tgi" | "ollama" | "hf_local"
    server_version: str = ""         # for protocol-level compat pin
    extra: Dict[str, Any] = field(default_factory=dict)

    def identity_hash(self) -> str:
        """Canonical identity hash — architect/editor must match exactly."""
        payload = json.dumps(
            {
                "model_id": self.model_id,
                "tokenizer_id": self.tokenizer_id,
                "hidden_dim": self.hidden_dim,
                "num_layers": self.num_layers,
                "num_heads": self.num_heads,
                "head_dim": self.head_dim,
                "dtype": self.dtype,
                "vocab_size": self.vocab_size,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class LatentIncompatibility(RuntimeError):
    """Raised when architect + editor bridge configs disagree."""


def compatibility_check(architect: LatentBridgeConfig, editor: LatentBridgeConfig) -> List[str]:
    """Return empty list when compatible, else a list of mismatch reasons."""
    mismatches: List[str] = []
    if architect.model_id != editor.model_id:
        mismatches.append(f"model_id: {architect.model_id} != {editor.model_id}")
    if architect.tokenizer_id != editor.tokenizer_id:
        mismatches.append(f"tokenizer_id: {architect.tokenizer_id} != {editor.tokenizer_id}")
    if architect.hidden_dim != editor.hidden_dim:
        mismatches.append(f"hidden_dim: {architect.hidden_dim} != {editor.hidden_dim}")
    if architect.num_layers != editor.num_layers:
        mismatches.append(f"num_layers: {architect.num_layers} != {editor.num_layers}")
    if architect.num_heads != editor.num_heads:
        mismatches.append(f"num_heads: {architect.num_heads} != {editor.num_heads}")
    if architect.head_dim != editor.head_dim:
        mismatches.append(f"head_dim: {architect.head_dim} != {editor.head_dim}")
    if architect.dtype != editor.dtype:
        mismatches.append(f"dtype: {architect.dtype} != {editor.dtype}")
    if architect.vocab_size != editor.vocab_size:
        mismatches.append(f"vocab_size: {architect.vocab_size} != {editor.vocab_size}")
    if architect.identity_hash() != editor.identity_hash():
        mismatches.append("identity_hash_mismatch")
    return mismatches


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------

@dataclass
class LatentEncodeResult:
    """Output of backend.encode — hidden state of the prompt."""
    hidden_states: LatentTensorSpec
    kv_cache: Optional[LatentTensorSpec] = None
    payload_bytes: bytes = b""       # raw tensor bytes
    prompt_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class LatentGenerateResult:
    """Output of backend.generate_from_latent — completed text + stats."""
    text: str = ""
    output_tokens: int = 0
    input_tokens_equivalent: int = 0  # tokens saved vs text round-trip
    latency_ms: float = 0.0


class LatentBackend:
    """Abstract interface for a per-backend latent bridge.

    Concrete implementations must provide:
    - ``config`` — LatentBridgeConfig describing the served model.
    - ``encode(prompt)`` — runs the architect forward pass, returns hidden state.
    - ``generate_from_latent(hidden_states, kv_cache)`` — feeds into editor.
    - ``health_check()`` — quick ping to verify the server exposes latent APIs.

    Every backend is an OPT-IN feature. The default OpenAI-compatible HTTP
    surface remains unchanged; latent endpoints live under a /latent/* prefix
    and must be explicitly enabled on the server.
    """

    backend_name: str = "abstract"

    def __init__(self, config: LatentBridgeConfig):
        self.config = config

    async def health_check(self) -> Dict[str, Any]:
        raise NotImplementedError

    async def encode(self, prompt: str, *, return_kv: bool = True) -> LatentEncodeResult:
        raise NotImplementedError

    async def generate_from_latent(
        self,
        encode_result: LatentEncodeResult,
        *,
        max_new_tokens: int = 512,
    ) -> LatentGenerateResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# vLLM backend — stub targeting the most feasible first implementation
# ---------------------------------------------------------------------------

class VLLMLatentBackend(LatentBackend):
    """vLLM-specific latent bridge.

    Requires a patched vLLM server that exposes:
    - ``POST /latent/encode``  — returns hidden_states + kv_cache (safetensors)
    - ``POST /latent/generate`` — accepts hidden_states + kv_cache + max_tokens

    Until the server-side patch lands, this backend's ``encode`` and
    ``generate_from_latent`` raise ``NotImplementedError`` with a user-facing
    message pointing to `docs/M5_LATENT_BRIDGE.md`.
    """

    backend_name = "vllm"

    def __init__(self, config: LatentBridgeConfig, *, base_url: str = "http://localhost:8000"):
        super().__init__(config)
        self.base_url = base_url.rstrip("/")

    async def health_check(self) -> Dict[str, Any]:
        """Check if the server has the /latent/* extension loaded."""
        try:
            import aiohttp  # type: ignore
        except ImportError:
            return {"available": False, "reason": "aiohttp missing"}
        url = f"{self.base_url}/latent/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {"available": True, **data}
                    return {"available": False, "reason": f"status={resp.status}"}
        except Exception as exc:
            return {"available": False, "reason": str(exc)}

    async def encode(self, prompt: str, *, return_kv: bool = True) -> LatentEncodeResult:
        raise NotImplementedError(
            "VLLMLatentBackend.encode requires a server-side extension. "
            "See docs/M5_LATENT_BRIDGE.md for the patch spec. This module ships "
            "the client protocol; the server patch is out of scope by default."
        )

    async def generate_from_latent(
        self,
        encode_result: LatentEncodeResult,
        *,
        max_new_tokens: int = 512,
    ) -> LatentGenerateResult:
        raise NotImplementedError(
            "VLLMLatentBackend.generate_from_latent requires the paired server-side "
            "extension. See docs/M5_LATENT_BRIDGE.md."
        )


# ---------------------------------------------------------------------------
# Benchmark harness (stub)
# ---------------------------------------------------------------------------

@dataclass
class LatentBenchmarkRun:
    mode: str                          # "latent" | "text"
    prompt_length_tokens: int
    output_length_tokens: int
    wall_time_ms: float
    network_bytes: int = 0
    backend: str = ""


def benchmark_note_for_backend(backend_name: str) -> str:
    """Return a user-facing feasibility note for the given backend."""
    notes = {
        "vllm": (
            "Most feasible v1 target. Requires a server-side patch exposing "
            "/latent/encode and /latent/generate endpoints that serialize "
            "hidden_states + KV cache as safetensors. Estimated effort: 1-2 "
            "weeks for the patch + integration tests. Quality/cost benefit "
            "must be measured before promoting to ProviderCapability."
        ),
        "sglang": (
            "Feasible. SGLang already has RadixAttention exposing prefix "
            "cache state. Extraction surface similar to vLLM; server patch "
            "size comparable."
        ),
        "hf_tgi": (
            "Uncertain. TGI exposes fewer KV cache internals; would require "
            "deeper server-side changes."
        ),
        "llama_server": (
            "Unlikely v1. llama.cpp's KV cache layout is different from "
            "transformers; tensor format would need translation."
        ),
        "ollama": (
            "Not recommended. Ollama wraps llama.cpp but does not expose KV "
            "cache APIs. Would require upstream llama.cpp + Ollama changes."
        ),
        "lmstudio": (
            "Not recommended. LM Studio is a GUI wrapper; no latent APIs "
            "planned as of this writing."
        ),
        "hf_local": (
            "Already shipped in-process via poor_cli/research/latent_communication.py. "
            "Network bridge is not needed when Transformers runs in the same "
            "Python process."
        ),
    }
    return notes.get(backend_name, "Backend feasibility unknown — contact maintainers.")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_BACKENDS: Dict[str, type] = {
    "vllm": VLLMLatentBackend,
}


def build_backend(backend: str, config: LatentBridgeConfig, **kwargs) -> LatentBackend:
    """Build the backend object for a given inference server type.

    Only ``vllm`` has a concrete (stub) adapter today. Other backends raise
    ``NotImplementedError`` with the feasibility note as the message so the
    caller knows exactly why it's not supported yet.
    """
    cls = _BACKENDS.get(backend.lower())
    if cls is None:
        raise NotImplementedError(
            f"No latent backend shipped for '{backend}'. "
            f"Feasibility: {benchmark_note_for_backend(backend)}"
        )
    return cls(config, **kwargs)


def supported_backends() -> List[str]:
    return list(_BACKENDS.keys())
