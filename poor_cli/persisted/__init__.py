"""Schema-versioned persisted state for poor-cli.

See PRD 003 for design rationale. Public surface:

- :func:`load_json` / :func:`save_json` — envelope-wrapped JSON I/O.
- :func:`seed_sqlite_meta` / :func:`run_sqlite_migrations` — SQLite ``meta`` table helpers.
- :data:`CURRENT_VERSIONS` — authoritative map of artifact -> current version.
- Exceptions: :class:`UnknownSchemaVersion`, :class:`ForwardMigrationFailed`.
"""

from .schema import (
    CURRENT_VERSIONS,
    ForwardMigrationFailed,
    UnknownSchemaVersion,
    VersionedState,
    load_json,
    read_sqlite_version,
    run_sqlite_migrations,
    save_json,
    seed_sqlite_meta,
    set_sqlite_version,
)

__all__ = [
    "CURRENT_VERSIONS",
    "ForwardMigrationFailed",
    "UnknownSchemaVersion",
    "VersionedState",
    "load_json",
    "save_json",
    "read_sqlite_version",
    "run_sqlite_migrations",
    "seed_sqlite_meta",
    "set_sqlite_version",
]
