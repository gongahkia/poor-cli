"""Canonical session snapshot storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .persisted import load_json, save_json


class SessionStore:
    """Persists conversation snapshots under .poor-cli/sessions."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.base_dir = self.repo_root / ".poor-cli" / "sessions"
        self.index_path = self.base_dir / "index.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        safe_session_id = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in {"-", "_"}).strip() or "session"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        file_name = f"session-{safe_session_id}-{timestamp}.json"
        target = self.base_dir / file_name

        snapshot = dict(payload)
        snapshot["session_id"] = safe_session_id
        snapshot["saved_at"] = snapshot.get("saved_at") or datetime.now(timezone.utc).isoformat()
        save_json(target, "session", snapshot)

        index_entry = {
            "sessionId": safe_session_id,
            "savedAt": str(snapshot["saved_at"]),
            "path": str(target),
            "provider": snapshot.get("provider"),
            "model": snapshot.get("model"),
            "messageCount": len(snapshot.get("history") or snapshot.get("messages") or []),
        }
        index = self._read_index()
        index = [entry for entry in index if str(entry.get("path", "")) != str(target)]
        index.insert(0, index_entry)
        self._write_index(index)
        return index_entry

    def list(self, limit: int = 20) -> List[Dict[str, Any]]:
        index = self._read_index()
        deduped: List[Dict[str, Any]] = []
        for entry in index:
            path = Path(str(entry.get("path", "")))
            if not path.is_file():
                continue
            deduped.append(entry)
            if len(deduped) >= max(1, min(int(limit), 500)):
                break
        return deduped

    def load_latest(self) -> Optional[Dict[str, Any]]:
        sessions = self.list(limit=1)
        if not sessions:
            return None
        latest_path = Path(str(sessions[0].get("path", "")))
        if not latest_path.is_file():
            return None
        try:
            payload = load_json(latest_path, "session")
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        payload.setdefault("session_id", sessions[0].get("sessionId", ""))
        payload.setdefault("saved_at", sessions[0].get("savedAt", ""))
        payload.setdefault("_store_path", str(latest_path))
        return payload

    def load(self, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not session_id:
            return self.load_latest()
        target_session = str(session_id).strip()
        if not target_session:
            return self.load_latest()
        for entry in self._read_index():
            if str(entry.get("sessionId", "")).strip() != target_session:
                continue
            path = Path(str(entry.get("path", "")))
            if not path.is_file():
                continue
            try:
                payload = load_json(path, "session")
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            payload.setdefault("session_id", target_session)
            payload.setdefault("saved_at", entry.get("savedAt", ""))
            payload.setdefault("_store_path", str(path))
            return payload
        return None

    def _read_index(self) -> List[Dict[str, Any]]:
        try:
            payload = load_json(self.index_path, "session_index")
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        entries = payload.get("sessions")
        if not isinstance(entries, list):
            return []
        result: List[Dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            result.append(dict(entry))
        return result

    def _write_index(self, entries: List[Dict[str, Any]]) -> None:
        payload = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "sessions": entries,
        }
        save_json(self.index_path, "session_index", payload)
