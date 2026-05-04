"""In-memory staged edit proposals for diff review."""

from __future__ import annotations

import difflib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .policy_hooks import emit_policy_hook_nowait


@dataclass
class Hunk:
    hunk_id: str
    path: str
    header: str
    before: List[str]
    after: List[str]
    line_start: int
    original_start: int
    original_end: int
    proposed_start: int
    proposed_end: int
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hunk_id": self.hunk_id,
            "hunkId": self.hunk_id,
            "path": self.path,
            "header": self.header,
            "before": "".join(self.before),
            "after": "".join(self.after),
            "line_start": self.line_start,
            "lineStart": self.line_start,
            "status": self.status,
        }


@dataclass
class PendingEdit:
    edit_id: str
    path: str
    original: str
    proposed: str
    hunks: List[Hunk]
    tool_call_id: str = ""
    prompt: str = ""
    diff_text: str = ""
    status: str = "pending"
    checkpoint_id: Optional[str] = None
    finalized: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edit_id": self.edit_id,
            "editId": self.edit_id,
            "path": self.path,
            "prompt": self.prompt,
            "tool_call_id": self.tool_call_id,
            "toolCallId": self.tool_call_id,
            "status": self.status,
            "diff": self.diff_text,
            "original": self.original,
            "proposed": self.proposed,
            "hunks": [h.to_dict() for h in self.hunks],
            "checkpoint_id": self.checkpoint_id,
            "checkpointId": self.checkpoint_id,
            "finalized": self.finalized,
        }


def _to_text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def _split_lines(value: str) -> List[str]:
    return value.splitlines(keepends=True)


def _line_count(value: str) -> int:
    return sum(
        1 for line in value.splitlines()
        if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))
    )


