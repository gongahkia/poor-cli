from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Protocol

from .extensions import ExtensionLoadError, load_entry_point_values
from .hooks import Hook, HookManager
from .offline import require_online
from .store import RunStore


class ProviderReplayMiss(RuntimeError):
    pass


class ProviderLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    model: str
    prompt: str
    system_prompt: str = ""
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
            self.store.append_event(
                self.run_id,
                "provider.cache_hit",
                {"provider": request.provider, "model": request.model, "request_hash": request_hash},
            )
            return replace(cached, cached=True)

        self.store.append_event(
            self.run_id,
            "provider.cache_miss",
            {"provider": request.provider, "model": request.model, "request_hash": request_hash},
        )
        if self.replay_only or self.wrapped is None:
            raise ProviderReplayMiss(f"missing cached provider response: {request_hash}")
        require_online(f"provider {request.provider}")

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
        self.hooks.before_model_call(
            {"run_id": self.run_id, "provider": request.provider, "model": request.model, "request_hash": request_hash}
        )
        response = replace(self.wrapped.call(request), cached=False)
        response_artifact = self.store.put_artifact(
            run_id=self.run_id,
            kind="provider.response",
            data={"request_hash": request_hash, "request": asdict(request), "response": asdict(response)},
        )
        self.store.append_event(
            self.run_id,
            "provider.call.completed",
            {
                "provider": response.provider,
                "model": response.model,
                "request_hash": request_hash,
                "artifact_id": response_artifact.artifact_id,
            },
        )
        return response

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
