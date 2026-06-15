from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import ConfigError, load_config
from .store import RunStore

if TYPE_CHECKING:
    from .providers import ProviderRequest, ProviderResponse


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Price:
    input_per_million: float | None = None
    output_per_million: float | None = None
    cached_input_per_million: float | None = None
    web_per_call: float | None = None
    router_multiplier: float = 1.0
    currency: str = "USD"
    source_url: str = ""
    retrieved_at: str = "2026-06-15"


@dataclass(frozen=True)
class BudgetEntry:
    kind: str
    provider: str
    model: str
    request_hash: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    web_calls: int = 0
    estimated_usd: float | None = None
    known_pricing: bool = False
    cached_response: bool = False
    pricing_source: str = ""


@dataclass
class BudgetLedger:
    store: RunStore
    run_id: str
    budget: dict[str, Any]
    entries: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)

    @classmethod
    def load(cls, store: RunStore, run_id: str) -> BudgetLedger:
        budget = store.get_run(run_id).get("budget")
        ledger = cls(store, run_id, budget if isinstance(budget, dict) else {})
        artifact = _latest_artifact(store, run_id, "budget.ledger")
        if artifact is None:
            return ledger
        try:
            payload = json.loads(store.artifact_payload(str(artifact["artifact_id"])))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ledger
        ledger.entries = list(payload.get("entries") or [])
        ledger.warnings = list(payload.get("warnings") or [])
        return ledger

    def check_provider_request(self, request: ProviderRequest, request_hash: str) -> None:
        self._check_wall_time()
        input_tokens = estimate_request_tokens(request)
        self._check_limit("max_calls", len(self.entries) + 1, "call")
        self._check_limit("max_tokens", self.totals()["tokens"] + input_tokens, "token")
        price = price_for(self.store, self.run_id, request.provider, request.model)
        estimated = estimate_cost(input_tokens, 0, 0, 0, price)
        if self.budget.get("strict_pricing") and estimated is None and self.budget.get("max_usd") is not None:
            self._exceeded("strict_pricing", f"unknown pricing for {request.provider}:{request.model}")
        if estimated is not None and self.budget.get("max_usd") is not None and self.totals()["estimated_usd"] + estimated > float(self.budget["max_usd"]):
            self._exceeded("max_usd", f"estimated provider call would exceed ${self.budget['max_usd']}")
        if estimated is None and self.budget.get("max_usd") is not None:
            self._warning("unknown_pricing", f"unknown pricing for {request.provider}:{request.model}", 0)

    def record_provider_response(
        self, request: ProviderRequest, request_hash: str, response: ProviderResponse, *, cached_response: bool = False
    ) -> None:
        usage = usage_from_response(request, response)
        price = price_for(self.store, self.run_id, request.provider, request.model)
        estimated = 0.0 if cached_response else estimate_cost(
            usage["input_tokens"], usage["cached_input_tokens"], usage["output_tokens"], usage["web_calls"], price
        )
        entry = BudgetEntry(
            kind="provider",
            provider=request.provider,
            model=request.model,
            request_hash=request_hash,
            input_tokens=usage["input_tokens"],
            cached_input_tokens=usage["cached_input_tokens"],
            output_tokens=usage["output_tokens"],
            web_calls=usage["web_calls"],
            estimated_usd=estimated,
            known_pricing=estimated is not None,
            cached_response=cached_response,
            pricing_source=price.source_url,
        )
        self.entries.append(asdict(entry))
        self.store.append_event(self.run_id, "budget.entry", asdict(entry))
        self._threshold_warnings()
        self.write()

    def write(self) -> None:
        payload = {
            "schema_version": "poor-cli-budget-ledger-v1",
            "budget": self.budget,
            "totals": self.totals(),
            "warnings": self.warnings,
            "entries": self.entries,
        }
        _write_json_artifact(self.store, self.run_id, "budget/LEDGER.json", "budget.ledger", payload)

    def totals(self) -> dict[str, Any]:
        estimated = sum(float(entry["estimated_usd"]) for entry in self.entries if entry.get("estimated_usd") is not None)
        input_tokens = sum(int(entry.get("input_tokens") or 0) for entry in self.entries)
        cached = sum(int(entry.get("cached_input_tokens") or 0) for entry in self.entries)
        output = sum(int(entry.get("output_tokens") or 0) for entry in self.entries)
        return {
            "calls": len(self.entries),
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "output_tokens": output,
            "tokens": input_tokens + output,
            "estimated_usd": round(estimated, 8),
            "known_pricing": all(bool(entry.get("known_pricing")) for entry in self.entries) if self.entries else True,
        }

    def _threshold_warnings(self) -> None:
        totals = self.totals()
        checks = [
            ("max_usd", totals["estimated_usd"], "$"),
            ("max_calls", totals["calls"], "calls"),
            ("max_tokens", totals["tokens"], "tokens"),
        ]
        for key, used, unit in checks:
            limit = self.budget.get(key)
            if not isinstance(limit, int | float) or limit <= 0:
                continue
            for percent in (50, 80, 100):
                if used >= float(limit) * percent / 100:
                    self._warning(f"{key}_{percent}", f"budget {key} reached {percent}%: {used} {unit} of {limit}", percent)

    def _check_limit(self, key: str, used: int, label: str) -> None:
        limit = self.budget.get(key)
        if isinstance(limit, int | float) and limit > 0 and used > int(limit):
            self._exceeded(key, f"{label} budget exceeded: {used} > {limit}")

    def _check_wall_time(self) -> None:
        limit = self.budget.get("max_wall_seconds")
        if isinstance(limit, int | float) and limit > 0 and time.monotonic() - self.started_at > float(limit):
            self._exceeded("max_wall_seconds", f"wall-time budget exceeded: {limit}s")

    def _warning(self, code: str, message: str, threshold: int) -> None:
        if any(row.get("code") == code for row in self.warnings):
            return
        row = {"code": code, "message": message, "threshold": threshold}
        self.warnings.append(row)
        self.store.append_event(self.run_id, "budget.warning", row)

    def _exceeded(self, code: str, message: str) -> None:
        payload = {"code": code, "message": message}
        self.store.append_event(self.run_id, "budget.exceeded", payload)
        self.write()
        raise BudgetExceeded(message)


