"""
Trust model for poor-cli repositories.

Prevents untrusted repos from injecting custom config, instructions, or skills.
Trusted repos are stored in ~/.poor-cli/trusted_repos.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .exceptions import setup_logger

logger = setup_logger(__name__)

TRUST_FILE = "trusted_repos.json"


class TrustManager:
    """Manages trust state for repositories."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = (base_dir or Path.home() / ".poor-cli").resolve()
        self._trust_file = self._base / TRUST_FILE
        self._trusted: Set[str] = set()
        self._load()

    def _load(self) -> None:
        if self._trust_file.exists():
            try:
                data = json.loads(self._trust_file.read_text(encoding="utf-8"))
                self._trusted = set(data.get("trusted", []))
            except Exception as exc:
                logger.warning("failed to load trust file: %s", exc)
                self._trusted = set()

    def _save(self) -> None:
        self._base.mkdir(parents=True, exist_ok=True)
        data = {"trusted": sorted(self._trusted)}
        self._trust_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_trusted(self, repo_path: Optional[str] = None) -> bool:
        """Check if a repo is trusted. Resolves to canonical path."""
        if repo_path is None:
            repo_path = str(Path.cwd())
        canonical = str(Path(repo_path).resolve())
        return canonical in self._trusted

    def trust(self, repo_path: Optional[str] = None) -> str:
        """Mark a repo as trusted. Returns canonical path."""
        if repo_path is None:
            repo_path = str(Path.cwd())
        canonical = str(Path(repo_path).resolve())
        self._trusted.add(canonical)
        self._save()
        logger.info("trusted repo: %s", canonical)
        return canonical

    def untrust(self, repo_path: Optional[str] = None) -> bool:
        """Remove trust for a repo. Returns True if was trusted."""
        if repo_path is None:
            repo_path = str(Path.cwd())
        canonical = str(Path(repo_path).resolve())
        if canonical in self._trusted:
            self._trusted.discard(canonical)
            self._save()
            logger.info("untrusted repo: %s", canonical)
            return True
        return False

    def list_trusted(self) -> List[str]:
        """List all trusted repo paths."""
        return sorted(self._trusted)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trusted": self.list_trusted(),
            "currentRepoTrusted": self.is_trusted(),
            "currentRepo": str(Path.cwd().resolve()),
        }
