"""Schema versioning for persisted-state artifacts.

Every JSON-backed file goes through ``load_json`` / ``save_json`` which wrap
the payload in a ``{"schema_version", "artifact", "data"}`` envelope. SQLite
databases declare their version in a ``meta`` table. Loaders refuse to read
a version newer than ``CURRENT_VERSIONS[artifact]``; migrations run
forward-only via :mod:`poor_cli.persisted.migrations`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ArtifactId = str

CURRENT_VERSIONS: dict[ArtifactId, int] = {
    "preferences": 1,
    "history": 1,
    "session": 1,
    "session_index": 1,
    "automation": 1,
    "runs": 1,
    "checkpoint": 1,
    "audit": 1,
    "savings": 1,
    "multiplayer": 1,
}

LEGACY_BACKUP_DIRNAME = ".legacy-v0"


class UnknownSchemaVersion(Exception):
    """Raised when a file declares a schema_version newer than this build knows."""


class ForwardMigrationFailed(Exception):
    """Raised when a registered migration function fails or is missing."""


@dataclass(frozen=True)
class VersionedState:
    schema_version: int
    artifact: ArtifactId
    data: Any


def _backup_dir_for(path: Path) -> Path:
    return path.parent / LEGACY_BACKUP_DIRNAME


def _backup_legacy(path: Path) -> Path:
    """Copy the pre-envelope file to ``.legacy-v0/<name>.<ts>.bak`` and return the backup path."""
    backup_dir = _backup_dir_for(path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{path.name}.{ts}.bak"
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _is_envelope(obj: Any, artifact: ArtifactId) -> bool:
    return (
        isinstance(obj, dict)
        and "schema_version" in obj
        and "data" in obj
        and obj.get("artifact", artifact) == artifact
    )


def load_json(
    path: Path,
    artifact: ArtifactId,
    *,
    default: Any = None,
) -> Any:
    """Load a JSON artifact, running forward-migrations as needed.

    If the file is missing, returns ``default`` (or ``None``). If the file
    exists without the envelope, treats it as v0, runs migrations to current,
    rewrites the envelope atomically, and keeps a backup in ``.legacy-v0/``.
    """
    from .migrations import migrate_forward

    if artifact not in CURRENT_VERSIONS:
        raise ValueError(f"Unknown artifact id: {artifact!r}")

    current = CURRENT_VERSIONS[artifact]

    if not path.exists():
        return default

    raw = json.loads(path.read_text(encoding="utf-8"))

    if _is_envelope(raw, artifact):
        version = int(raw["schema_version"])
        if version > current:
            raise UnknownSchemaVersion(
                f"{path}: schema_version {version} is newer than this build "
                f"(current={current} for artifact {artifact!r}). Upgrade poor-cli."
            )
        data = raw["data"]
        if version < current:
            data = migrate_forward(artifact, data, from_version=version, to_version=current)
            _backup_legacy(path)
            _atomic_write_json(
                path,
                {"schema_version": current, "artifact": artifact, "data": data},
            )
        return data

    # Legacy v0: unwrapped payload. Back up, migrate, rewrite.
    _backup_legacy(path)
    data = migrate_forward(artifact, raw, from_version=0, to_version=current)
    _atomic_write_json(
        path,
        {"schema_version": current, "artifact": artifact, "data": data},
    )
    return data


def save_json(path: Path, artifact: ArtifactId, data: Any) -> None:
    """Write ``data`` to ``path`` wrapped in the current envelope (atomic)."""
    if artifact not in CURRENT_VERSIONS:
        raise ValueError(f"Unknown artifact id: {artifact!r}")
    _atomic_write_json(
        path,
        {
            "schema_version": CURRENT_VERSIONS[artifact],
            "artifact": artifact,
            "data": data,
        },
    )


# ── SQLite helpers ───────────────────────────────────────────────────


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )


def read_sqlite_version(conn: sqlite3.Connection) -> int | None:
    """Return the ``schema_version`` row from ``meta``, or ``None`` if absent."""
    try:
        cur = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    except sqlite3.OperationalError:
        return None
    row = cur.fetchone()
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def set_sqlite_version(conn: sqlite3.Connection, version: int) -> None:
    _ensure_meta_table(conn)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(int(version)),),
    )


def seed_sqlite_meta(conn: sqlite3.Connection, artifact: ArtifactId) -> None:
    """Create the ``meta`` table (if needed) and seed schema_version + artifact.

    Idempotent: uses ``INSERT OR IGNORE`` so existing rows are preserved.
    """
    if artifact not in CURRENT_VERSIONS:
        raise ValueError(f"Unknown artifact id: {artifact!r}")
    _ensure_meta_table(conn)
    conn.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(CURRENT_VERSIONS[artifact]),),
    )
    conn.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES ('artifact', ?)",
        (artifact,),
    )


def run_sqlite_migrations(conn: sqlite3.Connection, artifact: ArtifactId) -> None:
    """Seed meta then apply any registered SQLite migrations up to current."""
    from .migrations import SQLITE_MIGRATIONS

    if artifact not in CURRENT_VERSIONS:
        raise ValueError(f"Unknown artifact id: {artifact!r}")
    current = CURRENT_VERSIONS[artifact]

    existing = read_sqlite_version(conn)
    if existing is None:
        seed_sqlite_meta(conn, artifact)
        existing = read_sqlite_version(conn) or current

    if existing > current:
        raise UnknownSchemaVersion(
            f"SQLite artifact {artifact!r}: schema_version {existing} newer than current {current}"
        )

    migrations = SQLITE_MIGRATIONS.get(artifact, {})
    v = existing
    while v < current:
        step = migrations.get(v)
        if step is None:
            raise ForwardMigrationFailed(
                f"No SQLite migration registered for {artifact!r} v{v} -> v{v + 1}"
            )
        step(conn)
        v += 1
        set_sqlite_version(conn, v)
    conn.commit()