def estimate_request_tokens(request: ProviderRequest) -> int:
    return _token_estimate(
        json.dumps(
            {
                "prompt": request.prompt,
                "system_prompt": request.system_prompt,
                "messages": request.messages,
                "params": request.params,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )


def usage_from_response(request: ProviderRequest, response: ProviderResponse) -> dict[str, int]:
    raw_usage = response.raw.get("usage") if isinstance(response.raw, dict) else None
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _int(usage.get("input_tokens") or usage.get("prompt_tokens")) or estimate_request_tokens(request)
    output_tokens = _int(usage.get("output_tokens") or usage.get("completion_tokens")) or _token_estimate(response.content)
    details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    cached_tokens = _int(details.get("cached_tokens")) if isinstance(details, dict) else 0
    cached_tokens = cached_tokens or _int(usage.get("cache_read_input_tokens") or usage.get("cached_input_tokens"))
    return {"input_tokens": input_tokens, "cached_input_tokens": cached_tokens, "output_tokens": output_tokens, "web_calls": 0}


def estimate_cost(input_tokens: int, cached_input_tokens: int, output_tokens: int, web_calls: int, price: Price) -> float | None:
    if price.input_per_million is None or price.output_per_million is None:
        return None
    uncached = max(0, input_tokens - cached_input_tokens)
    cached_rate = price.cached_input_per_million if price.cached_input_per_million is not None else price.input_per_million
    total = uncached * price.input_per_million / 1_000_000
    total += cached_input_tokens * cached_rate / 1_000_000
    total += output_tokens * price.output_per_million / 1_000_000
    if price.web_per_call is not None:
        total += web_calls * price.web_per_call
    return round(total * price.router_multiplier, 8)


def price_for(store: RunStore, run_id: str, provider: str, model: str) -> Price:
    run = store.get_run(run_id)
    try:
        config = load_config(Path(str(run.get("repo_path") or ".")))
    except ConfigError:
        config = {}
    for profile in (config.get("providers") or {}).values():
        if not isinstance(profile, dict) or str(profile.get("kind") or "") != provider:
            continue
        models = profile.get("models")
        if isinstance(models, list) and model not in {str(item) for item in models}:
            continue
        cost = profile.get("cost")
        if isinstance(cost, dict):
            return Price(
                input_per_million=_float(cost.get("input_per_million")),
                output_per_million=_float(cost.get("output_per_million")),
                cached_input_per_million=_float(cost.get("cached_input_per_million") or cost.get("cached_per_million")),
                web_per_call=_float(cost.get("web_per_call")),
                currency=str(cost.get("currency") or "USD"),
                source_url=str(cost.get("source_url") or "config"),
                retrieved_at=str(cost.get("retrieved_at") or ""),
            )
    return _seed_price(provider, model)


def _seed_price(provider: str, model: str) -> Price:
    lowered = model.lower()
    if provider == "openai" and lowered.startswith("gpt-5.5"):
        return Price(2.50, 15.00, 0.25, source_url="https://developers.openai.com/api/docs/pricing")
    if provider == "anthropic" and "sonnet-4-6" in lowered:
        return Price(3.00, 15.00, 0.30, source_url="https://www.anthropic.com/claude/sonnet")
    if provider == "kimi" and "k2.7" in lowered:
        return Price(0.95, 4.00, 0.19, source_url="https://platform.kimi.ai/docs/pricing/chat-k27-code")
    if provider == "openrouter":
        return Price(source_url="https://openrouter.ai/pricing")
    return Price(source_url="unknown")


def _latest_artifact(store: RunStore, run_id: str, kind: str) -> dict[str, Any] | None:
    artifacts = store.list_artifacts(run_id, kind)
    return artifacts[-1] if artifacts else None


def _write_json_artifact(store: RunStore, run_id: str, relpath: str, kind: str, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = store.root / "runs" / run_id / "artifacts" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    store.put_artifact(run_id=run_id, kind=kind, data=text)


def _token_estimate(text: str) -> int:
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
