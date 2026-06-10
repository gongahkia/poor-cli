"""Single source of truth for token counts across poor-cli.

Every token count anywhere in the codebase must route through this module.
See PRD 001 for rationale and the invariant tests rely on.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Protocol, Tuple

ProviderId = Literal["anthropic", "openai", "gemini", "ollama", "openrouter", "hf_local", "vllm", "llama_server", "sglang", "hf_tgi", "lmstudio"]

CountSource = Literal["native", "tiktoken", "heuristic"]


# ── calibration table ────────────────────────────────────────────────────
# chars per token, calibrated against empirical samples (code-heavy + prose).
# Keyed by (provider, model); "*" means "any model for that provider".
# This is a measurement, not a preference — do not move to config.
HEURISTIC_CHARS_PER_TOKEN: Dict[Tuple[Optional[str], str], float] = {
    ("anthropic", "*"):            3.5,
    ("openai",    "gpt-5.1"):      3.7,
    ("openai",    "gpt-5-mini"):   3.7,
    ("openai",    "*"):            3.8,
    ("gemini",    "*"):            3.6,
    ("openrouter","*"):            3.7,
    ("ollama",    "*"):            3.9,
    ("hf_local",  "*"):            3.9,
    ("vllm",      "*"):            3.9,
    ("llama_server", "*"):         3.9,
    ("sglang",    "*"):            3.9,
    ("hf_tgi",    "*"):            3.9,
    ("lmstudio",  "*"):            3.9,
    (None,        "*"):            3.8,  # last-resort fallback
}


def _lookup_ratio(provider: Optional[str], model: Optional[str]) -> float:
    """Resolve (provider, model) -> chars_per_token via the calibration table."""
    prov = (provider or "").lower() or None
    mod = model or ""
    if prov is not None and mod:
        ratio = HEURISTIC_CHARS_PER_TOKEN.get((prov, mod))
        if ratio is not None:
            return ratio
    if prov is not None:
        ratio = HEURISTIC_CHARS_PER_TOKEN.get((prov, "*"))
        if ratio is not None:
            return ratio
    return HEURISTIC_CHARS_PER_TOKEN[(None, "*")]


# ── data shapes ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TokenCount:
    """A token count plus the calibration source that produced it."""
    count: int
    source: CountSource
    provider: Optional[str] = None
    model: Optional[str] = None


class CountBackend(Protocol):
    """Counts tokens for a single provider. Implemented by provider adapters."""

    def count(self, text: str, *, model: Optional[str] = None) -> int: ...


# ── the counter ──────────────────────────────────────────────────────────

class TokenCounter:
    """
    Single source of truth for token counts.

    Resolution order per (provider, model):
      1. Registered native backend for that provider (if any).
      2. tiktoken for OpenAI-compatible providers (if tiktoken importable).
      3. Calibrated heuristic fallback via HEURISTIC_CHARS_PER_TOKEN.

    Thread-safe. Caches tiktoken encodings keyed by model.
    """

    def __init__(
        self,
        *,
        native_backends: Optional[Dict[str, CountBackend]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._native: Dict[str, CountBackend] = dict(native_backends or {})
        self._tiktoken_cache: Dict[str, Any] = {}
        self._tiktoken_disabled = False

    # ── registration ────────────────────────────────────────────────────

    def register_backend(self, provider: str, backend: CountBackend) -> None:
        with self._lock:
            self._native[str(provider).lower()] = backend

    def unregister_backend(self, provider: str) -> None:
        with self._lock:
            self._native.pop(str(provider).lower(), None)

    # ── core counting ───────────────────────────────────────────────────

    def count(
        self,
        text: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> TokenCount:
        text = text or ""
        prov = (provider or "").lower() or None

        if prov is not None:
            with self._lock:
                backend = self._native.get(prov)
            if backend is not None:
                try:
                    n = int(backend.count(text, model=model))
                    return TokenCount(count=max(0, n), source="native",
                                      provider=prov, model=model)
                except Exception:
                    # fall through to other strategies
                    pass

        if prov in ("openai", "openrouter", "vllm", "llama_server", "sglang", "hf_tgi", "lmstudio") and text:
            tik = self._tiktoken_count(text, model=model)
            if tik is not None:
                return TokenCount(count=tik, source="tiktoken",
                                  provider=prov, model=model)

        return self._heuristic(text, provider=prov, model=model)

    def approx_chars_for_tokens(
        self,
        tokens: int,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> int:
        """Approximate number of characters that fit in `tokens` tokens.

        Inverse of the heuristic count — used by truncation call sites that
        previously multiplied by a chars-per-token constant.
        """
        if tokens <= 0:
            return 0
        ratio = _lookup_ratio((provider or "").lower() or None, model)
        return max(1, int(tokens * ratio))

    async def acount(
        self,
        text: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> TokenCount:
        # Current backends are synchronous; async form provided for future
        # provider SDKs (e.g. Gemini's async count_tokens). The call itself
        # delegates to `count` so we do not have to re-implement strategy
        # selection twice.
        return self.count(text, provider=provider, model=model)

    def count_messages(
        self,
        messages: Iterable[Dict[str, Any]],
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> TokenCount:
        total = 0
        source: CountSource = "heuristic"
        first = True
        for msg in messages or ():
            content = msg.get("content") if isinstance(msg, dict) else str(msg)
            text = _stringify_content(content)
            if not text:
                continue
            tc = self.count(text, provider=provider, model=model)
            total += tc.count
            if first:
                source = tc.source
                first = False
        return TokenCount(count=total, source=source, provider=(provider or "").lower() or None, model=model)

    def reserve(
        self,
        *,
        budget: int,
        for_parts: Dict[str, str],
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Distribute `budget` tokens across `for_parts` in proportion to each
        part's counted size. Sum of returned values <= budget.
        """
        if budget <= 0 or not for_parts:
            return {name: 0 for name in for_parts}
        counts: Dict[str, int] = {}
        total = 0
        for name, text in for_parts.items():
            c = self.count(text or "", provider=provider, model=model).count
            counts[name] = c
            total += c
        if total <= budget:
            return counts
        scale = budget / float(total)
        scaled = {name: int(c * scale) for name, c in counts.items()}
        # ensure sum does not exceed budget (integer rounding should not over-commit here)
        assigned = sum(scaled.values())
        if assigned > budget:
            # trim from largest part
            largest = max(scaled, key=lambda k: scaled[k])
            scaled[largest] -= (assigned - budget)
            scaled[largest] = max(0, scaled[largest])
        return scaled

    # ── strategies ──────────────────────────────────────────────────────

    def _heuristic(
        self,
        text: str,
        *,
        provider: Optional[str],
        model: Optional[str],
    ) -> TokenCount:
        if not text:
            return TokenCount(count=0, source="heuristic", provider=provider, model=model)
        ratio = _lookup_ratio(provider, model)
        count = max(1, int(len(text) / ratio))
        return TokenCount(count=count, source="heuristic", provider=provider, model=model)

    def _tiktoken_count(self, text: str, *, model: Optional[str]) -> Optional[int]:
        if self._tiktoken_disabled:
            return None
        try:
            import tiktoken  # type: ignore
        except Exception:
            self._tiktoken_disabled = True
            return None
        key = (model or "cl100k_base")
        with self._lock:
            enc = self._tiktoken_cache.get(key)
            if enc is None:
                try:
                    if model:
                        try:
                            enc = tiktoken.encoding_for_model(model)
                        except Exception:
                            enc = tiktoken.get_encoding("cl100k_base")
                    else:
                        enc = tiktoken.get_encoding("cl100k_base")
                except Exception:
                    return None
                self._tiktoken_cache[key] = enc
        try:
            return len(enc.encode(text))
        except Exception:
            return None


# ── message-content stringification ─────────────────────────────────────

def _stringify_content(content: Any) -> str:
    """Flatten provider-shaped content (str, list-of-parts, dict) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return str(content.get("text", "")) or str(content)
    return str(content)


# ── module-level singleton ──────────────────────────────────────────────

_GLOBAL_COUNTER: Optional[TokenCounter] = None
_GLOBAL_LOCK = threading.Lock()


def get_token_counter() -> TokenCounter:
    """Return the process-wide TokenCounter, creating it on first call."""
    global _GLOBAL_COUNTER
    if _GLOBAL_COUNTER is None:
        with _GLOBAL_LOCK:
            if _GLOBAL_COUNTER is None:
                _GLOBAL_COUNTER = TokenCounter()
    return _GLOBAL_COUNTER


def set_token_counter(tc: Optional[TokenCounter]) -> None:
    """Replace the process-wide counter. Primarily for tests."""
    global _GLOBAL_COUNTER
    with _GLOBAL_LOCK:
        _GLOBAL_COUNTER = tc


# ── convenience helpers (keep call sites terse) ─────────────────────────

def count_text(
    text: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> int:
    """Shortcut: return just the integer count for the given text."""
    return get_token_counter().count(text, provider=provider, model=model).count
