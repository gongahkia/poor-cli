"""Checkpoint timeline tree data helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class CheckpointTreeNode:
    node_id: str
    label: str
    kind: str
    payload: Dict[str, Any]
    children: List["CheckpointTreeNode"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "label": self.label,
            "kind": self.kind,
            "payload": dict(self.payload),
            "children": [child.to_dict() for child in self.children],
        }


def checkpoint_tree_payload(session_id: str, branch_tree: Dict[str, Any], checkpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
    roots = [
        _branch_node(node)
        for node in branch_tree.get("roots", [])
        if isinstance(node, dict)
    ]
    checkpoint_nodes = [_checkpoint_node(item, idx + 1) for idx, item in enumerate(checkpoints)]
    root = CheckpointTreeNode(
        node_id=str(session_id or "session"),
        label=f"Session {session_id or 'current'}",
        kind="session",
        payload={"activeId": branch_tree.get("activeId")},
        children=roots + checkpoint_nodes,
    )
    return root.to_dict()


def _branch_node(node: Dict[str, Any]) -> CheckpointTreeNode:
    children = [_branch_node(child) for child in node.get("children", []) if isinstance(child, dict)]
    return CheckpointTreeNode(
        node_id=str(node.get("id") or ""),
        label=str(node.get("label") or node.get("id") or "turn"),
        kind="branch",
        payload={key: node.get(key) for key in ("id", "active", "createdAt", "preview")},
        children=children,
    )


def _checkpoint_node(item: Dict[str, Any], index: int) -> CheckpointTreeNode:
    checkpoint_id = str(item.get("checkpointId") or item.get("checkpoint_id") or f"checkpoint-{index}")
    created = str(item.get("createdAt") or item.get("created_at") or "")
    reason = str(item.get("description") or item.get("operationType") or item.get("operation_type") or "checkpoint")
    return CheckpointTreeNode(
        node_id=checkpoint_id,
        label=f"{created} {reason}".strip(),
        kind="checkpoint",
        payload=dict(item),
        children=[],
    )


def diff_hunk_count(diff_text: str) -> int:
    return sum(1 for line in str(diff_text).splitlines() if line.startswith("@@"))
