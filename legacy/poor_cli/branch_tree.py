from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_content(message: Dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    parts = message.get("parts")
    if isinstance(parts, list):
        texts: List[str] = []
        for part in parts:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])
        return "\n".join(texts)
    return ""


def _message_role(message: Dict[str, Any]) -> str:
    role = str(message.get("role") or "assistant")
    return "assistant" if role == "model" else role


def _message_id(message: Dict[str, Any]) -> Optional[str]:
    for key in ("id", "turn_id", "turnId"):
        value = str(message.get(key) or "").strip()
        if value:
            return value
    return None


def _message_parent_id(message: Dict[str, Any]) -> Optional[str]:
    value = str(message.get("parent_id") or message.get("parentId") or "").strip()
    return value or None


def _message_branch_of(message: Dict[str, Any]) -> Optional[str]:
    value = str(message.get("branch_of") or message.get("branchOf") or "").strip()
    return value or None


def _history_key(history: List[Dict[str, Any]]) -> str:
    return json.dumps(history, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _is_prefix(prefix: List[Dict[str, Any]], history: List[Dict[str, Any]]) -> bool:
    if len(prefix) > len(history):
        return False
    return _history_key(prefix) == _history_key(history[: len(prefix)])


@dataclass
class BranchNode:
    node_id: str
    parent_id: Optional[str]
    branch_of: Optional[str]
    role: str
    content: str
    snapshot: List[Dict[str, Any]]
    created_at: str = field(default_factory=_utc_now)

    def to_dict(
        self,
        active_id: Optional[str],
        children: List["BranchNode"],
        sibling_index: int = 1,
        sibling_count: int = 1,
    ) -> Dict[str, Any]:
        preview = self.content.replace("\n", " ").strip()
        if len(preview) > 80:
            preview = preview[:77] + "..."
        return {
            "id": self.node_id,
            "parentId": self.parent_id,
            "branchOf": self.branch_of,
            "role": self.role,
            "label": f"{self.role}: {preview}" if preview else self.role,
            "preview": preview,
            "active": self.node_id == active_id,
            "createdAt": self.created_at,
            "siblingIndex": sibling_index,
            "siblingCount": sibling_count,
            "children": [child.to_dict(active_id, []) for child in children],
        }


class ConversationBranchStore:
    def __init__(self) -> None:
        self.nodes: Dict[str, BranchNode] = {}
        self.active_id: Optional[str] = None
        self._counter = 0

    def clear(self) -> None:
        self.nodes.clear()
        self.active_id = None
        self._counter = 0

    def sync_from_history(self, history: List[Dict[str, Any]]) -> None:
        history = copy.deepcopy(history or [])
        if not history:
            return
        if not self.nodes:
            parent_id = None
            for idx, message in enumerate(history):
                parent_id = self.add_node(
                    parent_id,
                    message,
                    history[: idx + 1],
                    node_id=_message_id(message),
                    branch_of=_message_branch_of(message),
                )
            self.active_id = parent_id
            return

        active = self.nodes.get(self.active_id or "")
        parent_id = active.node_id if active and _is_prefix(active.snapshot, history) else None
        start = len(active.snapshot) if parent_id and active else 0

        if parent_id is None:
            best: Optional[BranchNode] = None
            for node in self.nodes.values():
                if _is_prefix(node.snapshot, history) and (best is None or len(node.snapshot) > len(best.snapshot)):
                    best = node
            if best:
                parent_id = best.node_id
                start = len(best.snapshot)

        if start == len(history):
            self.active_id = parent_id
            return

        for idx in range(start, len(history)):
            parent_id = self.add_node(
                parent_id,
                history[idx],
                history[: idx + 1],
                node_id=_message_id(history[idx]),
                branch_of=_message_branch_of(history[idx]),
            )
        self.active_id = parent_id

    def add_node(
        self,
        parent_id: Optional[str],
        message: Dict[str, Any],
        snapshot: List[Dict[str, Any]],
        branch_of: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> str:
        explicit_parent = _message_parent_id(message)
        if explicit_parent:
            parent_id = explicit_parent
        if node_id and node_id in self.nodes:
            return node_id
        self._counter += 1
        node_id = node_id or f"turn-{self._counter}"
        while node_id in self.nodes:
            self._counter += 1
            node_id = f"turn-{self._counter}"
        self.nodes[node_id] = BranchNode(
            node_id=node_id,
            parent_id=parent_id,
            branch_of=branch_of,
            role=_message_role(message),
            content=_message_content(message),
            snapshot=copy.deepcopy(snapshot),
        )
        return node_id

    def add_sibling(self, node_id: str, message: Dict[str, Any], snapshot: List[Dict[str, Any]]) -> str:
        node = self.nodes[node_id]
        sibling_id = self.add_node(node.parent_id, message, snapshot, branch_of=node_id)
        self.active_id = sibling_id
        return sibling_id

    def switch(self, node_id: Optional[str] = None, direction: str = "") -> BranchNode:
        target_id = node_id or self.active_id
        if not target_id or target_id not in self.nodes:
            raise KeyError("branch not found")
        if direction:
            target_id = self.sibling_id(target_id, direction)
        self.active_id = target_id
        return self.nodes[target_id]

    def sibling_id(self, node_id: str, direction: str) -> str:
        node = self.nodes[node_id]
        siblings = [candidate for candidate in self.nodes.values() if candidate.parent_id == node.parent_id]
        siblings.sort(key=lambda item: item.created_at)
        ids = [candidate.node_id for candidate in siblings]
        idx = ids.index(node_id)
        delta = -1 if direction in ("prev", "previous", "left") else 1
        return ids[(idx + delta) % len(ids)]

    def tree(self, max_siblings: int = 20) -> Dict[str, Any]:
        children: Dict[Optional[str], List[BranchNode]] = {}
        for node in self.nodes.values():
            children.setdefault(node.parent_id, []).append(node)
        for rows in children.values():
            rows.sort(key=lambda item: item.created_at)

        def build(parent_id: Optional[str]) -> List[Dict[str, Any]]:
            siblings = children.get(parent_id, [])
            cap = max(max_siblings, 1)
            visible = siblings[:cap]
            if self.active_id and self.active_id in {node.node_id for node in siblings}:
                active = next(node for node in siblings if node.node_id == self.active_id)
                if all(node.node_id != active.node_id for node in visible):
                    visible = visible[:-1] + [active]
            rendered: List[Dict[str, Any]] = []
            for node in visible:
                ids = [item.node_id for item in siblings]
                item = node.to_dict(
                    self.active_id,
                    children.get(node.node_id, []),
                    sibling_index=ids.index(node.node_id) + 1 if node.node_id in ids else 1,
                    sibling_count=len(siblings) or 1,
                )
                item["children"] = build(node.node_id)
                rendered.append(item)
            hidden = len(siblings) - len(visible)
            if hidden > 0:
                rendered.append({"collapsed": True, "count": hidden, "parentId": parent_id})
            return rendered

        def sibling_meta(node: BranchNode) -> tuple[int, int]:
            siblings = children.get(node.parent_id, [])
            ids = [item.node_id for item in siblings]
            return (ids.index(node.node_id) + 1 if node.node_id in ids else 1, len(siblings) or 1)

        nodes = []
        for node in sorted(self.nodes.values(), key=lambda item: item.created_at):
            idx, count = sibling_meta(node)
            nodes.append(node.to_dict(self.active_id, [], sibling_index=idx, sibling_count=count))
        active_path: List[Dict[str, Any]] = []
        active = self.nodes.get(self.active_id or "")
        if active:
            for node in sorted(self.nodes.values(), key=lambda item: len(item.snapshot)):
                if _history_key(node.snapshot) == _history_key(active.snapshot[: len(node.snapshot)]):
                    idx, count = sibling_meta(node)
                    active_path.append(node.to_dict(self.active_id, [], sibling_index=idx, sibling_count=count))
        return {
            "activeId": self.active_id,
            "activeLeaf": self.active_id,
            "activePath": active_path,
            "roots": build(None),
            "nodes": nodes,
            "maxSiblings": max_siblings,
        }