def should_stage_edit(
    config: Any,
    path: str,
    original: str,
    proposed: str,
    *,
    interactive: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> bool:
    if original == proposed:
        return False
    env = env or os.environ
    if str(env.get("POOR_CLI_DIFF_REVIEW", "")).strip().lower() == "auto":
        return False
    if not interactive:
        return False
    diff_cfg = getattr(config, "diff_review", None)
    mode = str(getattr(diff_cfg, "mode", "review") or "review").strip().lower()
    if mode == "auto":
        return False
    if mode == "review":
        return True
    if mode != "review_risky":
        return True
    threshold = int(getattr(diff_cfg, "risky_line_threshold", 50) or 50)
    risky_paths = getattr(diff_cfg, "risky_paths", []) or []
    rel = str(path)
    basename = Path(rel).name
    for pattern in risky_paths:
        pat = str(pattern)
        if pat == basename or pat == rel:
            return True
        try:
            if re.search(pat, rel):
                return True
        except re.error:
            continue
    diff_text = "".join(difflib.unified_diff(_split_lines(original), _split_lines(proposed)))
    return _line_count(diff_text) >= threshold


class EditStage:
    def __init__(self, writer: Optional[Callable[[Path, str], None]] = None):
        self._edits: Dict[str, PendingEdit] = {}
        self._writer = writer or self._default_write
        self.audit_events: List[Dict[str, Any]] = []

    @staticmethod
    def _default_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _audit(self, operation: str, edit: PendingEdit, **details: Any) -> None:
        self.audit_events.append({
            "operation": operation,
            "edit_id": edit.edit_id,
            "path": edit.path,
            "details": details,
        })

    def stage(
        self,
        *,
        path: str,
        original: bytes | str,
        proposed: bytes | str,
        tool_call_id: str = "",
        prompt: str = "",
    ) -> PendingEdit:
        original_text = _to_text(original)
        proposed_text = _to_text(proposed)
        edit_id = uuid.uuid4().hex[:12]
        diff_text = self._diff(path, original_text, proposed_text)
        edit = PendingEdit(
            edit_id=edit_id,
            path=str(path),
            original=original_text,
            proposed=proposed_text,
            hunks=self._hunks(edit_id, str(path), original_text, proposed_text),
            tool_call_id=tool_call_id,
            prompt=prompt,
            diff_text=diff_text,
        )
        self._edits[edit_id] = edit
        self._audit("diff.stage", edit, hunk_count=len(edit.hunks))
        return edit

    def list_pending(self) -> List[Dict[str, Any]]:
        return [edit.to_dict() for edit in self._edits.values() if not edit.finalized]

    def preview_edit(self, edit_id: str) -> Dict[str, Any]:
        return self._require(edit_id).to_dict()

    def accept_hunk(self, edit_id: str, hunk_id: str) -> Dict[str, Any]:
        edit = self._require(edit_id)
        self._hunk(edit, hunk_id).status = "accepted"
        self._refresh_status(edit)
        self._audit("diff.accept_hunk", edit, hunk_id=hunk_id)
        return edit.to_dict()

    def reject_hunk(self, edit_id: str, hunk_id: str) -> Dict[str, Any]:
        edit = self._require(edit_id)
        self._hunk(edit, hunk_id).status = "rejected"
        self._refresh_status(edit)
        self._audit("diff.reject_hunk", edit, hunk_id=hunk_id)
        return edit.to_dict()

    def accept_all(self, edit_id: str, checkpoint_manager: Any = None) -> Dict[str, Any]:
        edit = self._require(edit_id)
        for hunk in edit.hunks:
            hunk.status = "accepted"
        self._refresh_status(edit)
        return self.finalize(edit_id, checkpoint_manager=checkpoint_manager)

    def reject_all(self, edit_id: str) -> Dict[str, Any]:
        edit = self._require(edit_id)
        for hunk in edit.hunks:
            hunk.status = "rejected"
        self._refresh_status(edit)
        return self.finalize(edit_id)

    def regenerate_hunk(self, edit_id: str, hunk_id: str, new_content: str = "") -> Dict[str, Any]:
        edit = self._require(edit_id)
        hunk = self._hunk(edit, hunk_id)
        if new_content:
            hunk.after = _split_lines(new_content)
        hunk.status = "pending"
        self._refresh_status(edit)
        self._audit("diff.regenerate_hunk", edit, hunk_id=hunk_id)
        return edit.to_dict()

    def finalize(self, edit_id: str, checkpoint_manager: Any = None) -> Dict[str, Any]:
        edit = self._require(edit_id)
        accepted = [hunk for hunk in edit.hunks if hunk.status == "accepted"]
        if accepted:
            path = Path(edit.path)
            hook_payload = {
                "path": edit.path,
                "hunks": len(accepted),
                "editId": edit.edit_id,
            }
            hook_manager = getattr(self, "_hook_manager", None)
            emit_policy_hook_nowait(hook_manager, "pre_edit", hook_payload)
            current = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
            if current != edit.original:
                raise RuntimeError(f"Current file changed since staging: {edit.path}")
            if checkpoint_manager is not None:
                label = self._label(edit, len(accepted))
                if hasattr(checkpoint_manager, "create_for_batch"):
                    checkpoint = checkpoint_manager.create_for_batch(edit.edit_id, edit.path, label)
                else:
                    checkpoint = checkpoint_manager.create_checkpoint([edit.path], label, "diff_review_accept", ["diff_review"])
                edit.checkpoint_id = getattr(checkpoint, "checkpoint_id", None)
            self._writer(path, self._apply_accepted(edit))
            emit_policy_hook_nowait(
                hook_manager,
                "post_edit",
                {**hook_payload, "status": "written"},
            )
        edit.finalized = True
        self._refresh_status(edit)
        self._audit("diff.finalize", edit, accepted_hunks=len(accepted), checkpoint_id=edit.checkpoint_id)
        return edit.to_dict()

    @staticmethod
    def _diff(path: str, original: str, proposed: str) -> str:
        return "".join(difflib.unified_diff(
            _split_lines(original),
            _split_lines(proposed),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        ))

    @staticmethod
    def _hunks(edit_id: str, path: str, original: str, proposed: str) -> List[Hunk]:
        before = _split_lines(original)
        after = _split_lines(proposed)
        matcher = difflib.SequenceMatcher(a=before, b=after)
        hunks: List[Hunk] = []
        for index, (tag, i1, i2, j1, j2) in enumerate(matcher.get_opcodes(), 1):
            if tag == "equal":
                continue
            header = f"@@ -{i1 + 1},{i2 - i1} +{j1 + 1},{j2 - j1} @@"
            hunks.append(Hunk(
                hunk_id=f"{edit_id}:{index}",
                path=path,
                header=header,
                before=before[i1:i2],
                after=after[j1:j2],
                line_start=max(1, i1 + 1),
                original_start=i1,
                original_end=i2,
                proposed_start=j1,
                proposed_end=j2,
            ))
        return hunks

    def _apply_accepted(self, edit: PendingEdit) -> str:
        lines = _split_lines(edit.original)
        for hunk in sorted(edit.hunks, key=lambda item: item.original_start, reverse=True):
            if hunk.status == "accepted":
                lines[hunk.original_start:hunk.original_end] = hunk.after
        return "".join(lines)

    def _require(self, edit_id: str) -> PendingEdit:
        try:
            return self._edits[edit_id]
        except KeyError as exc:
            raise KeyError(f"unknown edit_id: {edit_id}") from exc

    @staticmethod
    def _hunk(edit: PendingEdit, hunk_id: str) -> Hunk:
        for hunk in edit.hunks:
            if hunk.hunk_id == hunk_id:
                return hunk
        raise KeyError(f"unknown hunk_id: {hunk_id}")

    @staticmethod
    def _refresh_status(edit: PendingEdit) -> None:
        statuses = {hunk.status for hunk in edit.hunks}
        if edit.finalized:
            if statuses == {"accepted"}:
                edit.status = "accepted"
            elif "accepted" in statuses:
                edit.status = "partial"
            else:
                edit.status = "rejected"
            return
        if statuses == {"accepted"}:
            edit.status = "accepted"
        elif statuses == {"rejected"}:
            edit.status = "rejected"
        elif statuses == {"pending"}:
            edit.status = "pending"
        else:
            edit.status = "partial"

    @staticmethod
    def _label(edit: PendingEdit, edit_count: int) -> str:
        prompt = " ".join((edit.prompt or "diff review accept").split())
        if len(prompt) > 72:
            prompt = prompt[:69] + "..."
        return f"{prompt} ({edit_count} edit{'s' if edit_count != 1 else ''})"
