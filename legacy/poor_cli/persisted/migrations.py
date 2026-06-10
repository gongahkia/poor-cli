"""Forward-only migration registry for persisted-state artifacts.

To add a migration, register a function that takes v_n data and returns
v_{n+1} data in :data:`MIGRATIONS`. For SQLite migrations, register a
function that mutates a live connection in :data:`SQLITE_MIGRATIONS`.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from .schema import ArtifactId, ForwardMigrationFailed

JsonMigration = Callable[[Any], Any]
SqliteMigration = Callable[[sqlite3.Connection], None]


def _identity(data: Any) -> Any:
    """v0 -> v1 pure-structural wrap: content is unchanged."""
    return data


# ``MIGRATIONS[artifact][from_version] -> v_{from_version+1} data``
#
# v0 is the pre-envelope legacy format. For every current artifact the v0 → v1
# step is structural only (wrap in envelope; no payload changes), so ``_identity``
# is correct.
MIGRATIONS: dict[ArtifactId, dict[int, JsonMigration]] = {
    "preferences": {0: _identity},
    "history": {0: _identity},
    "session": {0: _identity},
    "session_index": {0: _identity},
    "automation": {0: _identity},
    "checkpoint": {0: _identity},
}


SQLITE_MIGRATIONS: dict[ArtifactId, dict[int, SqliteMigration]] = {
    # SQLite migrations land in the PRDs that introduce schema changes.
    # Scaffolding only for now — databases are seeded at v1 on creation.
}


def migrate_forward(
    artifact: ArtifactId,
    data: Any,
    *,
    from_version: int,
    to_version: int,
) -> Any:
    """Apply registered migrations in order from ``from_version`` to ``to_version``."""
    if from_version == to_version:
        return data
    if from_version > to_version:
        raise ForwardMigrationFailed(
            f"{artifact!r}: cannot migrate backwards ({from_version} -> {to_version})"
        )

    chain = MIGRATIONS.get(artifact, {})
    current = data
    v = from_version
    while v < to_version:
        step = chain.get(v)
        if step is None:
            raise ForwardMigrationFailed(
                f"No migration registered for {artifact!r} v{v} -> v{v + 1}"
            )
        current = step(current)
        v += 1
    return current
