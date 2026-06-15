from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from .models import Budget
from .orchestrator import Orchestrator
from .replay import replay_summary, replay_verify
from .store import RunStore
from .swarm import run_swarm_plan


def serve_stdio(root: Path) -> int:
    server = RpcServer(root)
    for line in sys.stdin:
        server.handle(line)
    return 0


class RpcServer:
    def __init__(self, root: Path):
        self.root = root
        self.active: dict[str, threading.Event] = {}
        self.lock = threading.Lock()

    def handle(self, line: str) -> None:
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            self._send({"jsonrpc": "2.0", "id": None, "error": _err(-32700, "parse error")})
            return
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or "method" not in req:
            self._send({"jsonrpc": "2.0", "id": req.get("id") if isinstance(req, dict) else None, "error": _err(-32600, "invalid request")})
            return
        rid = req.get("id")
        try:
            raw_params = req.get("params")
            result = self._call(str(req["method"]), raw_params if isinstance(raw_params, dict) else {})
            if rid is not None:
                self._send({"jsonrpc": "2.0", "id": rid, "result": result})
        except KeyError:
            self._send({"jsonrpc": "2.0", "id": rid, "error": _err(-32601, "method not found")})
        except ValueError as exc:
            self._send({"jsonrpc": "2.0", "id": rid, "error": _err(-32602, str(exc))})
        except Exception as exc:
            self._send({"jsonrpc": "2.0", "id": rid, "error": _err(-32603, f"{type(exc).__name__}: {exc}")})

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "run":
            goal = str(params.get("goal") or "").strip()
            if not goal:
                raise ValueError("goal is required")
            budget = Budget(
                mode=str(params.get("mode") or "balanced"),
                max_usd=_float(params.get("budget")),
                max_parallel_agents=max(1, int(params.get("parallel") or 1)),
            )
            if params.get("swarm"):
                return self._start_swarm(goal, budget, params)
            store = RunStore(self.root)
            run_id, _ = Orchestrator(store).plan(goal, budget, graph_mode=bool(params.get("graph")))
            cancel = threading.Event()
            self.active[run_id] = cancel
            thread = threading.Thread(target=self._run, args=(run_id, budget, params, cancel), daemon=True)
            thread.start()
            return {"run_id": run_id, "status": "running"}
        if method == "inspect":
            store = RunStore(self.root)
            try:
                run_id = str(params.get("run_id") or "")
                return {"run": store.get_run(run_id), "tasks": store.list_tasks(run_id), "events": store.list_events(run_id)}
            finally:
                store.close()
        if method == "status":
            store = RunStore(self.root)
            try:
                run = store.get_run(str(params.get("run_id") or ""))
                return {"run_id": run["run_id"], "status": run["status"], "summary": run.get("final_summary") or ""}
            finally:
                store.close()
        if method == "cancel":
            run_id = str(params.get("run_id") or "")
            active_cancel = self.active.get(run_id)
            if active_cancel is None:
                return {"run_id": run_id, "cancelled": False, "reason": "not_active"}
            active_cancel.set()
            return {"run_id": run_id, "cancelled": True}
        if method == "replay":
            store = RunStore(self.root)
            try:
                run_id = str(params.get("run_id") or "")
                state = replay_summary(store, run_id, params.get("from_event"))
                if params.get("verify"):
                    state["verification"] = replay_verify(store, run_id)
                return state
            finally:
                store.close()
        raise KeyError(method)

    def _run(self, run_id: str, budget: Budget, params: dict[str, Any], cancel: threading.Event) -> None:
        store = RunStore(self.root)
        try:
            code = Orchestrator(store).run(
                run_id,
                budget,
                _selected(params),
                dry_run=bool(params.get("dry_run")),
                allow_overlap=bool(params.get("allow_overlap")),
                cancel=cancel,
            )
            self._events(store, run_id, code)
        finally:
            self.active.pop(run_id, None)
            store.close()

    def _start_swarm(self, goal: str, budget: Budget, params: dict[str, Any]) -> dict[str, Any]:
        store = RunStore(self.root)
        cancel = threading.Event()
        run_id, plan = Orchestrator(store).plan(goal, budget, graph_mode=bool(params.get("graph")))
        self.active[run_id] = cancel

        def target() -> None:
            try:
                result = run_swarm_plan(
                    store, run_id, plan.tasks, budget, selected_agents=_selected(params), allow_dirty=True, cancel=cancel
                )
                self._events(store, run_id, int(result["exit_code"]))
            finally:
                self.active.pop(run_id, None)
                store.close()

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return {"run_id": run_id, "status": "running"}

    def _events(self, store: RunStore, run_id: str, code: int) -> None:
        for event in store.list_events(run_id):
            self._send({"jsonrpc": "2.0", "method": "poor/event", "params": event})
        self._send({"jsonrpc": "2.0", "method": "poor/event", "params": {"run_id": run_id, "type": "rpc.run.finished", "exit_code": code}})

    def _send(self, payload: dict[str, Any]) -> None:
        with self.lock:
            sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def _err(code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _selected(params: dict[str, Any]) -> set[str] | None:
    raw = params.get("agents")
    if not raw:
        return None
    if isinstance(raw, list):
        return {str(item).strip() for item in raw if str(item).strip()}
    return {item.strip() for item in str(raw).split(",") if item.strip()}
