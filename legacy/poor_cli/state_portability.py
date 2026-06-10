"""Open-harness state export/import."""

from __future__ import annotations

import json
import hashlib
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass
class StateArchiveResult:
    archive: str
    files: List[str]
    skipped: List[str]
    manifest: Optional[Dict[str, object]] = None

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {"archive": self.archive, "files": self.files, "skipped": self.skipped}
        if self.manifest is not None:
            payload["manifest"] = self.manifest
        return payload


@dataclass
class RepoStateInfo:
    path: str
    exists: bool
    files: int
    bytes: int
    removal_command: str = "poor-cli state remove"

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": self.path,
            "exists": self.exists,
            "files": self.files,
            "bytes": self.bytes,
            "removal_command": self.removal_command,
        }


def _repo_state_path(repo_root: Optional[Path] = None) -> Path:
    from .repo_config import _normalize_repo_path

    return _normalize_repo_path(repo_root) / ".poor-cli"


def inspect_repo_state(*, repo_root: Optional[Path] = None) -> RepoStateInfo:
    path = _repo_state_path(repo_root)
    files = 0
    total_bytes = 0
    if path.exists():
        for child in path.rglob("*"):
            if child.is_file():
                files += 1
                total_bytes += child.stat().st_size
    return RepoStateInfo(str(path), path.exists(), files, total_bytes)


def ensure_repo_state(*, repo_root: Optional[Path] = None) -> RepoStateInfo:
    from .repo_config import get_repo_config

    get_repo_config(repo_path=repo_root, enable_legacy_history_migration=False)
    return inspect_repo_state(repo_root=repo_root)


def remove_repo_state(*, repo_root: Optional[Path] = None, dry_run: bool = False) -> RepoStateInfo:
    before = inspect_repo_state(repo_root=repo_root)
    if before.exists and not dry_run:
        shutil.rmtree(before.path)
    return before


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_existing(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    yield child


def export_state(
    output: Path,
    *,
    home_state: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> StateArchiveResult:
    home = Path(home_state or Path.home() / ".poor-cli").resolve()
    repo_state = _repo_state_path(repo_root)
    repo = repo_state.parent
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = [
        home / "memory",
        home / "sessions",
        home / "history.json",
        home / "history.sqlite3",
        home / "preferences.json",
        repo_state / "context",
        repo_state / "audit",
        repo_state / "runs",
    ]
    files: List[str] = []
    skipped: List[str] = []
    manifest: Dict[str, object] = {
        "schema": "poor-cli-state-archive",
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "home_state": str(home),
        "repo_root": str(repo),
        "files": {},
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_existing(sources):
            try:
                if path.is_relative_to(home):
                    arcname = Path("home") / path.relative_to(home)
                elif path.is_relative_to(repo_state):
                    arcname = Path("repo") / path.relative_to(repo_state)
                else:
                    skipped.append(str(path))
                    continue
                archive.write(path, arcname.as_posix())
                files.append(arcname.as_posix())
                manifest["files"][arcname.as_posix()] = {  # type: ignore[index]
                    "sha256": _sha256(path),
                    "bytes": path.stat().st_size,
                }
            except Exception:
                skipped.append(str(path))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return StateArchiveResult(str(output), files, skipped, manifest)


def inspect_state_archive(archive_path: Path) -> StateArchiveResult:
    archive_path = Path(archive_path).expanduser().resolve()
    files: List[str] = []
    skipped: List[str] = []
    manifest: Dict[str, object] = {}
    with zipfile.ZipFile(archive_path, "r") as archive:
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except Exception:
            skipped.append("manifest.json")
        files = sorted(member.filename for member in archive.infolist() if not member.is_dir())
    return StateArchiveResult(str(archive_path), files, skipped, manifest)


def import_state(
    archive_path: Path,
    *,
    home_state: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    replace: bool = False,
    dry_run: bool = False,
) -> StateArchiveResult:
    archive_path = Path(archive_path).expanduser().resolve()
    home = Path(home_state or Path.home() / ".poor-cli").resolve()
    repo_state = _repo_state_path(repo_root)
    files: List[str] = []
    skipped: List[str] = []
    with zipfile.ZipFile(archive_path, "r") as archive:
        manifest: Dict[str, object] = {}
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except Exception:
            manifest = {}
        expected = manifest.get("files", {}) if isinstance(manifest, dict) else {}
        for member in archive.infolist():
            name = member.filename
            if member.is_dir() or name == "manifest.json":
                continue
            if name.startswith("home/"):
                dest = home / name.removeprefix("home/")
            elif name.startswith("repo/"):
                dest = repo_state / name.removeprefix("repo/")
            else:
                skipped.append(name)
                continue
            if dest.exists() and not replace:
                skipped.append(name)
                continue
            meta = expected.get(name, {}) if isinstance(expected, dict) else {}
            if isinstance(meta, dict) and meta.get("sha256"):
                with archive.open(member, "r") as src:
                    data = src.read()
                actual = hashlib.sha256(data).hexdigest()
                if actual != meta.get("sha256"):
                    skipped.append(f"{name}:checksum-mismatch")
                    continue
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                files.append(str(dest))
                continue
            if dry_run:
                files.append(str(dest))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src:
                dest.write_bytes(src.read())
            files.append(str(dest))
    return StateArchiveResult(str(archive_path), files, skipped, manifest)
