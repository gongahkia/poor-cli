from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from poor_cli.store import RunStore

from .builtin import builtin_tools


class ToolError(RuntimeError):
    pass


class ToolNotFound(ToolError):
    pass


class ToolReplayMiss(ToolError):
    pass


@dataclass(frozen=True)
class ToolRequest:
    name: str
    args: dict[str, Any] = field(default_factory=dict)

    def request_hash(self) -> str:
        return hashlib.sha256(_stable_json(asdict(self)).encode()).hexdigest()


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    output: Any = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    cached: bool = False


ToolFn = Callable[[dict[str, Any]], ToolResult]


class ToolDispatcher:
    def __init__(
        self,
        store: RunStore,
        run_id: str,
        *,
        workdir: Path | None = None,
        tools: dict[str, ToolFn] | None = None,
        replay_only: bool = False,
    ):
        self.store = store
        self.run_id = run_id
        self.workdir = (workdir or Path.cwd()).resolve()
        self.tools = tools if tools is not None else builtin_tools(self.workdir)
        self.replay_only = replay_only

    def call(self, name: str, args: dict[str, Any] | None = None, task_id: str | None = None) -> ToolResult:
        request = ToolRequest(name=name, args=args or {})
        request_hash = request.request_hash()
        cached = self._cached_result(request_hash)
        if cached is not None:
            self.store.append_event(self.run_id, "tool.cache_hit", {"tool": name, "request_hash": request_hash}, task_id)
            return replace(cached, cached=True)

        self.store.append_event(self.run_id, "tool.cache_miss", {"tool": name, "request_hash": request_hash}, task_id)
        if self.replay_only:
            raise ToolReplayMiss(f"missing cached tool result: {request_hash}")
        if name not in self.tools:
            self.store.append_event(
                self.run_id,
                "tool.call.failed",
                {"tool": name, "request_hash": request_hash, "error": "not found"},
                task_id,
            )
            raise ToolNotFound(f"unknown tool: {name}")

        request_artifact = self.store.put_artifact(run_id=self.run_id, task_id=task_id, kind="tool.request", data=asdict(request))
        self.store.append_event(
            self.run_id,
            "tool.call.started",
            {"tool": name, "request_hash": request_hash, "artifact_id": request_artifact.artifact_id},
            task_id,
        )
        try:
            result = replace(self.tools[name](request.args), cached=False)
        except Exception as exc:
            result = ToolResult(name=name, ok=False, error=str(exc))
        result_artifact = self.store.put_artifact(
            run_id=self.run_id,
            task_id=task_id,
            kind="tool.result",
            data={"request_hash": request_hash, "request": asdict(request), "result": asdict(result)},
        )
        event_type = "tool.call.completed" if result.ok else "tool.call.failed"
        self.store.append_event(
            self.run_id,
            event_type,
            {"tool": name, "request_hash": request_hash, "artifact_id": result_artifact.artifact_id, "ok": result.ok},
            task_id,
        )
        return result

    def _cached_result(self, request_hash: str) -> ToolResult | None:
        for artifact in reversed(self.store.list_artifacts(self.run_id, "tool.result")):
            payload = json.loads(self.store.artifact_payload(str(artifact["artifact_id"])))
            if payload.get("request_hash") != request_hash:
                continue
            result = payload.get("result")
            if not isinstance(result, dict):
                continue
            return ToolResult(
                name=str(result.get("name") or ""),
                ok=bool(result.get("ok")),
                output=result.get("output"),
                error=str(result["error"]) if result.get("error") is not None else None,
                raw=result.get("raw") if isinstance(result.get("raw"), dict) else {},
                cached=bool(result.get("cached")),
            )
        return None


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
