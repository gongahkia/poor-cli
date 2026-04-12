# PRD 003: Schema-version every persisted-state file with a migration framework

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (2–3d)
- **Blocks:** —
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/session_store.py`
  - `poor_cli/history.py`
  - `poor_cli/config.py` (narrow — only the load/save paths)
  - `poor_cli/checkpoint.py`
  - `poor_cli/audit_log.py`
  - `poor_cli/automation_manager.py`
- **New files it adds:**
  - `poor_cli/persisted/__init__.py`
  - `poor_cli/persisted/schema.py`
  - `poor_cli/persisted/migrations.py`
  - `tests/test_persisted_schema.py`
  - `tests/test_persisted_migrations.py`

---

## 1. Problem

`.poor-cli/` holds several persisted-state artifacts:
- `preferences.json`
- `history.json`
- `sessions/*.json`
- `runs.db` (SQLite)
- `repo_graph.db` (SQLite)
- `checkpoints/*` (opaque)
- `audit/*` (append-only)
- `history_migration_marker.json` (single informal migration marker — the *only* migration signal today)

There is no schema version on any of these except the informal marker. One rename of a field in, say, `automation_manager.py` will corrupt every user's persisted state silently. The project has already been burned by this — the `history_migration_marker.json` exists to compensate for a past bad migration.

[`LEARNING.md` §1.4 & §2.2](../LEARNING.md) flag this as a P0 fix: "One bad field rename will break users."

## 2. Current state

Load/save is idiomatic JSON/SQLite today. Example:

```python
# poor_cli/session_store.py (conceptually)
def load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)

def save(path: Path, data: dict) -> None:
    with path.open("w") as f:
        json.dump(data, f, indent=2)
```

SQLite files (runs.db, repo_graph.db) have implicit schemas via `CREATE TABLE IF NOT EXISTS`. There is no `schema_version` row in a `meta` table.

## 3. Goal & non-goals

**Goal:** every persisted-state artifact declares a `schema_version: int`. Loaders refuse to read an unknown version, and migrations run forward-only via a registered migration pipeline. Tests prove that a synthetic "v1 state" + every migration produces the current schema byte-for-byte.

**Non-goals:**
- Do not introduce automatic *downgrades* (forward-only is enough).
- Do not change the semantic content of persisted state today — v1 is just current-state with a version field tacked on.
- Do not migrate SQLite schemas via raw ALTER TABLE scripts written by the agent; this PRD spec's the framework but only ships the scaffolding for SQLite. Actual SQLite migrations land in the PRDs that introduce schema changes.

## 4. Design

### 4.1 Framework

```python
# poor_cli/persisted/schema.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

ArtifactId = str  # e.g., "preferences", "history", "session", "automation"

@dataclass(frozen=True)
class VersionedState:
    schema_version: int
    artifact: ArtifactId
    data: Any  # dict for JSON; handled differently for SQLite

CURRENT_VERSIONS: dict[ArtifactId, int] = {
    "preferences":  1,
    "history":      1,
    "session":      1,
    "automation":   1,
    "runs":         1,   # SQLite, see 4.2
    "checkpoint":   1,
    "audit":        1,
}

class UnknownSchemaVersion(Exception): ...
class ForwardMigrationFailed(Exception): ...
```

```python
# poor_cli/persisted/migrations.py
from .schema import ArtifactId

Migration = Callable[[Any], Any]  # input = v_n data, output = v_{n+1} data

MIGRATIONS: dict[ArtifactId, dict[int, Migration]] = {
    # "preferences": {1: migrate_prefs_1_to_2, ...}
}

def migrate_forward(artifact: ArtifactId, data: Any, from_version: int, to_version: int) -> Any:
    ...
```

### 4.2 JSON artifacts

Wrapper format for every JSON-backed file:

```json
{
  "schema_version": 1,
  "artifact": "preferences",
  "data": { ... actual payload ... }
}
```

`load()` reads the envelope, validates `schema_version <= CURRENT_VERSIONS[artifact]`, runs any forward migrations into the current version, and returns `.data`.

`save()` writes with the current version.

First-run / missing-wrapper detection: if the file exists but lacks the envelope, treat it as legacy v0, wrap it with `schema_version: 0`, run migrations from v0 → current. Delete the `history_migration_marker.json` sentinel after this proves stable for one release.

### 4.3 SQLite artifacts

Add a `meta` table to each SQLite database:

```sql
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- seeded on creation:
INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('artifact', '<name>');
```

A helper in `persisted/schema.py`:

```python
def read_sqlite_version(conn) -> int: ...
def set_sqlite_version(conn, v: int) -> None: ...
def run_sqlite_migrations(conn, artifact: ArtifactId) -> None: ...
```

Individual migrations are written as Python functions that take a live connection, apply DDL/DML, and bump the version.

### 4.4 Backward-compatibility — v0 auto-upgrade

For users who already have `.poor-cli/` state without the envelope:

- On first `load()`, detect absence of `schema_version` field.
- Interpret current on-disk format as v0 for that artifact.
- Run the v0 → v1 migration (which for preferences is "wrap in envelope; populate schema_version=1; no other change").
- Write the new format atomically (tempfile + rename).
- Back up the old file to `.poor-cli/.legacy-v0/<artifact>.json.bak` with timestamp.

## 5. Files to create / modify / delete

**Create**
- `poor_cli/persisted/__init__.py` — exports `load_json`, `save_json`, `with_versioned_sqlite`.
- `poor_cli/persisted/schema.py` — types, `CURRENT_VERSIONS`, envelope functions, version readers.
- `poor_cli/persisted/migrations.py` — `MIGRATIONS` registry, `migrate_forward`, migration helpers.
- `tests/test_persisted_schema.py`
- `tests/test_persisted_migrations.py`

**Modify**
- `poor_cli/session_store.py` — route load/save through `persisted.load_json/save_json`.
- `poor_cli/history.py` — same.
- `poor_cli/config.py` — narrow: only the functions that persist preferences. **Do not refactor anything else.** 🟠
- `poor_cli/automation_manager.py` — same.
- `poor_cli/checkpoint.py` — same.
- `poor_cli/audit_log.py` — SQLite meta table, versioned opener.

**Delete** — nothing in this PRD. A follow-up will remove `history_migration_marker.json` once one release proves the auto-upgrade stable.

## 6. Implementation plan

1. Land `poor_cli/persisted/schema.py` and `migrations.py` with no integrations yet.
2. Land the envelope wrapper functions `load_json` / `save_json`. Unit test them.
3. Migrate `preferences.json` load/save first. Write the v0 → v1 migration. Write a test that reads a pre-envelope fixture file (`tests/fixtures/persisted/preferences_v0.json`) and writes out an envelope.
4. Migrate `history.json`. Add v0 detection. Keep `history_migration_marker.json` support — the new framework absorbs what that marker did. (Remove the marker in a follow-up release.)
5. Migrate session / automation / checkpoint JSON files the same way.
6. Add the `meta` table + helper to SQLite-backed stores (`audit_log.py`, and stub hooks in `runs.db` and `repo_graph.db` loaders). Migration registry scaffolded but empty — seed with `schema_version = 1`.
7. Integration test: synthesize a v0 directory, load through the new framework, assert output structure, verify the `.legacy-v0/` backup.
8. Update `.gitignore` to exclude `.poor-cli/.legacy-v0/`.
9. `make lint && make test`.

## 7. Testing & acceptance criteria

**New tests**
- `test_persisted_schema.py::test_envelope_roundtrip`
- `test_persisted_schema.py::test_unknown_version_refuses_to_load`
- `test_persisted_schema.py::test_sqlite_meta_table_seeded`
- `test_persisted_migrations.py::test_v0_preferences_auto_upgrade`
- `test_persisted_migrations.py::test_legacy_v0_backup_created`
- `test_persisted_migrations.py::test_migrate_forward_chains_migrations_in_order`
- `test_persisted_migrations.py::test_missing_migration_raises_explicitly`

**Commands to pass**
- `make lint && make test`

**Manual verification**
- Delete `.poor-cli/` from a scratch dir; run `poor-cli exec --prompt "hi"`; verify new envelope format in `preferences.json`.
- Re-run; verify it loads without re-migrating.

**Done criterion**
- [ ] Every persisted JSON artifact has `{schema_version, artifact, data}` on disk.
- [ ] Every SQLite DB has a `meta` table with `schema_version`.
- [ ] Loaders refuse unknown versions with a clear error.
- [ ] v0 auto-upgrade keeps a backup in `.poor-cli/.legacy-v0/`.
- [ ] Tests cover migration chain.

## 8. Rollback / risk

🟠 Moderate — we are rewriting disk format. Mitigations:

- Atomic writes (tempfile + rename) prevent partial-write corruption.
- `.legacy-v0/` backup retained on v0 → v1 upgrade so users can downgrade by restoring the file.
- The wrapper is a superset — reverting the PR requires one release of `poor-cli` that still reads the envelope. Document this in commit and release notes.

## 9. Out-of-scope & boundary

- 🚫 Do not refactor `config.py` broadly. Only touch its JSON load/save paths.
- 🚫 Do not change any artifact's semantic content in this PRD. v0 → v1 is a pure structural wrap.
- 🚫 Do not delete `history_migration_marker.json` in this PR. Leave for follow-up.
- 🚫 Do not change `audit_log.py` schema beyond adding the `meta` table.
- 🚫 Do not add a new artifact to `CURRENT_VERSIONS` unless one of the migrated files requires it.

## 10. Related PRDs & references

- LEARNING.md §1.4 and §2.2.
- Real-world inspiration: Alembic (SQLAlchemy), django-migrations.
- The existing `history_migration_marker.json` documents the past pain.
