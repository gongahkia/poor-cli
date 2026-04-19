"""Cross-tool capability graph for adaptive tool activation and ranking."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

GRAPH_FILENAME = "tool_capability_graph.json"
PERSIST_EVERY_N_UPDATES = 25
MAX_REQUEST_STATES = 256
MAX_PRODUCED_PATHS_PER_REQUEST = 200


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _edge_key(src: str, dst: str) -> str:
    return f"{src}\x1f{dst}"


def _clean_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return ""
    return os.path.normpath(text)


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


class ToolCapabilityGraph:
    """Thread-safe capability graph persisted to .poor-cli."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = Path(base_dir) if base_dir else Path.cwd() / ".poor-cli"
        self._path = self._base / GRAPH_FILENAME
        self._lock = threading.Lock()
        self._loaded = False
        self._updates_since_persist = 0
        self._payload: Dict[str, Any] = {
            "version": 1,
            "updated_at": "",
            "nodes": {},
            "edges": {},
            "group_edges": {},
        }
        self._request_state: Dict[str, Dict[str, Any]] = {}

    def load(self) -> None:
        self._loaded = True
        if not self._path.is_file():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("failed to load tool capability graph: %s", exc)
            return
        if not isinstance(payload, dict):
            return
        with self._lock:
            self._payload["version"] = int(payload.get("version", 1) or 1)
            self._payload["updated_at"] = str(payload.get("updated_at", "") or "")
            self._payload["nodes"] = payload.get("nodes", {}) if isinstance(payload.get("nodes"), dict) else {}
            self._payload["edges"] = payload.get("edges", {}) if isinstance(payload.get("edges"), dict) else {}
            self._payload["group_edges"] = (
                payload.get("group_edges", {})
                if isinstance(payload.get("group_edges"), dict)
                else {}
            )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _touch_locked(self) -> bool:
        self._payload["updated_at"] = _iso_now()
        self._updates_since_persist += 1
        if self._updates_since_persist >= PERSIST_EVERY_N_UPDATES:
            self._updates_since_persist = 0
            return True
        return False

    def persist(self) -> None:
        self._ensure_loaded()
        self._base.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "version": self._payload.get("version", 1),
                "updated_at": _iso_now(),
                "nodes": self._payload.get("nodes", {}),
                "edges": self._payload.get("edges", {}),
                "group_edges": self._payload.get("group_edges", {}),
            }
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self._base), suffix=".json.tmp")
            try:
                os.write(fd, json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
                os.fsync(fd)
                os.close(fd)
                os.replace(tmp, str(self._path))
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as exc:
            logger.warning("failed to persist tool capability graph: %s", exc)

    def _trim_request_state(self) -> None:
        if len(self._request_state) <= MAX_REQUEST_STATES:
            return
        keys = list(self._request_state.keys())
        for request_id in keys[: len(keys) - MAX_REQUEST_STATES]:
            self._request_state.pop(request_id, None)

    def _node(self, tool_name: str) -> Dict[str, Any]:
        nodes = self._payload["nodes"]
        node = nodes.get(tool_name)
        if not isinstance(node, dict):
            node = {
                "calls": 0,
                "success": 0,
                "failure": 0,
                "total_latency_ms": 0.0,
                "groups": {},
                "capabilities": {},
                "last_seen": "",
            }
            nodes[tool_name] = node
        return node

    def _edge(self, src: str, dst: str) -> Dict[str, Any]:
        edges = self._payload["edges"]
        key = _edge_key(src, dst)
        edge = edges.get(key)
        if not isinstance(edge, dict):
            edge = {
                "src": src,
                "dst": dst,
                "transitions": 0,
                "success": 0,
                "failure": 0,
                "total_latency_ms": 0.0,
                "file_flow": 0,
                "last_seen": "",
            }
            edges[key] = edge
        return edge

    def _group_edge(self, src: str, dst: str) -> Dict[str, Any]:
        group_edges = self._payload["group_edges"]
        key = _edge_key(src, dst)
        edge = group_edges.get(key)
        if not isinstance(edge, dict):
            edge = {
                "src": src,
                "dst": dst,
                "transitions": 0,
                "success": 0,
                "failure": 0,
                "total_latency_ms": 0.0,
                "last_seen": "",
            }
            group_edges[key] = edge
        return edge

    def observe_tool_call_start(
        self,
        *,
        request_id: str,
        call_id: str,
        tool_name: str,
        group: str = "",
        capabilities: Optional[Sequence[str]] = None,
        consumed_paths: Optional[Sequence[str]] = None,
    ) -> None:
        self._ensure_loaded()
        rid = str(request_id or "__direct__")
        cid = str(call_id or f"call:{time.time_ns()}")
        name = str(tool_name or "").strip()
        if not name:
            return
        group_name = str(group or "").strip()
        consumed = {_clean_path(path) for path in (consumed_paths or []) if _clean_path(path)}
        caps = _ordered_unique(capabilities or [])

        should_persist = False
        with self._lock:
            state = self._request_state.setdefault(
                rid,
                {
                    "last_call_id": "",
                    "calls": {},
                    "produced_paths": set(),
                },
            )
            calls = state.setdefault("calls", {})
            produced_paths = state.setdefault("produced_paths", set())
            if not isinstance(produced_paths, set):
                produced_paths = set(produced_paths)
                state["produced_paths"] = produced_paths

            node = self._node(name)
            node["calls"] = int(node.get("calls", 0) or 0) + 1
            node["last_seen"] = _iso_now()
            if group_name:
                groups = node.get("groups")
                if not isinstance(groups, dict):
                    groups = {}
                    node["groups"] = groups
                groups[group_name] = int(groups.get(group_name, 0) or 0) + 1
            if caps:
                capability_counts = node.get("capabilities")
                if not isinstance(capability_counts, dict):
                    capability_counts = {}
                    node["capabilities"] = capability_counts
                for capability in caps:
                    capability_counts[capability] = int(capability_counts.get(capability, 0) or 0) + 1

            source_call_id = str(state.get("last_call_id", "") or "")
            source_tool = ""
            source_group = ""
            if source_call_id:
                source_ctx = calls.get(source_call_id)
                if isinstance(source_ctx, dict):
                    source_tool = str(source_ctx.get("tool", "") or "")
                    source_group = str(source_ctx.get("group", "") or "")
            if source_tool:
                edge = self._edge(source_tool, name)
                edge["transitions"] = int(edge.get("transitions", 0) or 0) + 1
                edge["last_seen"] = _iso_now()
                if consumed and produced_paths and consumed.intersection(produced_paths):
                    edge["file_flow"] = int(edge.get("file_flow", 0) or 0) + 1
                if source_group and group_name:
                    group_edge = self._group_edge(source_group, group_name)
                    group_edge["transitions"] = int(group_edge.get("transitions", 0) or 0) + 1
                    group_edge["last_seen"] = _iso_now()

            calls[cid] = {
                "tool": name,
                "group": group_name,
                "source_call_id": source_call_id,
                "source_tool": source_tool,
                "source_group": source_group,
                "consumed_paths": list(consumed),
            }
            state["last_call_id"] = cid
            if source_call_id and source_call_id != cid:
                calls.pop(source_call_id, None)
            self._trim_request_state()
            should_persist = self._touch_locked()
        if should_persist:
            self.persist()

    def observe_tool_call_result(
        self,
        *,
        request_id: str,
        call_id: str,
        tool_name: str,
        success: bool,
        latency_ms: float,
        produced_paths: Optional[Sequence[str]] = None,
    ) -> None:
        self._ensure_loaded()
        rid = str(request_id or "__direct__")
        cid = str(call_id or "")
        name = str(tool_name or "").strip()
        if not name:
            return
        latency = max(0.0, float(latency_ms or 0.0))
        produced = {_clean_path(path) for path in (produced_paths or []) if _clean_path(path)}

        should_persist = False
        with self._lock:
            state = self._request_state.get(rid, {})
            calls = state.get("calls", {}) if isinstance(state, dict) else {}
            context = calls.get(cid, {}) if isinstance(calls, dict) else {}
            source_tool = str(context.get("source_tool", "") or "")
            source_group = str(context.get("source_group", "") or "")
            group_name = str(context.get("group", "") or "")

            node = self._node(name)
            if success:
                node["success"] = int(node.get("success", 0) or 0) + 1
            else:
                node["failure"] = int(node.get("failure", 0) or 0) + 1
            node["total_latency_ms"] = float(node.get("total_latency_ms", 0.0) or 0.0) + latency
            node["last_seen"] = _iso_now()

            if source_tool:
                edge = self._edge(source_tool, name)
                if success:
                    edge["success"] = int(edge.get("success", 0) or 0) + 1
                else:
                    edge["failure"] = int(edge.get("failure", 0) or 0) + 1
                edge["total_latency_ms"] = float(edge.get("total_latency_ms", 0.0) or 0.0) + latency
                edge["last_seen"] = _iso_now()
                if source_group and group_name:
                    group_edge = self._group_edge(source_group, group_name)
                    if success:
                        group_edge["success"] = int(group_edge.get("success", 0) or 0) + 1
                    else:
                        group_edge["failure"] = int(group_edge.get("failure", 0) or 0) + 1
                    group_edge["total_latency_ms"] = float(group_edge.get("total_latency_ms", 0.0) or 0.0) + latency
                    group_edge["last_seen"] = _iso_now()

            if produced and isinstance(state, dict):
                produced_paths = state.setdefault("produced_paths", set())
                if not isinstance(produced_paths, set):
                    produced_paths = set(produced_paths)
                produced_paths.update(produced)
                if len(produced_paths) > MAX_PRODUCED_PATHS_PER_REQUEST:
                    trimmed = list(produced_paths)[:MAX_PRODUCED_PATHS_PER_REQUEST]
                    state["produced_paths"] = set(trimmed)
                else:
                    state["produced_paths"] = produced_paths

            if isinstance(calls, dict) and cid != str(state.get("last_call_id", "") or ""):
                calls.pop(cid, None)
            should_persist = self._touch_locked()
        if should_persist:
            self.persist()

    @staticmethod
    def _node_score(node: Dict[str, Any]) -> float:
        calls = max(0, int(node.get("calls", 0) or 0))
        success = max(0, int(node.get("success", 0) or 0))
        failure = max(0, int(node.get("failure", 0) or 0))
        total_latency = max(0.0, float(node.get("total_latency_ms", 0.0) or 0.0))
        avg_latency = total_latency / max(1, success + failure)
        success_rate = (success + 1.0) / (success + failure + 2.0)
        usage_bonus = min(1.0, math.log1p(calls) / 5.0)
        latency_penalty = min(1.0, avg_latency / 2500.0)
        return (success_rate * 0.65) + (usage_bonus * 0.30) - (latency_penalty * 0.25)

    def rank_tool_names(self, tool_names: Sequence[str]) -> List[str]:
        self._ensure_loaded()
        names = _ordered_unique(tool_names)
        with self._lock:
            nodes = self._payload.get("nodes", {})
            scored = []
            for name in names:
                node = nodes.get(name, {}) if isinstance(nodes, dict) else {}
                score = self._node_score(node if isinstance(node, dict) else {})
                scored.append((name, score))
        return [name for name, _score in sorted(scored, key=lambda item: (-item[1], item[0]))]

    def suggest_followup_groups(
        self,
        *,
        seed_groups: Sequence[str],
        available_groups: Sequence[str],
        prompt: str = "",
        limit: int = 2,
    ) -> List[str]:
        self._ensure_loaded()
        seeds = [group for group in _ordered_unique(seed_groups) if group]
        available = set(_ordered_unique(available_groups))
        if not seeds or not available:
            return []
        candidates: Dict[str, float] = {}
        prompt_text = str(prompt or "").lower()
        with self._lock:
            group_edges = self._payload.get("group_edges", {})
            for seed in seeds:
                outgoing: List[Dict[str, Any]] = []
                for edge in group_edges.values() if isinstance(group_edges, dict) else []:
                    if not isinstance(edge, dict):
                        continue
                    if str(edge.get("src", "")) != seed:
                        continue
                    outgoing.append(edge)
                total = sum(max(0, int(edge.get("transitions", 0) or 0)) for edge in outgoing)
                if total <= 0:
                    continue
                for edge in outgoing:
                    dst = str(edge.get("dst", "") or "")
                    if not dst or dst in seeds or dst not in available:
                        continue
                    transitions = max(0, int(edge.get("transitions", 0) or 0))
                    success = max(0, int(edge.get("success", 0) or 0))
                    failure = max(0, int(edge.get("failure", 0) or 0))
                    success_rate = (success + 1.0) / (success + failure + 2.0)
                    transition_prob = transitions / max(1, total)
                    confidence = min(1.0, transitions / 12.0)
                    score = transition_prob * success_rate * (0.5 + 0.5 * confidence)
                    if dst in prompt_text:
                        score += 0.10
                    candidates[dst] = max(candidates.get(dst, 0.0), score)
        ranked = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))
        return [name for name, _ in ranked[: max(0, int(limit))]]

    def get_stats(self) -> Dict[str, Any]:
        self._ensure_loaded()
        with self._lock:
            nodes = self._payload.get("nodes", {})
            edges = self._payload.get("edges", {})
            group_edges = self._payload.get("group_edges", {})
            return {
                "nodes": len(nodes) if isinstance(nodes, dict) else 0,
                "edges": len(edges) if isinstance(edges, dict) else 0,
                "groupEdges": len(group_edges) if isinstance(group_edges, dict) else 0,
                "updatedAt": str(self._payload.get("updated_at", "") or ""),
            }

    def snapshot(self) -> Dict[str, Any]:
        self._ensure_loaded()
        with self._lock:
            return {
                "version": int(self._payload.get("version", 1) or 1),
                "updated_at": str(self._payload.get("updated_at", "") or ""),
                "nodes": json.loads(json.dumps(self._payload.get("nodes", {}))),
                "edges": json.loads(json.dumps(self._payload.get("edges", {}))),
                "group_edges": json.loads(json.dumps(self._payload.get("group_edges", {}))),
            }


_default_graph: Optional[ToolCapabilityGraph] = None
_default_graph_lock = threading.Lock()


def get_default_graph(base_dir: Optional[Path] = None) -> ToolCapabilityGraph:
    global _default_graph
    if _default_graph is not None:
        return _default_graph
    with _default_graph_lock:
        if _default_graph is None:
            _default_graph = ToolCapabilityGraph(base_dir=base_dir)
    return _default_graph


def reset_default_graph() -> None:
    global _default_graph
    with _default_graph_lock:
        _default_graph = None
