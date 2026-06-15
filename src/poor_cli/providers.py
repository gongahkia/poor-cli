from __future__ import annotations

import hashlib
import json
import time
import urllib.error
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, cast

from .config import ConfigError, load_config
from .cost import BudgetLedger
from .extensions import ExtensionLoadError, load_entry_point_values
from .hooks import Hook, HookManager
from .offline import require_online
from .store import RunStore


class ProviderReplayMiss(RuntimeError):
    pass


class ProviderLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 0
    initial_seconds: float = 1.0
    max_seconds: float = 8.0


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    model: str
    prompt: str
    system_prompt: str = ""
    messages: list[dict[str, Any]] | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def request_hash(self) -> str:
        return hashlib.sha256(_stable_json(asdict(self)).encode()).hexdigest()


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    model: str
    content: str
    raw: dict[str, Any] = field(default_factory=dict)
    cached: bool = False


class Provider(Protocol):
    def call(self, request: ProviderRequest) -> ProviderResponse: ...


class BatchProvider(Provider, Protocol):
    def call_many(self, requests: list[ProviderRequest]) -> list[ProviderResponse]: ...


class CachedReplayProvider:
    def __init__(
        self,
        store: RunStore,
        run_id: str,
        wrapped: Provider | None = None,
        replay_only: bool = False,
        hooks: Iterable[Hook] | HookManager | None = None,
    ):
        self.store = store
        self.run_id = run_id
        self.wrapped = wrapped
        self.replay_only = replay_only
        self.hooks = hooks if isinstance(hooks, HookManager) else HookManager.from_hooks(hooks)

    def call(self, request: ProviderRequest) -> ProviderResponse:
        request_hash = request.request_hash()
        cached = self._cached_response(request_hash)
        if cached is not None:
            return self._cache_hit(request, request_hash, cached)

        self.store.append_event(
            self.run_id,
            "provider.cache_miss",
            {"provider": request.provider, "model": request.model, "request_hash": request_hash},
        )
        if self.replay_only or self.wrapped is None:
            raise ProviderReplayMiss(f"missing cached provider response: {request_hash}")
        require_online(f"provider {request.provider}")

        request_artifact = self._start_live_request(request, request_hash)
        self.hooks.before_model_call(
            {"run_id": self.run_id, "provider": request.provider, "model": request.model, "request_hash": request_hash}
        )
        started = time.monotonic()
        response = replace(self._call_with_retries(request), cached=False)
        return self._complete_live_request(request, request_hash, request_artifact.artifact_id, response, time.monotonic() - started)

    def call_many(self, requests: Iterable[ProviderRequest]) -> list[ProviderResponse]:
        request_list = list(requests)
        responses: list[ProviderResponse | None] = [None] * len(request_list)
        misses: list[tuple[int, ProviderRequest, str]] = []
        for index, request in enumerate(request_list):
            request_hash = request.request_hash()
            cached = self._cached_response(request_hash)
            if cached is not None:
                responses[index] = self._cache_hit(request, request_hash, cached)
                continue
            self.store.append_event(
                self.run_id,
                "provider.cache_miss",
                {"provider": request.provider, "model": request.model, "request_hash": request_hash},
            )
            misses.append((index, request, request_hash))
        if not misses:
            return cast(list[ProviderResponse], responses)
        if self.replay_only or self.wrapped is None:
            raise ProviderReplayMiss(f"missing cached provider response: {misses[0][2]}")
        require_online("provider batch")

        request_artifacts: dict[int, str] = {}
        for index, request, request_hash in misses:
            request_artifacts[index] = self._start_live_request(request, request_hash).artifact_id
            self.hooks.before_model_call(
                {"run_id": self.run_id, "provider": request.provider, "model": request.model, "request_hash": request_hash}
            )
        self.store.append_event(
            self.run_id,
            "provider.batch.started",
            {"request_hashes": [request_hash for _, _, request_hash in misses], "miss_count": len(misses)},
        )
        live_requests = [request for _, request, _ in misses]
        if hasattr(self.wrapped, "call_many"):
            live_responses = cast(BatchProvider, self.wrapped).call_many(live_requests)
        else:
            live_responses = [self._call_with_retries(request) for request in live_requests]
        if len(live_responses) != len(misses):
            raise RuntimeError("batch provider returned wrong response count")
        for (index, request, request_hash), response in zip(misses, live_responses, strict=True):
            live = replace(response, cached=False)
            responses[index] = self._complete_live_request(request, request_hash, request_artifacts[index], live, 0.0)
        self.store.append_event(
            self.run_id,
            "provider.batch.completed",
            {"request_hashes": [request_hash for _, _, request_hash in misses], "miss_count": len(misses)},
        )
        return cast(list[ProviderResponse], responses)

    def _cache_hit(self, request: ProviderRequest, request_hash: str, cached: ProviderResponse) -> ProviderResponse:
        self.store.append_event(
            self.run_id,
            "provider.cache_hit",
            {"provider": request.provider, "model": request.model, "request_hash": request_hash},
        )
        BudgetLedger.load(self.store, self.run_id).record_provider_response(request, request_hash, cached, cached_response=True)
        return replace(cached, cached=True)

    def _start_live_request(self, request: ProviderRequest, request_hash: str) -> Any:
        BudgetLedger.load(self.store, self.run_id).check_provider_request(request, request_hash)
        request_artifact = self.store.put_artifact(run_id=self.run_id, kind="provider.request", data=asdict(request))
        self.store.append_event(
            self.run_id,
            "provider.call.started",
            {
                "provider": request.provider,
                "model": request.model,
                "request_hash": request_hash,
                "artifact_id": request_artifact.artifact_id,
            },
        )
        return request_artifact

    def _complete_live_request(
        self, request: ProviderRequest, request_hash: str, request_artifact_id: str, response: ProviderResponse, latency_seconds: float
    ) -> ProviderResponse:
        response_artifact = self.store.put_artifact(
            run_id=self.run_id,
            kind="provider.response",
            data={
                "request_hash": request_hash,
                "request": asdict(request),
                "response": asdict(response),
                "latency_seconds": round(latency_seconds, 3),
            },
        )
        self.store.append_event(
            self.run_id,
            "provider.call.completed",
            {
                "provider": response.provider,
                "model": response.model,
                "request_hash": request_hash,
                "artifact_id": response_artifact.artifact_id,
                "request_artifact_id": request_artifact_id,
                "latency_seconds": round(latency_seconds, 3),
            },
        )
        BudgetLedger.load(self.store, self.run_id).record_provider_response(request, request_hash, response, cached_response=False)
        return response

    def _call_with_retries(self, request: ProviderRequest) -> ProviderResponse:
        if self.wrapped is None:
            raise ProviderReplayMiss("missing wrapped provider")
        policy = _retry_policy(self.store, self.run_id, request)
        delay = max(0.0, policy.initial_seconds)
        attempt = 0
        while True:
            try:
                return self.wrapped.call(request)
            except Exception as exc:
                retryable = _retryable_provider_error(exc)
                if not retryable or attempt >= policy.max_retries:
                    raise
                attempt += 1
                status = _error_status(exc)
                self.store.append_event(
                    self.run_id,
                    "provider.rate_limited" if status == 429 else "provider.retryable_error",
                    {
                        "provider": request.provider,
                        "model": request.model,
                        "attempt": attempt,
                        "status": status,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                self.store.append_event(
                    self.run_id,
                    "provider.backoff",
                    {"provider": request.provider, "model": request.model, "attempt": attempt, "seconds": round(delay, 3)},
                )
                if delay:
                    time.sleep(delay)
                self.store.append_event(
                    self.run_id,
                    "provider.retry",
                    {"provider": request.provider, "model": request.model, "attempt": attempt},
                )
                delay = min(policy.max_seconds, delay * 2 if delay else 0.0)

    def _cached_response(self, request_hash: str) -> ProviderResponse | None:
        for artifact in reversed(self.store.list_artifacts(self.run_id, "provider.response")):
            payload = json.loads(self.store.artifact_payload(str(artifact["artifact_id"])))
            if payload.get("request_hash") != request_hash:
                continue
            response = payload.get("response")
            if not isinstance(response, dict):
                continue
            raw = response.get("raw")
            return ProviderResponse(
                provider=str(response.get("provider") or ""),
                model=str(response.get("model") or ""),
                content=str(response.get("content") or ""),
                raw=raw if isinstance(raw, dict) else {},
                cached=bool(response.get("cached")),
            )
        return None


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _retry_policy(store: RunStore, run_id: str, request: ProviderRequest) -> RetryPolicy:
    run = store.get_run(run_id)
    try:
        config = load_config(Path(str(run.get("repo_path") or ".")))
    except ConfigError:
        config = {}
    limits: dict[str, Any] = {}
    for profile in (config.get("providers") or {}).values():
        if not isinstance(profile, dict) or str(profile.get("kind") or "") != request.provider:
            continue
        models = profile.get("models")
        if isinstance(models, list) and request.model not in {str(item) for item in models}:
            continue
        raw_limits = profile.get("limits")
        limits = raw_limits if isinstance(raw_limits, dict) else {}
        break
    return RetryPolicy(
        max_retries=max(0, int(limits.get("max_retries") or 0)),
        initial_seconds=max(0.0, float(limits.get("backoff_initial_seconds") or 1.0)),
        max_seconds=max(0.0, float(limits.get("backoff_max_seconds") or 8.0)),
    )


def _retryable_provider_error(exc: Exception) -> bool:
    status = _error_status(exc)
    if status is not None:
        return status in {408, 409, 429} or 500 <= status <= 599
    return isinstance(exc, TimeoutError | urllib.error.URLError | OSError)


def _error_status(exc: Exception) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status", None) or getattr(exc, "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def load_provider_entry_points(group: str = "poor_cli.providers") -> dict[str, Provider]:
    providers: dict[str, Provider] = {}
    try:
        values = load_entry_point_values(group)
    except ExtensionLoadError as exc:
        raise ProviderLoadError(str(exc)) from exc
    for name, value in values:
        provider = value() if isinstance(value, type) else value
        if not hasattr(provider, "call"):
            raise ProviderLoadError(f"provider entry point {name} has no call method")
        providers[name] = provider
    return providers
