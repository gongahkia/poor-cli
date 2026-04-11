"""Speculative decoding integration for local inference (vLLM).

Pairs small draft models with main models to accelerate generation.
Only works with self-hosted inference — closed API providers are unaffected.
Ollama lacks native speculative decoding support; this is vLLM-only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)

# main model -> draft model
DRAFT_MODEL_PAIRS: Dict[str, str] = {
    "llama3.1:70b": "llama3.1:8b",
    "llama3.1:70b-instruct": "llama3.1:8b-instruct",
    "llama3.3:70b": "llama3.3:8b",
    "qwen2.5-coder:32b": "qwen2.5-coder:1.5b",
    "qwen2.5-coder:32b-instruct": "qwen2.5-coder:1.5b-instruct",
    "qwen2.5:72b": "qwen2.5:7b",
    "codellama:34b": "codellama:7b",
    "deepseek-coder-v2:33b": "deepseek-coder-v2:7b",
    "deepseek-coder-v2:236b": "deepseek-coder-v2:16b",
    "mistral-large:123b": "mistral:7b",
    "mixtral:8x22b": "mistral:7b",
}

LOCAL_PROVIDERS = {"ollama", "vllm"} # providers considered "local inference"


def resolve_draft_model(main_model: str) -> Optional[str]:
    """Look up draft model for a given main model.

    Returns None if no pairing exists.
    """
    if main_model in DRAFT_MODEL_PAIRS:
        return DRAFT_MODEL_PAIRS[main_model]
    normalized = main_model.lower().strip()
    for key, val in DRAFT_MODEL_PAIRS.items():
        if key.lower() == normalized:
            return val
    return None


def is_local_provider(provider_name: str) -> bool:
    """Check if provider is self-hosted / local inference."""
    return provider_name.lower() in LOCAL_PROVIDERS


def is_spec_decode_available(provider_name: str, backend: str = "vllm") -> bool:
    """Speculative decoding is only available on vLLM backend."""
    return is_local_provider(provider_name) and backend.lower() == "vllm"


@dataclass
class SpeculativeMetrics:
    """Track speculative decoding acceptance rate and speedup."""
    total_draft_tokens: int = 0
    accepted_tokens: int = 0
    rejected_tokens: int = 0
    total_requests: int = 0
    total_time_saved_ms: float = 0.0
    _start_times: Dict[str, float] = field(default_factory=dict, repr=False)

    @property
    def acceptance_rate(self) -> float:
        if self.total_draft_tokens == 0:
            return 0.0
        return self.accepted_tokens / self.total_draft_tokens

    @property
    def speedup_factor(self) -> float:
        """Theoretical speedup based on acceptance rate and speculative window."""
        k = 5 # num_speculative_tokens default
        if self.total_draft_tokens == 0:
            return 1.0
        return k * self.acceptance_rate + 1

    def record(self, draft_tokens: int, accepted: int) -> None:
        """Record one speculative decoding batch result."""
        self.total_draft_tokens += draft_tokens
        self.accepted_tokens += accepted
        self.rejected_tokens += (draft_tokens - accepted)
        self.total_requests += 1

    def start_request(self, request_id: str) -> None:
        self._start_times[request_id] = time.monotonic()

    def end_request(self, request_id: str, baseline_ms: float = 0.0) -> None:
        start = self._start_times.pop(request_id, None)
        if start is not None and baseline_ms > 0:
            elapsed_ms = (time.monotonic() - start) * 1000
            self.total_time_saved_ms += max(0, baseline_ms - elapsed_ms)

    def summary(self) -> Dict[str, Any]:
        return {
            "total_draft_tokens": self.total_draft_tokens,
            "accepted_tokens": self.accepted_tokens,
            "rejected_tokens": self.rejected_tokens,
            "acceptance_rate": round(self.acceptance_rate, 4),
            "speedup_factor": round(self.speedup_factor, 2),
            "total_requests": self.total_requests,
            "total_time_saved_ms": round(self.total_time_saved_ms, 1),
        }

    def reset(self) -> None:
        self.total_draft_tokens = 0
        self.accepted_tokens = 0
        self.rejected_tokens = 0
        self.total_requests = 0
        self.total_time_saved_ms = 0.0
        self._start_times.clear()


# module-level singleton
_metrics = SpeculativeMetrics()

def get_metrics() -> SpeculativeMetrics:
    return _metrics


def build_vllm_launch_args(
    main_model: str,
    draft_model: Optional[str] = None,
    num_speculative_tokens: int = 5,
) -> List[str]:
    """Build vLLM server launch CLI args for speculative decoding.

    Returns list of extra args to append to `vllm serve <model>`.
    """
    resolved = draft_model or resolve_draft_model(main_model)
    if resolved is None:
        logger.warning("no draft model found for %s — spec decode disabled", main_model)
        return []
    return [
        "--speculative-model", resolved,
        "--num-speculative-tokens", str(num_speculative_tokens),
    ]


def vllm_launch_command(
    main_model: str,
    draft_model: Optional[str] = None,
    num_speculative_tokens: int = 5,
    host: str = "0.0.0.0",
    port: int = 8000,
) -> str:
    """Return full vLLM serve command string with spec decode enabled."""
    extra = build_vllm_launch_args(main_model, draft_model, num_speculative_tokens)
    if not extra:
        return f"vllm serve {main_model} --host {host} --port {port}"
    return f"vllm serve {main_model} --host {host} --port {port} {' '.join(extra)}"


@dataclass
class SpeculativeDecodingManager:
    """Manages speculative decoding config and metrics for a session."""
    enabled: bool = False
    backend: str = "vllm"
    main_model: str = ""
    draft_model: str = "" # resolved draft model name
    num_speculative_tokens: int = 5
    metrics: SpeculativeMetrics = field(default_factory=lambda: get_metrics())

    @classmethod
    def from_config(cls, config: Any, provider_name: str, model_name: str) -> "SpeculativeDecodingManager":
        """Create manager from Config object, respecting feature gate."""
        sd_cfg = getattr(config, "speculative_decoding", None)
        if sd_cfg is None or not sd_cfg.enabled:
            return cls(enabled=False, main_model=model_name)
        if not is_spec_decode_available(provider_name, sd_cfg.backend):
            logger.info("spec decode not available for provider=%s backend=%s", provider_name, sd_cfg.backend)
            return cls(enabled=False, main_model=model_name)
        draft = sd_cfg.draft_model
        if draft == "auto":
            draft = resolve_draft_model(model_name) or ""
        if not draft:
            logger.warning("no draft model for %s — spec decode disabled", model_name)
            return cls(enabled=False, main_model=model_name)
        logger.info("speculative decoding enabled: %s -> %s (k=%d)", model_name, draft, sd_cfg.num_speculative_tokens)
        return cls(
            enabled=True,
            backend=sd_cfg.backend,
            main_model=model_name,
            draft_model=draft,
            num_speculative_tokens=sd_cfg.num_speculative_tokens,
        )

    def get_launch_command(self, host: str = "0.0.0.0", port: int = 8000) -> str:
        """Get vLLM launch command with spec decode args."""
        if not self.enabled:
            return ""
        return vllm_launch_command(
            self.main_model,
            self.draft_model,
            self.num_speculative_tokens,
            host,
            port,
        )

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "main_model": self.main_model,
            "draft_model": self.draft_model,
            "num_speculative_tokens": self.num_speculative_tokens,
            "metrics": self.metrics.summary() if self.enabled else {},
        }
